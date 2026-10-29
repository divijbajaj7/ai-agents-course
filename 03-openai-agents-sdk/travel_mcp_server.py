"""Travel facts MCP server (FastMCP, stdio). Written by the Week 11 notebook."""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("travel-facts")

RATES_TO_INR = {"INR": 1.0, "USD": 88.2, "EUR": 102.9, "GBP": 118.4, "AED": 24.0, "SGD": 68.6}
FACTS = {
    "goa":       {"country": "India",     "currency": "INR", "timezone": "UTC+5:30", "plug": "Type C/D", "emergency": "112"},
    "dubai":     {"country": "UAE",       "currency": "AED", "timezone": "UTC+4",    "plug": "Type G",   "emergency": "999"},
    "singapore": {"country": "Singapore", "currency": "SGD", "timezone": "UTC+8",    "plug": "Type G",   "emergency": "999"},
}


@mcp.tool()
def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert an amount between currencies at indicative rates.

    Args:
        amount: The amount to convert.
        from_currency: ISO code, e.g. "INR".
        to_currency: ISO code, e.g. "SGD".
    """
    f, t = from_currency.upper(), to_currency.upper()
    if f not in RATES_TO_INR or t not in RATES_TO_INR:
        return f"Unsupported currency. Supported: {', '.join(RATES_TO_INR)}"
    return f"{amount:,.2f} {f} = {amount * RATES_TO_INR[f] / RATES_TO_INR[t]:,.2f} {t} (indicative)"


@mcp.tool()
def destination_facts(city: str) -> str:
    """Practical facts for a destination: currency, timezone, plug type, emergency number.

    Args:
        city: City name, e.g. "Dubai".
    """
    f = FACTS.get(city.strip().lower())
    if not f:
        return f"No facts for '{city}'. Known: {', '.join(c.title() for c in FACTS)}"
    return "; ".join(f"{k}: {v}" for k, v in f.items())


if __name__ == "__main__":
    mcp.run(transport="stdio")