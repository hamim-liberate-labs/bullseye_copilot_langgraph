# Bullseye Copilot

An AI assistant for the Bullseye for Schools platform, built on **LangGraph +
LangChain v1**. A FastAPI gateway runs a ReAct agent over the Bullseye data tools
and a per-chat file/bash/web workspace, and streams its output to a React frontend
over Server-Sent Events.

The repository is self-contained: the Bullseye MCP server, the system prompt, and
the help-center snapshot are all bundled here.

## Repository layout

```
langgraph-copilot/
├── backend/             FastAPI + LangGraph gateway (src/ layout)
│   ├── src/bullseye_copilot/
│   │   ├── main.py      FastAPI app: CORS, router, frontend serving
│   │   ├── api/v1/      routes (endpoints/) + request models (schemas/)
│   │   ├── core/        config + logging
│   │   ├── llm/         models, prompts/, workflows/copilot/ (agent + tools)
│   │   ├── services/    Bullseye sign-in
│   │   └── utils/       SSE streaming + per-chat workspace
│   ├── tests/           unit tests (path confinement — no API key needed)
│   └── run.py           development entry point
├── frontend/            React UI (Vite) — chat + artifact panel
├── bullseye-mcp/        bundled Bullseye MCP server (spawned over stdio)
├── prompts/             system prompt (loaded at startup)
└── knowledge/help/      help-center snapshot (surfaced to the agent as ./help)
```

See [`backend/project_structure.md`](backend/project_structure.md) for the full
module-by-module map.

## Architecture

| Concern | Implementation |
|---|---|
| Engine | `langchain.agents.create_agent` — a ReAct agent on LangGraph |
| Bullseye data tools | the bundled MCP server (`bullseye-mcp/`), spawned over stdio and adapted via `langchain-mcp-adapters` |
| File tools | Read/Write/Edit confined to the per-chat workspace |
| Bash / Python | runs with `cwd` set to the workspace (**not yet an OS-level sandbox — see [Security](#security)**) |
| Web | `web_fetch` plus an optional Tavily `web_search` |
| Confirm before write | system-prompt prose confirmation by default; optional enforced interrupt (`BULLSEYE_ENABLE_HITL=1`) |
| Conversation memory | LangGraph checkpointer keyed by `thread_id = session_id` |
| Streaming | `agent.astream_events` → SSE events (`tool`, `text`, `result`) |
| Per-user isolation | per-turn MCP subprocess env + per-request tool closures |

Each conversation carries two ids: **`chat_id`** is the artifact workspace folder
(the file-tool isolation boundary), and **`session_id`** is the LangGraph
`thread_id` used by the checkpointer for memory.

## Prerequisites

- Python 3.13+
- Node.js 18+
- An Anthropic and/or OpenAI API key (for the model[s] you select; the default
  model is GPT and the summarizer defaults to Haiku, so both keys are needed for
  the out-of-the-box configuration)
- Access to a Bullseye API instance

## Setup

### 1. Bullseye MCP server

The backend spawns this over stdio, so it needs its own virtualenv and `.env`:

```bash
cd bullseye-mcp
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then fill in the BULLSEYE_* values
```

### 2. Backend

```bash
cd backend
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then set ANTHROPIC_API_KEY / OPENAI_API_KEY and BULLSEYE_BASE_URL
python run.py                 # serves on http://127.0.0.1:8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                   # Vite proxies /api → 127.0.0.1:8000
```

## Configuration

All backend settings are environment variables, documented in
[`backend/.env.example`](backend/.env.example). Key groups:

- **Credentials** — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `BULLSEYE_BASE_URL`.
- **Agent defaults** — model, reasoning effort, turn limit, and the
  confirm-before-write mode (`BULLSEYE_ENABLE_HITL`).
- **Cost controls** — context editing, history summarization, and artifact-rewrite
  limits.
- **Observability** — set the `LANGSMITH_*` variables to enable LangChain tracing
  to your own LangSmith project.

## Tests

```bash
cd backend
pytest                        # or: python tests/unit/test_file_scope.py
```

The file-tool path-confinement suite requires no API key.

## Security

> **The Bash tool is not yet sandboxed at the OS level.** It runs commands with
> `cwd` set to the per-chat workspace, but a hostile command could still read
> outside the workspace or reach the network. This **must be hardened before any
> production deployment.**

Recommended hardening (Linux): run each command inside `bubblewrap` or `nsjail`
with no network namespace and a read-only bind of only the workspace and `./help`,
or run the backend in a locked-down container. File **tool** access is already
confined (enforced by `tests/unit/test_file_scope.py`); the open gap is arbitrary
shell execution.

## Production considerations

- **Persistence.** Conversation memory uses an in-process `MemorySaver`, so
  threads are lost on restart. Swap in `langgraph-checkpoint-sqlite` or
  `-postgres` for durable history.
- **Bash sandbox.** Harden shell execution before deploying — see
  [Security](#security).
- **Enforced confirm-before-write.** `BULLSEYE_ENABLE_HITL=1` adds a hard
  interrupt before `next_steps_write`. It requires a frontend that can resume an
  interrupted thread (`Command(resume=…)`); the current frontend cannot, so it is
  off by default.
