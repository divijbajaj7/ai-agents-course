"""Nimbus support desk -- a small FastMCP server over a tickets table."""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("nimbus-support")

TICKETS = [
    {"id": "T-2101", "product": "Orbit",    "opened": "2026-03-09", "status": "open",   "summary": "Watch hot while charging, burning smell"},
    {"id": "T-2102", "product": "Orbit",    "opened": "2026-03-11", "status": "open",   "summary": "App logs me out every day, lost workouts"},
    {"id": "T-2103", "product": "Orbit",    "opened": "2026-03-14", "status": "closed", "summary": "Strap broke, replaced"},
    {"id": "T-2104", "product": "Orbit",    "opened": "2026-03-22", "status": "open",   "summary": "Notifications arrive 5 minutes late"},
    {"id": "T-2105", "product": "Pulse X1", "opened": "2026-03-02", "status": "open",   "summary": "Left bud disconnects during calls"},
    {"id": "T-2106", "product": "Echo Bar", "opened": "2026-02-18", "status": "closed", "summary": "Stopped working after rain"},
]


@mcp.tool()
def list_tickets(product: str, status: str = "open") -> str:
    """List support tickets for a product.

    Args:
        product: "Orbit", "Pulse X1" or "Echo Bar".
        status: "open", "closed" or "all".
    """
    hits = [t for t in TICKETS if t["product"].lower() == product.lower()
            and (status == "all" or t["status"] == status)]
    return "\n".join(f"{t['id']} [{t['status']}] {t['opened']}: {t['summary']}" for t in hits) or "No tickets."


if __name__ == "__main__":
    mcp.run(transport="stdio")
