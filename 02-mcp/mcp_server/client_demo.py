"""Drive the incident MCP server with a real LLM.

    export OPENAI_API_KEY=sk-...
    python3 mcp_server/client_demo.py
    python3 mcp_server/client_demo.py "why is checkout slow?"

This is the payoff of the whole session. The agent loop is *identical* to the one
written by hand in notebook 01 — the only difference is where the tool list comes
from. Yesterday it was a Python list you typed. Today it is `tools/list` over MCP.

    hand-written:   TOOLS = [SEARCH_TOOL, CALC_TOOL, ...]
    over MCP:       TOOLS = to_openai(await session.list_tools())

Everything else — the while loop, the dispatch, the tool messages — is unchanged.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI

HERE = Path(__file__).resolve().parent
SERVER = HERE / "incident_server.py"

# Keys live in week10/.env so nothing is hard-coded in the scripts.
try:
    from dotenv import load_dotenv
    load_dotenv(HERE.parent / ".env")
except ImportError:
    pass

MODEL = "gpt-4.1-mini"
MAX_STEPS = 8

SYSTEM = """You are an incident response assistant for an engineering team.

TOOL POLICY
- Search past incidents before proposing any fix. Someone has usually seen it before.
- Check the runbook before recommending an action, and cite which one you used.
- Use list_services if you are unsure of an exact service name.
- Never create a ticket unless the user explicitly asks for one.

STOPPING CONDITION
- Stop once you can answer. Do not keep searching for more context.

OUTPUT
- A short recommendation, then the incident ids and runbook sections you relied on.

FAILURE
- If a tool returns an error twice, stop and report what you tried. Never invent
  an incident id, a service name, or a runbook step."""


def to_openai(mcp_tools):
    """Convert MCP tool definitions into OpenAI function-calling schemas.

    This ten-line function is the entire bridge between the two worlds. MCP already
    gives you a name, a description and a JSON Schema — which is exactly the three
    things OpenAI wants. That is not a coincidence; it is the point of the protocol.
    """
    return [{
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description or "",
            "parameters": t.inputSchema or {"type": "object", "properties": {}},
        },
    } for t in mcp_tools]


async def run(goal: str, verbose: bool = True) -> str:
    client = OpenAI()
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            listed = (await session.list_tools()).tools
            tools = to_openai(listed)

            if verbose:
                print(f"connected to '{info.serverInfo.name}' "
                      f"— {len(tools)} tools discovered over MCP:")
                for t in listed:
                    print(f"    {t.name}")
                print()

            messages = [{"role": "system", "content": SYSTEM},
                        {"role": "user", "content": goal}]

            # ---- the loop from notebook 01, unchanged ----------------------
            for step in range(1, MAX_STEPS + 1):
                reply = client.chat.completions.create(
                    model=MODEL, messages=messages, tools=tools,
                ).choices[0].message
                messages.append(reply)

                if not reply.tool_calls:
                    return reply.content

                # The model often narrates alongside its tool calls. That is the
                # "thought" half of Thought -> Action -> Observation, so show it --
                # but only mid-loop, or we would print the final answer twice.
                if verbose and reply.content:
                    print(f"  [{step}] THOUGHT     {reply.content.strip()[:110]}")

                for call in reply.tool_calls:
                    args = json.loads(call.function.arguments or "{}")
                    if verbose:
                        print(f"  [{step}] ACTION      {call.function.name}({args})")
                    try:
                        # The one real change: dispatch goes over the protocol
                        # instead of into a local dict.
                        result = await session.call_tool(call.function.name, args)
                        out = "\n".join(c.text for c in result.content
                                        if getattr(c, "text", None))
                    except Exception as exc:
                        out = f"ERROR: {type(exc).__name__}: {exc}"
                    if verbose:
                        first = out.splitlines()[0] if out.strip() else "(empty)"
                        print(f"      OBSERVATION {first[:88]}")
                    messages.append({"role": "tool", "tool_call_id": call.id,
                                     "content": out[:4000]})

            return "Stopped: hit the step budget without reaching an answer."


DEFAULT = ("checkout-api p99 latency just jumped to 4 seconds. Has this happened "
           "before, and what should I do first?")

if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("No OPENAI_API_KEY. Put one in week10/.env or export it.")
    question = " ".join(sys.argv[1:]) or DEFAULT
    print(f"GOAL: {question}\n")
    print(asyncio.run(run(question)))
