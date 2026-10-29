"""Engineering Incident Copilot — an MCP server built with FastMCP.

Run it directly (stdio transport, which is what Claude Desktop / Cursor use):

    python3 mcp_server/incident_server.py

Inspect it in a browser:

    npx @modelcontextprotocol/inspector python3 mcp_server/incident_server.py

Drive it from an LLM:

    python3 mcp_server/client_demo.py

------------------------------------------------------------------------------
The three MCP primitives, and who is in charge of each:

  TOOLS      model-controlled  -- the LLM decides to call these
  RESOURCES  app-controlled    -- the host app decides what to load into context
  PROMPTS    user-controlled   -- the user picks these from a menu

Almost everyone builds only tools and then wonders why the other two exist.
The control axis is the answer.
"""

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DB = Path(__file__).resolve().parent / "incidents.db"

mcp = FastMCP(
    "incident-copilot",
    instructions=(
        "Tools for investigating production incidents. Search past incidents for "
        "prior art before proposing a fix, and read the service runbook before "
        "recommending any action."
    ),
)


def q(sql, args=()):
    """Query helper — returns a list of dicts."""
    if not DB.exists():
        raise FileNotFoundError(
            f"{DB.name} not found. Run: python3 {DB.parent.name}/seed_data.py"
        )
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()


# =============================================================== TOOLS
# Model-controlled. The docstring IS the description the model reads, so write
# it for a competent new joiner who cannot ask you a follow-up question.
# LLM Context Window-  (Prompt Token) + MCP (Incident-Copilot)- 6 Tools ( All 6 Tools Doc String is part of my context window ) 

@mcp.tool()
def search_incidents(query: str, service: str = "", limit: int = 5) -> str:
    """Search past production incidents by keyword.

    Use this BEFORE proposing any fix — someone has usually seen it before.
    Searches the title, summary, resolution and tags.

    Args:
        query: Keywords, e.g. "latency spike" or "connection pool". Not a question.
        service: Optional exact service name to narrow the search, e.g. "checkout-api".
        limit: Max results, 1-20. Default 5.

    Returns:
        Matching incidents with id, service, severity, status and a one-line summary.
        Call get_incident for the full record.
    """
    limit = max(1, min(int(limit), 20))
    like = f"%{query.strip()}%"
    sql = ("SELECT id, service, severity, status, title, summary, tags, opened_at, "
           "duration_min FROM incidents WHERE (title LIKE ? OR summary LIKE ? OR "
           "resolution LIKE ? OR tags LIKE ?)")
    args = [like, like, like, like]
    if service.strip():
        sql += " AND service = ?"
        args.append(service.strip())
    sql += " ORDER BY opened_at DESC LIMIT ?"
    args.append(limit)

    rows = q(sql, args)
    if not rows:
        return (f"No incidents matched '{query}'"
                + (f" for service '{service}'." if service else ".")
                + " Try broader keywords, or list_services to check the name.")

    out = [f"{len(rows)} match(es) for '{query}':"]
    for r in rows:
        out.append(
            f"\n{r['id']}  [{r['severity']}/{r['status']}]  {r['service']}  "
            f"({r['opened_at']}, {r['duration_min']}m)\n"
            f"  {r['title']}\n  {r['summary'][:180]}\n  tags: {r['tags']}"
        )
    return "\n".join(out)


@mcp.tool()
def get_incident(incident_id: str) -> str:
    """Fetch the full record for one incident, including how it was resolved.

    Args:
        incident_id: An id like "INC-1004", exactly as returned by search_incidents.

    Returns:
        The full incident including the resolution, or an error naming the problem.
    """
    rows = q("SELECT * FROM incidents WHERE id = ?", (incident_id.strip().upper(),))
    if not rows:
        return f"No incident with id '{incident_id}'. Use search_incidents to find one."
    r = rows[0]
    return (
        f"{r['id']} — {r['title']}\n"
        f"service    : {r['service']}\n"
        f"severity   : {r['severity']}\n"
        f"status     : {r['status']}\n"
        f"opened     : {r['opened_at']}\n"
        f"resolved   : {r['resolved_at'] or '(still open)'}\n"
        f"duration   : {r['duration_min']} min\n"
        f"tags       : {r['tags']}\n\n"
        f"SUMMARY\n{r['summary']}\n\n"
        f"RESOLUTION\n{r['resolution'] or '(not yet resolved)'}"
    )


@mcp.tool()
def search_runbooks(query: str, service: str = "") -> str:
    """Search the operational runbooks for a documented procedure.

    Use this to find the approved fix before improvising one. Matches on individual
    words, so "connection pool" also finds "connection-pool exhaustion".

    Args:
        query: What you need to do or diagnose, e.g. "connection pool" or "rotate keys".
        service: Optional exact service name to search only that runbook.

    Returns:
        The matching runbook sections, most relevant first, with their service.
    """
    words = [w for w in re.split(r"[^a-z0-9]+", query.lower()) if len(w) > 2]
    if not words:
        return "ERROR: give at least one search word of three or more characters."

    if service.strip():
        rows = q("SELECT service, body FROM runbooks WHERE service = ?",
                 (service.strip(),))
        if not rows:
            return (f"No runbook for '{service}'. Available: "
                    + ", ".join(r["name"] for r in q("SELECT name FROM runbooks")))
    else:
        rows = q("SELECT service, body FROM runbooks")

    # Score each ### section by how many query words it contains, then return only
    # the best ones. Shaping tool output in your own code -- rather than handing the
    # model a whole document -- is the cheapest context saving available.
    def matches(word, text):
        # Crude stemming so "rotate" also finds "rotation" and "keys" finds "key".
        return word in text or (len(word) > 4 and word[:-2] in text)

    scored = []
    for r in rows:
        for section in r["body"].split("\n### "):
            low = section.lower()
            hits = sum(1 for w in words if matches(w, low))
            if hits:
                scored.append((hits, r["service"], section.strip()))
    if not scored:
        return (f"No runbook mentions any of {words}. Services with runbooks: "
                + ", ".join(r["name"] for r in q("SELECT name FROM runbooks")))

    scored.sort(key=lambda x: -x[0])
    out = []
    for hits, svc, section in scored[:3]:
        head = section.splitlines()[0]
        out.append(f"--- {svc} · matched {hits}/{len(words)} terms · {head}\n"
                   f"{section[:900]}")
    return "\n\n".join(out)


@mcp.tool()
def service_health(service: str) -> str:
    """Get the current status and incident history summary for one service.

    Args:
        service: Exact service name, e.g. "auth-service". Use list_services if unsure.

    Returns:
        Owning team, tier, on-call rota, open incidents and recent incident stats.
    """
    svc = service.strip()
    meta = q("SELECT * FROM services WHERE name = ?", (svc,))
    if not meta:
        names = ", ".join(r["name"] for r in q("SELECT name FROM services"))
        return f"Unknown service '{service}'. Known services: {names}"
    m = meta[0]

    stats = q("SELECT COUNT(*) n, SUM(status!='resolved') open_n, "
              "AVG(CASE WHEN duration_min>0 THEN duration_min END) avg_min "
              "FROM incidents WHERE service = ?", (svc,))[0]
    open_rows = q("SELECT id, severity, title, opened_at FROM incidents "
                  "WHERE service = ? AND status != 'resolved' ORDER BY opened_at DESC",
                  (svc,))

    lines = [
        f"{svc}",
        f"  team       : {m['team']}",
        f"  tier       : {m['tier']}",
        f"  on-call    : {m['oncall']}",
        f"  incidents  : {stats['n']} total, {stats['open_n'] or 0} not resolved",
        f"  mean TTR   : {round(stats['avg_min'] or 0)} min",
    ]
    if open_rows:
        lines.append("  OPEN:")
        lines += [f"    {r['id']} [{r['severity']}] {r['title']} ({r['opened_at']})"
                  for r in open_rows]
    return "\n".join(lines)


@mcp.tool()
def list_services() -> str:
    """List every service this server knows about, with its owning team and tier.

    Call this first if you are unsure of an exact service name.
    """
    rows = q("SELECT name, team, tier, oncall FROM services ORDER BY tier, name")
    return "\n".join(f"{r['name']:<16} tier {r['tier']}  {r['team']:<10} {r['oncall']}"
                     for r in rows)


@mcp.tool()
def create_ticket(title: str, severity: str, service: str, body: str) -> str:
    """Create a follow-up ticket. THIS WRITES TO THE TRACKER.

    Only call this when the user has explicitly asked for a ticket to be created.
    Never create one on your own initiative to "record" or "track" something.

    Args:
        title: A short, specific title. Not a question.
        severity: One of SEV1, SEV2, SEV3.
        service: The affected service. Must be a known service name.
        body: What happened, what was tried, and what the follow-up action is.

    Returns:
        The new ticket id, or an error explaining what was wrong with the input.
    """
    sev = severity.strip().upper()
    if sev not in {"SEV1", "SEV2", "SEV3"}:
        return f"ERROR: severity must be SEV1, SEV2 or SEV3 (got '{severity}'). Nothing created."
    if not title.strip():
        return "ERROR: title is empty. Nothing created."
    known = {r["name"] for r in q("SELECT name FROM services")}
    if service.strip() not in known:
        return (f"ERROR: unknown service '{service}'. Known: {', '.join(sorted(known))}. "
                "Nothing created.")

    con = sqlite3.connect(DB)
    try:
        n = con.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        tid = f"TKT-{2000 + n}"
        con.execute("INSERT INTO tickets VALUES (?,?,?,?,?,?,?)",
                    (tid, title.strip(), sev, service.strip(), body.strip(),
                     datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "mcp-agent"))
        con.commit()
    finally:
        con.close()
    return f"Created {tid} [{sev}] on {service}: {title.strip()}"


@mcp.tool()
def rca_report(incident_id: str) -> str:
    """Generate a RCA report for an incident.
    Args:
        incident_id: An id like "INC-1004", exactly as returned by search_incidents.
    Returns:
        The RCA report for the incident."""

    rows = q("SELECT * FROM incidents WHERE id = ?", (incident_id.strip().upper(),))
    if not rows:
        return f"No incident with id '{incident_id}'. Use search_incidents to find one."
    r = rows[0]
    return f"Report for {incident_id}"
    return (
        f"{r['id']} — {r['title']}\n"
        f"service    : {r['service']}\n"
        f"severity   : {r['severity']}\n"
        f"status     : {r['status']}\n"
        f"opened     : {r['opened_at']}\n"  
        f"resolved   : {r['resolved_at'] or '(still open)'}\n"
        f"duration   : {r['duration_min']} min\n"
        f"tags       : {r['tags']}\n\n"
        f"SUMMARY\n{r['summary']}\n\n"
        f"RESOLUTION\n{r['resolution'] or '(not yet resolved)'}"
    )



# =========================================================== RESOURCES
# App-controlled. The host decides when to load these into context — the model
# does not call them the way it calls a tool.

@mcp.resource("runbook://{service}")
def runbook(service: str) -> str:
    """The full operational runbook for a service, as markdown."""
    rows = q("SELECT body FROM runbooks WHERE service = ?", (service,))
    if not rows:
        return f"# No runbook for '{service}'"
    return rows[0]["body"]


@mcp.resource("incidents://recent")
def recent_incidents() -> str:
    """The 15 most recent incidents across all services."""
    rows = q("SELECT id, service, severity, status, title, opened_at FROM incidents "
             "ORDER BY opened_at DESC LIMIT 15")
    return "\n".join(
        f"{r['id']}  {r['opened_at']}  [{r['severity']}/{r['status']}]  "
        f"{r['service']:<16} {r['title']}" for r in rows)


@mcp.resource("incidents://open")
def open_incidents() -> str:
    """Every incident that is not yet resolved."""
    rows = q("SELECT id, service, severity, title, opened_at FROM incidents "
             "WHERE status != 'resolved' ORDER BY severity, opened_at DESC")
    if not rows:
        return "No open incidents."
    return "\n".join(f"{r['id']}  [{r['severity']}]  {r['service']:<16} {r['title']}  "
                     f"(since {r['opened_at']})" for r in rows)


# ============================================================= PROMPTS
# User-controlled. These show up as slash-commands / menu items in the host app.

@mcp.prompt()
def postmortem_draft(incident_id: str) -> str:
    """Draft a blameless postmortem for an incident."""
    return f"""Draft a blameless postmortem for {incident_id}.

Steps:
1. Call get_incident("{incident_id}") for the full record.
2. Call search_incidents with its key symptom to find prior occurrences.
3. Call search_runbooks to check whether a documented procedure already covered it.

Then write, in this order:
- **Impact** — who was affected, for how long, and how you know.
- **Timeline** — detection, diagnosis, mitigation, resolution.
- **Root cause** — the contributing conditions, not a person.
- **What went well** / **What was difficult**.
- **Action items** — each one specific, owned, and testable.

If any prior incident had the same root cause, say so explicitly and ask why the
earlier action item did not prevent this one."""


@mcp.prompt()
def triage(symptom: str) -> str:
    """Triage a live symptom against history and runbooks."""
    return f"""We are seeing: {symptom}

Work in this order and show your reasoning:
1. list_services, then service_health on the most likely service.
2. search_incidents for this symptom — has it happened before?
3. search_runbooks for the documented procedure.
4. Recommend the next concrete action, citing the incident id or runbook section
   it came from.

If the history and the runbook disagree, say so rather than picking one silently.
Do not create a ticket unless I ask."""


if __name__ == "__main__":
    mcp.run(transport="stdio")
