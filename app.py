"""
app.py — FastAPI Web Server
============================

Features implemented here:
  Feature 5: /api/travel/stream — SSE streaming endpoint
  Feature 6: User authentication (middleware + login/logout routes)

Routes:
  GET  /           → main travel planner page (requires auth)
  GET  /login      → login page
  POST /api/login  → validates credentials, sets session cookie
  POST /api/logout → clears session cookie
  POST /api/travel          → standard (non-streaming) travel planner
  POST /api/travel/stream   → Feature 5: SSE streaming travel planner
  GET  /health     → health check (public)
"""

from pathlib import Path
import traceback
import time
import hmac
import hashlib
import json
import secrets
import os
import uvicorn

from fastapi import FastAPI, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    Response,
    StreamingResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from backend import run_travel_agent, stream_travel_agent

# Allow asyncio.run() inside FastAPI's existing event loop
import nest_asyncio
nest_asyncio.apply()


BASE_DIR = Path(__file__).resolve().parent


# ============================================================
# Feature 6: Auth Configuration
#
# Credentials are stored in .env:
#   TRIPMATE_USER=admin
#   TRIPMATE_PASSWORD=yourpassword
#
# Sessions use HMAC-SHA256 signed tokens stored in a cookie.
# No external auth library needed — only Python built-ins.
# ============================================================

SECRET_KEY        = os.getenv("SECRET_KEY",         "tripmate-secret-key-change-in-production")
TRIPMATE_USER     = os.getenv("TRIPMATE_USER",      "admin")
TRIPMATE_PASSWORD = os.getenv("TRIPMATE_PASSWORD",  "tripmate123")
COOKIE_NAME       = "tripmate_session"


def create_session_token(username: str) -> str:
    """
    Creates a signed session token.
    Format: base64(payload).hmac_signature
    """
    from base64 import b64encode
    payload     = json.dumps({"u": username, "t": int(time.time())})
    payload_b64 = b64encode(payload.encode()).decode()
    sig         = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_session_token(token: str) -> bool:
    """Verifies the HMAC signature of a session token."""
    try:
        payload_b64, sig  = token.rsplit(".", 1)
        expected_sig      = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig)
    except Exception:
        return False


# ============================================================
# FastAPI App
# ============================================================

app = FastAPI(
    title="TripMate AI",
    description="LangGraph Multi-Agent Travel Planner with FastAPI + MCP",
    version="2.0.0"
)


# ---- Middleware 1: No-cache for static files ----
@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"]        = "no-cache"
        response.headers["Expires"]       = "0"
    return response


# ---- Middleware 2: Feature 6 — Auth Gate ----
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """
    Intercepts every request and checks for a valid session cookie.
    Public paths bypass the check. Everything else requires auth.
    """
    public_paths = [
        "/login",
        "/api/login",
        "/static/",
        "/favicon.ico",
        "/health",
    ]

    if any(request.url.path.startswith(p) for p in public_paths):
        return await call_next(request)

    session = request.cookies.get(COOKIE_NAME)
    if not session or not verify_session_token(session):
        return RedirectResponse(url="/login", status_code=302)

    return await call_next(request)


# ---- Static files & templates ----
app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)

templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)


# ============================================================
# Pydantic Models
# ============================================================

class TravelRequest(BaseModel):
    message:   str
    thread_id: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


# ============================================================
# Feature 6: Auth Routes
# ============================================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login page. Redirect to home if already logged in."""
    session = request.cookies.get(COOKIE_NAME)
    if session and verify_session_token(session):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        request=request, name="login.html", context={}
    )


@app.post("/api/login")
async def login(request_data: LoginRequest):
    """Validate credentials and set a signed session cookie."""
    valid_user = secrets.compare_digest(
        request_data.username.strip(), TRIPMATE_USER
    )
    valid_pass = secrets.compare_digest(
        request_data.password, TRIPMATE_PASSWORD
    )

    if not (valid_user and valid_pass):
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Invalid username or password."}
        )

    token    = create_session_token(request_data.username)
    response = JSONResponse(content={"success": True})
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=86400,   # 24 hours
        samesite="lax"
    )
    return response


@app.post("/api/logout")
async def logout():
    """Clear the session cookie."""
    response = JSONResponse(content={"success": True})
    response.delete_cookie(COOKIE_NAME)
    return response


# ============================================================
# Main App Routes
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


@app.post("/api/travel")
async def travel_planner(request_data: TravelRequest):
    """
    Standard (non-streaming) travel planner endpoint.
    Waits for all agents to finish, then returns everything in one JSON response.
    """
    try:
        user_message = request_data.message.strip()

        if not user_message:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Message cannot be empty."}
            )

        result = run_travel_agent(
            user_input=user_message,
            thread_id=request_data.thread_id
        )

        return JSONResponse(
            content={
                "success":            True,
                "thread_id":          result["thread_id"],
                "answer":             result["answer"],
                "flight_results":     result["flight_results"],
                "hotel_results":      result["hotel_results"],
                "weather_results":    result.get("weather_results",    ""),
                "restaurant_results": result.get("restaurant_results", ""),
                "currency_results":   result.get("currency_results",   ""),
                "itinerary":          result["itinerary"],
                "llm_calls":          result["llm_calls"],
                "route":              result.get("route", "full_trip"),
            }
        )

    except Exception as e:
        print("ERROR:", e)
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.post("/api/travel/stream")
async def travel_planner_stream(request_data: TravelRequest):
    """
    Feature 5: SSE Streaming endpoint.

    Returns a text/event-stream response. Each agent's result is sent
    as a separate SSE event as soon as that agent finishes — no waiting
    for the whole pipeline.

    SSE event types:
      start         — pipeline started
      router_done   — query classified (includes route type)
      flight_done   — flight agent finished
      hotel_done    — hotel agent finished
      weather_done  — weather agent finished
      restaurant_done — restaurant agent finished
      currency_done — currency agent finished
      itinerary_done — itinerary agent finished
      final_done    — final formatter finished
      complete      — all done (includes thread_id + llm_calls)
      error         — something went wrong
    """
    user_message = request_data.message.strip()

    if not user_message:
        return JSONResponse(
            status_code=400,
            content={"error": "Message cannot be empty."}
        )

    def generate():
        yield from stream_travel_agent(user_message, request_data.thread_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",    # Disable nginx buffering if behind a proxy
            "Connection":       "keep-alive",
        }
    )


@app.get("/health")
async def health_check():
    return {
        "status":  "ok",
        "message": "TripMate AI v2.0 is running",
        "version": "2.0.0"
    }


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={})


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )