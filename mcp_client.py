import os
import asyncio
import certifi
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_groq import ChatGroq

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

load_dotenv()


TAVILY_API_KEY     = os.getenv("TAVILY_API_KEY")
AVIATION_STACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
OPENWEATHER_API_KEY    = os.getenv("OPENWEATHER_API_KEY")
GROQ_API_KEY           = os.getenv("GROQ_API_KEY")


# LLM (used for destination extraction)
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=GROQ_API_KEY
)


# ============================================================
# Feature 1 + 2: MultiServerMCPClient — 4 servers connected
#
# Transport types:
#   streamable_http → Tavily (remote HTTP MCP server)
#   stdio           → AviationStack, Weather, Currency (local subprocess)
# ============================================================

client = MultiServerMCPClient(
    {
        # Tavily: remote web-search MCP over HTTP
        "tavily": {
            "transport": "streamable_http",
            "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={TAVILY_API_KEY}"
        },

        # AviationStack: live flight data (runs as uvx subprocess)
        "aviationstack": {
            "transport": "stdio",
            "command": "uvx",
            "args": [
                "aviationstack-mcp"
            ],
            "env": {
                "AVIATION_STACK_API_KEY": AVIATION_STACK_API_KEY
            }
        },

        # Feature 1: Custom Weather MCP Server (local Python subprocess)
        "weather": {
            "transport": "stdio",
            "command": "/Users/adithyaboyapati/anaconda3/envs/bapi_lang/bin/python",
            "args": [
                "/Users/adithyaboyapati/Desktop/bappy_Tutorials/TripMate-AI-Using-MCP/custom_weather_mcp_server.py"
            ],
            "env": {
                "OPENWEATHER_API_KEY": OPENWEATHER_API_KEY
            }
        },

        # Feature 1: NEW Currency Converter MCP Server (local Python subprocess)
        "currency": {
            "transport": "stdio",
            "command": "/Users/adithyaboyapati/anaconda3/envs/bapi_lang/bin/python",
            "args": [
                "/Users/adithyaboyapati/Desktop/bappy_Tutorials/TripMate-AI-Using-MCP/custom_currency_mcp_server.py"
            ]
        }
    }
)


###################################
# Debug: Print all available tools
###################################

async def get_all_tools():
    tools = await client.get_tools()
    print("\nAvailable MCP Tools:\n")
    for tool in tools:
        print(tool.name)


###################################
# Tavily + Aviation Tools
###################################

search_tool    = None
aviation_tools = {}


async def initialize_mcp():
    """Lazily initialize Tavily search tool on first use."""
    global search_tool
    global aviation_tools

    if search_tool is not None and aviation_tools:
        return

    tools = await client.get_tools()

    print("\nAvailable MCP Tools:\n")
    for tool in tools:
        print(tool.name)

    search_tool = next(
        tool
        for tool in tools
        if tool.name == "tavily_search"
    )

    aviation_tools = {
        tool.name: tool
        for tool in tools
        if tool.name != "tavily_search"
    }


async def tavily_mcp_search(query: str):
    """Search the web using Tavily MCP."""
    await initialize_mcp()
    result = await search_tool.ainvoke({"query": query})
    return result


# Feature 2: Restaurant search — reuses Tavily with restaurant-specific query
async def restaurant_mcp_search(query: str):
    """
    Search for restaurants and local food using Tavily MCP.
    Same tool as tavily_search — just a dedicated wrapper for clarity.
    """
    await initialize_mcp()
    result = await search_tool.ainvoke({"query": query})
    return result


async def aviation_mcp_call(tool_name: str, tool_args: dict = None):
    """Call any AviationStack MCP tool by name."""
    tools = await client.get_tools()

    tool = next(
        t for t in tools
        if t.name == tool_name
    )

    result = await tool.ainvoke(tool_args or {})
    return result


###################################
# Weather Tools
###################################

weather_tool  = None
forecast_tool = None


async def initialize_weather_tools():
    """Lazily initialize weather tools on first use."""
    global weather_tool, forecast_tool

    if weather_tool is not None:
        return

    tools = await client.get_tools()

    weather_tool = next(
        t for t in tools
        if t.name == "get_current_weather"
    )

    forecast_tool = next(
        t for t in tools
        if t.name == "get_forecast"
    )


async def weather_mcp_search(city: str):
    """Get current weather for a city via Weather MCP."""
    await initialize_weather_tools()
    return await weather_tool.ainvoke({"city": city})


async def forecast_mcp_search(city: str):
    """Get weather forecast for a city via Weather MCP."""
    await initialize_weather_tools()
    return await forecast_tool.ainvoke({"city": city})


###################################
# Feature 2: Currency Tools (NEW)
###################################

currency_convert_tool = None


async def initialize_currency_tool():
    """Lazily initialize the currency conversion tool on first use."""
    global currency_convert_tool

    if currency_convert_tool is not None:
        return

    tools = await client.get_tools()

    currency_convert_tool = next(
        t for t in tools
        if t.name == "convert_currency"
    )


async def currency_mcp_convert(amount: float, from_currency: str, to_currency: str):
    """
    Convert currency using the Currency MCP server.

    Example:
        result = await currency_mcp_convert(2000.0, "USD", "JPY")
    """
    await initialize_currency_tool()
    return await currency_convert_tool.ainvoke({
        "amount":        amount,
        "from_currency": from_currency,
        "to_currency":   to_currency
    })


###################################
# Destination Extractor
###################################

def extract_destination(query: str):
    """
    Uses the Groq LLM to extract just the destination city/country from
    the user's natural language query.

    Example:
        "Plan a 7-day Japan trip from Hyderabad" → "Japan"
    """
    prompt = f"""
    Extract only the destination city or country.

    Query:
    {query}

    Return only destination name.
    """

    response = llm.invoke(prompt)
    return response.content.strip()
