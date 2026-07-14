# ✈️ TripMate AI — A Multi‑Agent Travel Planner (v2.0)

**TripMate AI** is an open‑source AI travel planner that turns a natural‑language request into a practical travel plan. It now ships with **six major upgrades**:

1. **Currency Converter MCP Server** – a custom MCP server (`custom_currency_mcp_server.py`) that uses the free ExchangeRate API to convert budgets and fetch live rates.
2. **Restaurant Finder Agent** – searches the best local restaurants and food recommendations via Tavily MCP.
3. **LangGraph Conditional Routing** – the request is classified (`full_trip`, `flights_only`, `hotels_only`, `weather_only`) and irrelevant agents are **skipped**, speeding up execution.
4. **SQLite/MemorySaver Fallback** – if `DATABASE_URL` is not set the app falls back to an in‑memory checkpointer, so you can run the project locally without a database.
5. **Server‑Sent Events (SSE) Streaming** – the `/api/travel/stream` endpoint streams real‑time updates as each agent finishes, driving an 8‑step stepper UI.
6. **User Authentication** – simple HMAC‑signed session cookies, a premium login page, and a logout button protect the planner.

The UI has been refreshed to match the **Aurora Dark Theme** with glass‑morphism, micro‑animations, and a new **8‑step stepper** and **7 result tabs**.

---

## 📦 Tech Stack

- **Python 3.10+**
- **FastAPI**
- **LangGraph + LangChain** (agent orchestration)
- **Groq** (LLM inference)
- **MCP** (`langchain-mcp-adapters` + `mcp` server/client)
- **Tavily API** (web search)
- **AviationStack API** (flight data)
- **OpenWeather API** (weather data)
- **PostgreSQL** (persisted state) – optional, falls back to **MemorySaver**
- **HTML / CSS / JavaScript** – premium Aurora design, SSE‑driven UI

---

## 📂 Project Structure

```text
.
├── app.py                      # FastAPI entry point (auth, health, endpoints)
├── backend.py                  # LangGraph workflow + new agents & routing
├── mcp_client.py               # MCP client helpers (weather, flight, tavily, currency)
├── custom_weather_mcp_server.py# Existing weather MCP server
├── custom_currency_mcp_server.py# **NEW** – currency conversion MCP server
├── static/                     # CSS, JS, images
│   ├── style.css               # Updated with .astep.skipped & 4‑column grid
│   └── script.js               # SSE streaming + logout handler
├── templates/                  # HTML templates
│   ├── index.html              # Main UI with 8‑step stepper & 7 tabs
│   └── login.html              # **NEW** – premium login page
├── .env                        # Environment variables (incl. auth creds)
└── README.md                   # **UPDATED** – reflects all changes
```

---

## 🔧 Prerequisites

- Python 3.10 or newer
- (Optional) PostgreSQL instance – if omitted the app uses an in‑memory saver.
- API keys for:
  - **Groq**
  - **Tavily**
  - **AviationStack**
  - **OpenWeather**
- `uvx` installed for the local `aviationstack-mcp` command (or adjust `mcp_client.py`).

---

## 🌱 Environment Variables

Create a `.env` file in the project root:

```env
# ── Core configuration ───────────────────────
DATABASE_URL=postgresql://user:password@localhost:5432/travel_db   # optional
GROQ_API_KEY=your_groq_api_key
AVIATIONSTACK_API_KEY=your_aviationstack_api_key
TAVILY_API_KEY=your_tavily_api_key
OPENWEATHER_API_KEY=your_openweather_api_key
DEFAULT_ORIGIN_IATA=HYD

# ── Feature 6: Authentication (CHANGE BEFORE PRODUCTION!) ───────
TRIPMATE_USER=admin
TRIPMATE_PASSWORD=tripmate123
SECRET_KEY=tripmate-secret-key-change-in-production
```

> **Note:** `.env` is listed in `.gitignore`, so your credentials never get committed.

---

## 📦 Installation

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 🚀 Running the Application

```bash
# Start the FastAPI server (development mode with auto‑reload)
python app.py
```

Open your browser and go to:

```
http://127.0.0.1:8000/
```

You will be redirected to the **login page**. Use the credentials defined in `.env` (default `admin / tripmate123`). Once logged in you can start creating travel plans.

---

## 📡 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/health` | Simple health check |
| GET    | `/login` | Render login page |
| POST   | `/api/login` | Validate credentials, set session cookie |
| POST   | `/api/logout` | Clear session cookie |
| POST   | `/api/travel` | Traditional (non‑streaming) travel request |
| POST   | `/api/travel/stream` | **SSE streaming** – real‑time agent updates |

### Example (streaming) request
```bash
curl -X POST http://127.0.0.1:8000/api/travel/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"Plan a 5‑day trip to Bali with a $1500 budget","thread_id":null}'
```
The response is a `text/event-stream` that pushes events such as `router_done`, `flight_done`, … `final_done`.

---

## 🧭 How the Workflow Works

1. **Authentication** – middleware validates the session cookie.
2. **Router** – classifies the query (`full_trip`, `flights_only`, `hotels_only`, `weather_only`).
3. **Agents** – each agent runs only if required:
   - Flight, Hotel, Weather, Restaurant, Currency, Itinerary, Formatter.
4. **Conditional Routing** – skipped agents are marked with a dimmed stepper style (`.astep.skipped`).
5. **Streaming** – each agent emits an SSE event; the UI updates the stepper instantly.
6. **Final Answer** – formatted with 9 sections (summary, flight, hotel, weather, restaurants, currency, itinerary, budget, recommendations).

---

## 🙋‍♀️ Contributing

1. Fork the repository.
2. Create a feature branch (`git checkout -b my‑feature`).
3. Make your changes and ensure the UI still respects the Aurora design.
4. Run the test suite (if any) and `git push`.
5. Open a Pull Request.

---

## 📜 Acknowledgments

Built with love using LangGraph, MCP, Groq, and a handful of travel APIs. The UI design follows the **Aurora Dark Theme** with glass‑morphism and subtle micro‑animations.
