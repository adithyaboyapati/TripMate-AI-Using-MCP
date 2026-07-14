"""
backend.py — LangGraph Multi-Agent Orchestration
=================================================

This file contains ALL the agent logic and the LangGraph graph.

Features implemented here:
  Feature 2: Restaurant Agent + Currency Agent (two new agents)
  Feature 3: LangGraph Conditional Routing (skip irrelevant agents)
  Feature 4: SQLite / MemorySaver fallback (no DATABASE_URL needed)
  Feature 5: SSE Streaming via stream_travel_agent() generator

Agent Pipeline (full_trip route):
  START → router → flight → hotel → weather → restaurant → currency → itinerary → final → END

Conditional routes (partial queries):
  flights_only : router → flight → final
  hotels_only  : router → hotel → final
  weather_only : router → weather → final
"""

import os
import json
import certifi
from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from typing import TypedDict, Annotated
import operator
import uuid
import asyncio
import psycopg
from psycopg.rows import dict_row

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
)
from langchain_groq import ChatGroq
from mcp_client import (
    tavily_mcp_search,
    aviation_mcp_call,
    extract_destination,
    forecast_mcp_search,
    weather_mcp_search,
    restaurant_mcp_search,   # Feature 2: new
    currency_mcp_convert,    # Feature 2: new
)


GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing. Please add it to your .env file.")


# =========================
# LLM
# =========================

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=GROQ_API_KEY
)


# =========================
# Feature 2+3: Extended State
#
# Every field here is shared across ALL agents.
# Annotated[list, operator.add] means messages are APPENDED not overwritten.
# =========================

class TravelState(TypedDict):
    messages:           Annotated[list[AnyMessage], operator.add]
    user_query:         str
    # Agent outputs
    flight_results:     str
    hotel_results:      str
    weather_results:    str
    restaurant_results: str    # Feature 2
    currency_results:   str    # Feature 2
    itinerary:          str
    # Metadata
    llm_calls:          int
    route:              str    # Feature 3: "full_trip"|"flights_only"|"hotels_only"|"weather_only"


# =======================================================
# Feature 3: Router Agent
#
# The FIRST node in the graph. Uses the LLM to classify
# the user's query and decides which agents to run.
# =======================================================

def query_router(state: TravelState):
    print("\nINSIDE QUERY ROUTER\n")

    prompt = f"""
Classify this travel query into exactly one of these categories:

- full_trip     : User wants complete trip planning (flights + hotels + weather + restaurants + itinerary)
- flights_only  : User only wants flight information, live flights, or flight schedules
- hotels_only   : User only wants hotel or accommodation information
- weather_only  : User only wants weather information for a city or destination

Query: {state['user_query']}

Return ONLY one of these exact strings (no explanation, no punctuation):
full_trip
flights_only
hotels_only
weather_only
"""

    response = llm.invoke(prompt)
    route = response.content.strip().lower().split()[0]  # take first word only

    valid_routes = {"full_trip", "flights_only", "hotels_only", "weather_only"}
    if route not in valid_routes:
        route = "full_trip"

    print(f"\nROUTE DETERMINED: {route}\n")

    return {
        "route":    route,
        "messages": [AIMessage(content=f"Query classified as: {route}")],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =======================================================
# Feature 3: Conditional Edge Functions
#
# These functions read state["route"] and return the name
# of the NEXT node. LangGraph uses them as conditional edges.
# =======================================================

def route_after_router(state: TravelState) -> str:
    """After router: decide first agent based on route type."""
    route = state.get("route", "full_trip")
    if route in ("full_trip", "flights_only"):
        return "flight_agent"
    elif route == "hotels_only":
        return "hotel_agent"
    elif route == "weather_only":
        return "weather_agent"
    return "flight_agent"  # safe default


def route_after_flight(state: TravelState) -> str:
    """After flight agent: continue to hotel only for full_trip."""
    if state.get("route", "full_trip") == "full_trip":
        return "hotel_agent"
    return "final_agent"


def route_after_hotel(state: TravelState) -> str:
    """After hotel agent: continue to weather only for full_trip."""
    if state.get("route", "full_trip") == "full_trip":
        return "weather_agent"
    return "final_agent"


def route_after_weather(state: TravelState) -> str:
    """After weather agent: continue to restaurant only for full_trip."""
    if state.get("route", "full_trip") == "full_trip":
        return "restaurant_agent"
    return "final_agent"


# =========================
# Flight Agent
# =========================

FLIGHT_AGENT_PROMPT = """
You are a travel flight expert.

User Query:
{query}

Airport Information:
{airport_data}

Airline Information:
{airline_data}

Generate:

1. Likely departure airport
2. Likely arrival airport
3. Airlines serving this route
4. Typical flight duration
5. Estimated airfare range
6. Peak season pricing warning
7. Booking advice

Return concise travel guidance.
"""


def flight_agent(state: TravelState):
    print("\nINSIDE FLIGHT AGENT\n")

    query = state["user_query"]

    try:
        airports = asyncio.run(
            aviation_mcp_call("list_airports")
        )

        airlines = asyncio.run(
            aviation_mcp_call("list_airlines")
        )

        print("\nAIRPORTS:", airports)
        print("\nAIRLINES:", airlines)

        prompt = FLIGHT_AGENT_PROMPT.format(
            query=query,
            airport_data=str(airports)[:3000],
            airline_data=str(airlines)[:3000]
        )

        response = llm.invoke([
            SystemMessage(content="You are an expert travel flight planner."),
            HumanMessage(content=prompt)
        ])

        flight_data = response.content

    except Exception as e:
        flight_data = f"Flight information unavailable: {str(e)}"

    return {
        "flight_results": flight_data,
        "messages":       [AIMessage(content="Flight recommendations generated")],
        "llm_calls":      state.get("llm_calls", 0) + 1
    }


# =========================
# Hotel Agent
# =========================

def hotel_agent(state: TravelState):
    print("\nINSIDE HOTEL AGENT\n")

    query        = f"Best hotels for {state['user_query']}"
    hotel_results = asyncio.run(tavily_mcp_search(query))

    return {
        "hotel_results": hotel_results,
        "messages":      [AIMessage(content="Hotel information fetched.")],
        "llm_calls":     state.get("llm_calls", 0) + 1
    }


# =========================
# Weather Agent
# =========================

def weather_agent(state: TravelState):
    print("\nINSIDE WEATHER AGENT\n")

    city = extract_destination(state["user_query"])

    weather_data  = asyncio.run(weather_mcp_search(city))
    forecast_data = asyncio.run(forecast_mcp_search(city))

    return {
        "weather_results": f"""
Current Weather:
{weather_data}

Forecast:
{forecast_data}
        """,
        "messages":  [AIMessage(content="Weather information fetched")],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =========================
# Feature 2: Restaurant Agent (NEW)
#
# Uses Tavily MCP search to find local restaurants and food
# recommendations for the destination city.
# =========================

def restaurant_agent(state: TravelState):
    print("\nINSIDE RESTAURANT AGENT\n")

    city  = extract_destination(state["user_query"])
    query = f"Best restaurants and must-try local food in {city} for tourists 2024"

    try:
        results         = asyncio.run(restaurant_mcp_search(query))
        restaurant_data = str(results)
    except Exception as e:
        restaurant_data = f"Restaurant information unavailable: {str(e)}"

    return {
        "restaurant_results": restaurant_data,
        "messages":           [AIMessage(content="Restaurant information fetched.")],
        "llm_calls":          state.get("llm_calls", 0) + 1
    }


# =========================
# Feature 2: Currency Agent (NEW)
#
# Uses the Currency MCP server to convert the user's budget
# from USD into the destination currency. Destination currency
# is extracted by asking the LLM.
# =========================

def currency_agent(state: TravelState):
    print("\nINSIDE CURRENCY AGENT\n")

    city = extract_destination(state["user_query"])

    # Step 1: Ask LLM what currency this destination uses
    currency_prompt = f"""
What is the ISO 4217 currency code for the primary currency used in {city}?
Return ONLY the 3-letter currency code (e.g., JPY, EUR, USD, THB, INR, SGD).
Do not add any explanation or punctuation.
"""
    currency_response = llm.invoke(currency_prompt)
    to_currency       = currency_response.content.strip().upper()[:3]

    # Step 2: Extract travel budget from the user query
    budget_prompt = f"""
Extract the numeric travel budget in USD from this query.
If no budget is mentioned, return 2000.
Query: {state['user_query']}
Return ONLY a number. No currency symbols, no text, no commas.
"""
    budget_response = llm.invoke(budget_prompt)
    try:
        budget = float(budget_response.content.strip().replace(",", ""))
    except Exception:
        budget = 2000.0

    # Step 3: Call Currency MCP to convert
    try:
        result = asyncio.run(
            currency_mcp_convert(budget, "USD", to_currency)
        )
        currency_data = f"""
**Budget Conversion:**
- Your budget: **${budget:,.0f} USD**
- Destination currency: **{to_currency}**
- Converted: {result.get('summary', str(result))}

Exchange rate source: open.er-api.com (live rates)
"""
    except Exception as e:
        currency_data = f"Currency conversion unavailable: {str(e)}"

    return {
        "currency_results": currency_data,
        "messages":         [AIMessage(content="Currency conversion completed.")],
        "llm_calls":        state.get("llm_calls", 0) + 1
    }


# =========================
# Itinerary Agent (updated to use all results)
# =========================

def itinerary_agent(state: TravelState):
    print("\nINSIDE ITINERARY AGENT\n")

    prompt = f"""
Create a complete travel itinerary.

User Query:
{state['user_query']}

Flight Results:
{state.get('flight_results', 'N/A')}

Hotel Results:
{state.get('hotel_results', 'N/A')}

Weather Results:
{state.get('weather_results', 'N/A')}

Restaurant & Food Guide:
{state.get('restaurant_results', 'N/A')}

Currency Information:
{state.get('currency_results', 'N/A')}

Make the itinerary practical, budget-aware, and easy to follow.
Include restaurant recommendations and local food experiences in the day-by-day plan.
Factor in the currency conversion when estimating daily costs.
"""

    response = llm.invoke([
        SystemMessage(content="You are an expert travel planner."),
        HumanMessage(content=prompt)
    ])

    return {
        "itinerary": response.content,
        "messages":  [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =========================
# Final Response Agent (updated for 9 sections)
# =========================

def final_agent(state: TravelState):
    print("\nINSIDE FINAL AGENT\n")

    final_prompt = f"""
Generate the final travel response for the user.

User Request:
{state['user_query']}

Flights:
{state.get('flight_results', 'N/A')}

Hotels:
{state.get('hotel_results', 'N/A')}

Weather:
{state.get('weather_results', 'N/A')}

Restaurants & Local Food:
{state.get('restaurant_results', 'N/A')}

Currency & Budget:
{state.get('currency_results', 'N/A')}

Itinerary:
{state.get('itinerary', 'N/A')}

Format the final answer beautifully using these sections:

1. Trip Summary
2. Flight Information
3. Hotel Suggestions
4. Weather Information
5. Restaurants & Local Food
6. Currency & Budget Tips
7. Day-by-Day Itinerary
8. Estimated Total Budget
9. Final Recommendations

Important:
- Be clear and practical.
- Mention that live flight API may not provide ticket prices if pricing is unavailable.
- Include weather-based travel advice.
- Include restaurant and street-food recommendations.
- Include currency tips (what to carry, ATM availability).
- Keep the response useful for real travel planning.
"""

    response = llm.invoke([
        SystemMessage(content="You are a professional AI travel booking assistant."),
        HumanMessage(content=final_prompt)
    ])

    return {
        "messages":  [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =========================
# Feature 3: Build the Graph with Conditional Routing
# =========================

graph = StateGraph(TravelState)

# Register all nodes
graph.add_node("router",           query_router)
graph.add_node("flight_agent",     flight_agent)
graph.add_node("hotel_agent",      hotel_agent)
graph.add_node("weather_agent",    weather_agent)
graph.add_node("restaurant_agent", restaurant_agent)
graph.add_node("currency_agent",   currency_agent)
graph.add_node("itinerary_agent",  itinerary_agent)
graph.add_node("final_agent",      final_agent)

# Entry: START → router (always)
graph.add_edge(START, "router")

# Feature 3: Conditional edge from router → depends on route type
graph.add_conditional_edges(
    "router",
    route_after_router,
    {
        "flight_agent": "flight_agent",
        "hotel_agent":  "hotel_agent",
        "weather_agent": "weather_agent",
    }
)

# Feature 3: Conditional edge from flight → hotel (full_trip) OR final (others)
graph.add_conditional_edges(
    "flight_agent",
    route_after_flight,
    {
        "hotel_agent":  "hotel_agent",
        "final_agent":  "final_agent",
    }
)

# Feature 3: Conditional edge from hotel → weather (full_trip) OR final (others)
graph.add_conditional_edges(
    "hotel_agent",
    route_after_hotel,
    {
        "weather_agent": "weather_agent",
        "final_agent":   "final_agent",
    }
)

# Feature 3: Conditional edge from weather → restaurant (full_trip) OR final (others)
graph.add_conditional_edges(
    "weather_agent",
    route_after_weather,
    {
        "restaurant_agent": "restaurant_agent",
        "final_agent":      "final_agent",
    }
)

# Linear tail: restaurant → currency → itinerary → final → END
graph.add_edge("restaurant_agent", "currency_agent")
graph.add_edge("currency_agent",   "itinerary_agent")
graph.add_edge("itinerary_agent",  "final_agent")
graph.add_edge("final_agent",      END)


# ===========================================================
# Feature 4: Smart Checkpointer (SQLite / Memory fallback)
#
# If DATABASE_URL is set → use PostgreSQL (production)
# If not set            → fall back to MemorySaver (local dev)
#
# This means the project runs locally without any DB setup.
# ===========================================================

def build_checkpointer():
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        # Production: PostgreSQL on Render (or any Postgres host)
        if "sslmode=" not in database_url:
            separator    = "&" if "?" in database_url else "?"
            database_url = f"{database_url}{separator}sslmode=require"

        conn = psycopg.connect(
            database_url,
            autocommit=True,
            row_factory=dict_row
        )
        saver = PostgresSaver(conn)
        saver.setup()
        print("✅ Using PostgreSQL checkpointer")
        return saver

    else:
        # Local dev: in-memory (conversation state resets on restart)
        from langgraph.checkpoint.memory import MemorySaver
        print("⚠️  No DATABASE_URL found — using in-memory checkpointer.")
        print("   (State will reset when the server restarts.)")
        return MemorySaver()


checkpointer = build_checkpointer()
travel_graph = graph.compile(checkpointer=checkpointer)


# =========================
# Standard (non-streaming) runner
# =========================

def run_travel_agent(user_input: str, thread_id: str | None = None):
    """
    Runs the full travel agent pipeline synchronously.
    Returns a dict with all results once the graph finishes.
    """
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    result = travel_graph.invoke(
        {
            "messages":           [HumanMessage(content=user_input)],
            "user_query":         user_input,
            "flight_results":     "",
            "hotel_results":      "",
            "weather_results":    "",
            "restaurant_results": "",
            "currency_results":   "",
            "itinerary":          "",
            "llm_calls":          0,
            "route":              ""
        },
        config=config
    )

    final_answer = result["messages"][-1].content

    return {
        "thread_id":          thread_id,
        "answer":             final_answer,
        "flight_results":     result.get("flight_results",     ""),
        "hotel_results":      result.get("hotel_results",      ""),
        "weather_results":    result.get("weather_results",    ""),
        "restaurant_results": result.get("restaurant_results", ""),
        "currency_results":   result.get("currency_results",   ""),
        "itinerary":          result.get("itinerary",          ""),
        "llm_calls":          result.get("llm_calls",          0),
        "route":              result.get("route",              "full_trip"),
    }


# =========================
# Feature 5: SSE Streaming Runner
#
# Uses travel_graph.stream() with stream_mode="updates".
# Each node's output is yielded as an SSE line immediately
# after that node finishes — no more waiting 60s for everything.
#
# SSE format:  data: {"event": "...", ...}\n\n
# =========================

def stream_travel_agent(user_input: str, thread_id: str | None = None):
    """
    Generator that yields SSE-formatted strings in real time.

    Called by the /api/travel/stream endpoint in app.py.
    The frontend reads this stream using the Fetch ReadableStream API.
    """
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "messages":           [HumanMessage(content=user_input)],
        "user_query":         user_input,
        "flight_results":     "",
        "hotel_results":      "",
        "weather_results":    "",
        "restaurant_results": "",
        "currency_results":   "",
        "itinerary":          "",
        "llm_calls":          0,
        "route":              ""
    }

    # Signal the frontend that the stream has started
    yield f"data: {json.dumps({'event': 'start', 'thread_id': thread_id})}\n\n"

    total_llm_calls = 0

    try:
        # stream_mode="updates" → yields only what each node returned (delta)
        for event in travel_graph.stream(
            initial_state,
            config=config,
            stream_mode="updates"
        ):
            # event = { "node_name": { key: value, ... } }
            for node_name, node_output in event.items():

                # Track total LLM calls across all agents
                total_llm_calls = node_output.get("llm_calls", total_llm_calls)

                if node_name == "router":
                    route = node_output.get("route", "full_trip")
                    yield f"data: {json.dumps({'event': 'router_done', 'route': route})}\n\n"

                elif node_name == "flight_agent":
                    yield f"data: {json.dumps({'event': 'flight_done', 'data': node_output.get('flight_results', '')})}\n\n"

                elif node_name == "hotel_agent":
                    yield f"data: {json.dumps({'event': 'hotel_done', 'data': node_output.get('hotel_results', '')})}\n\n"

                elif node_name == "weather_agent":
                    yield f"data: {json.dumps({'event': 'weather_done', 'data': node_output.get('weather_results', '')})}\n\n"

                elif node_name == "restaurant_agent":
                    yield f"data: {json.dumps({'event': 'restaurant_done', 'data': node_output.get('restaurant_results', '')})}\n\n"

                elif node_name == "currency_agent":
                    yield f"data: {json.dumps({'event': 'currency_done', 'data': node_output.get('currency_results', '')})}\n\n"

                elif node_name == "itinerary_agent":
                    yield f"data: {json.dumps({'event': 'itinerary_done', 'data': node_output.get('itinerary', '')})}\n\n"

                elif node_name == "final_agent":
                    messages     = node_output.get("messages", [])
                    final_answer = messages[-1].content if messages else ""
                    yield f"data: {json.dumps({'event': 'final_done', 'data': final_answer})}\n\n"

        # All nodes finished — send the completion signal
        yield f"data: {json.dumps({'event': 'complete', 'thread_id': thread_id, 'llm_calls': total_llm_calls})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"
