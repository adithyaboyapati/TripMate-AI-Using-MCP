"""
Custom Currency Converter MCP Server
=====================================
Feature 1: New MCP Server

This is a hand-built MCP server (just like custom_weather_mcp_server.py)
that wraps the free open.er-api.com ExchangeRate API.

Transport: stdio  →  runs as a subprocess managed by MultiServerMCPClient
No API key required (uses the open/free endpoint).

How it works:
- mcp_client.py spawns this file as a child process
- Communication happens via stdin/stdout using the MCP protocol
- The @mcp.tool() decorator registers each function as a callable tool
"""

from mcp.server.fastmcp import FastMCP
import requests

mcp = FastMCP("Currency MCP Server")


@mcp.tool()
def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """
    Convert an amount from one currency to another using live exchange rates.

    Args:
        amount: The numeric amount to convert (e.g. 2000.0)
        from_currency: ISO 4217 source currency code (e.g. "USD")
        to_currency: ISO 4217 target currency code (e.g. "JPY")

    Returns:
        A dict with the conversion result and exchange rate.
    """

    from_currency = from_currency.strip().upper()
    to_currency   = to_currency.strip().upper()

    url = f"https://open.er-api.com/v6/latest/{from_currency}"

    try:
        response = requests.get(url, timeout=10)
        data = response.json()
    except Exception as e:
        return {"error": f"Network error: {str(e)}"}

    if data.get("result") != "success":
        return {
            "error": f"Exchange rate API error: {data.get('error-type', 'unknown')}"
        }

    rates = data.get("rates", {})
    rate  = rates.get(to_currency)

    if rate is None:
        return {"error": f"Currency code '{to_currency}' not found in exchange rates."}

    converted_amount = round(amount * rate, 2)

    return {
        "from_currency":    from_currency,
        "to_currency":      to_currency,
        "original_amount":  amount,
        "converted_amount": converted_amount,
        "exchange_rate":    rate,
        "summary": (
            f"{amount:,.2f} {from_currency} "
            f"= {converted_amount:,.2f} {to_currency} "
            f"(1 {from_currency} = {rate} {to_currency})"
        )
    }


@mcp.tool()
def get_exchange_rates(base_currency: str) -> dict:
    """
    Get all exchange rates for a given base currency.

    Args:
        base_currency: ISO 4217 base currency code (e.g. "USD")

    Returns:
        A dict with top popular currency rates.
    """

    base_currency = base_currency.strip().upper()
    url = f"https://open.er-api.com/v6/latest/{base_currency}"

    try:
        response = requests.get(url, timeout=10)
        data = response.json()
    except Exception as e:
        return {"error": f"Network error: {str(e)}"}

    if data.get("result") != "success":
        return {"error": "Exchange rate API error"}

    rates = data.get("rates", {})

    # Return most popular currencies only (not all ~160)
    popular = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF",
               "CNY", "INR", "SGD", "AED", "THB", "MYR", "KRW",
               "QAR", "SAR", "TRY", "IDR", "BDT"]

    filtered_rates = {
        cur: rates[cur]
        for cur in popular
        if cur in rates and cur != base_currency
    }

    return {
        "base_currency": base_currency,
        "rates": filtered_rates,
        "last_updated": data.get("time_last_update_utc", "Unknown")
    }


if __name__ == "__main__":
    mcp.run()
