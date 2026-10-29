# Module 2 — Model Context Protocol (Sessions 4–5)

Stop rewriting the same tool for every app. MCP is the standard interface between AI
applications and tools.

| Notebook | Session | What it covers |
|---|---|---|
| `01_mcp_client_with_llm.ipynb` | 4 | Connect to an MCP server, list its tools, convert them to your model's format, and drive them from the agent loop you wrote in module 1 |
| `02_build_mcp_server_stepwise.ipynb` | 5 | Build a server decorator by decorator. **Project: the Engineering Incident Copilot — tools, resources and prompts, plus the security checklist.** |

`mcp_server/` holds the finished server, its seed data and a demo client. Test it with the
MCP Inspector or connect it to a desktop AI client using `claude_desktop_config.json`.

Slides: [`../slides/01-agentic-ai-and-mcp.pptx`](../slides/01-agentic-ai-and-mcp.pptx)
