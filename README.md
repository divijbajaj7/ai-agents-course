# Building AI Agents — course code

Everything you need for the course: notebooks you run, the slides used in class, and the
supporting code. Thirteen teaching sessions, five modules, and a project in every module.

**You learn a concept, then you build it.** Only the first two sessions are mostly discussion;
from session 3 onwards every session is hands-on in a notebook.

## Modules

| Folder | Sessions | What you build |
|---|---|---|
| [`01-agent-foundations`](01-agent-foundations) | 1–3 | A research agent written from scratch in plain Python — no framework — then an evaluation harness for it |
| [`02-mcp`](02-mcp) | 4–5 | An MCP server (an "Engineering Incident Copilot") that any AI app can connect to, and a client that drives it |
| [`03-openai-agents-sdk`](03-openai-agents-sdk) | 6–7 | A travel concierge: multiple specialist agents, handoffs, guardrails, human approval, and a voice interface |
| [`04-langchain`](04-langchain) | 8–10 | A review-intelligence pipeline, a data-analyst agent with guardrails, and an agentic RAG investigator over docs + SQL + web |
| [`05-langgraph`](05-langgraph) | 11–13 | A support-ticket router that cannot skip its safety check, and a content team with human sign-off |
| [`slides`](slides) | — | The decks used in class |

From module 4 onwards the notebooks follow one running case study: **Nimbus**, a fictional
consumer-electronics company. The data, the questions and the problems carry across sessions.

## Setup

```bash
git clone https://github.com/divijbajaj7/ai-agents-course.git
cd ai-agents-course/01-agent-foundations

pip install -r requirements.txt
cp .env.example .env          # then put your own API key in .env

jupyter lab
```

Each module has its own `requirements.txt` and `.env.example`. Install per module — the
versions are pinned, because these libraries change quickly and the notebooks were tested
against those exact versions.

Every notebook also starts with a `%pip install` cell, so if you are on Google Colab you can
skip the setup above and just run the notebook top to bottom.

## What you need

- Python 3.10 or newer, and basic Python (functions, dicts, classes)
- An OpenAI API key. The notebooks use small, inexpensive models (`gpt-4.1-mini`)
- Prior exposure to LLMs, prompting and RAG — this course starts at agents

## How to use the notebooks

Every notebook is saved **with the outputs from a real run**, so you can read it before you
run anything and see exactly what each cell produced. When you run it yourself the wording
will differ, and sometimes the agent will take a different path — that is normal, and in
several notebooks it is the actual lesson.

Each notebook ends with exercises. Do them; the assessments assume you have.
