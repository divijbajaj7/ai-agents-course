# Module 5 — LangGraph (Sessions 11–13)

When a rule must hold every single time, a prompt is not enough. Draw the workflow as a
graph and the unsafe path stops existing.

| Notebook | Session | What it covers |
|---|---|---|
| `01_why_langgraph.ipynb` | 11 | Where agent loops break (run live in two frameworks), then graphs, typed state, nodes, edges and cycles |
| `02_langgraph_basics.ipynb` | 12 | `create_agent` opened up, an agent as a node, checkpoints, time travel, streaming. **Project: a support-ticket router whose safety check cannot be skipped.** |
| `03_hitl_and_agent_teams.ipynb` | 13 | `interrupt` and resume, durable pauses, parallel fan-out, subgraphs, a supervisor. **Project: a blog-writing team with a human approving the outline and signing off.** |

`LangGraph_Foundations_Guide.md` is a written study guide for session 11 — read it before class.

Slides: [`../slides/04-langgraph-foundations.pptx`](../slides/04-langgraph-foundations.pptx) and
[`../slides/05-langgraph-in-practice.pptx`](../slides/05-langgraph-in-practice.pptx)
