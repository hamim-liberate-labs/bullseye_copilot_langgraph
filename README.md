# Bullseye Copilot — LangGraph build

The Bullseye Copilot built on **LangGraph + LangChain v1**: a FastAPI gateway that
runs a ReAct agent over the Bullseye data tools plus a per-chat file/bash/web
workspace, and streams its output to a React frontend over SSE.

This repo is **self-contained**: the Bullseye MCP server, the system prompt, and
the help-center snapshot are all bundled here.

```
langgraph-copilot/
├── backend/                          FastAPI + LangGraph gateway (src/ layout)
│   ├── src/bullseye_copilot/
│   │   ├── main.py                   FastAPI app: CORS, router, frontend serving
│   │   ├── api/v1/                   routes (endpoints/) + request models (schemas/)
│   │   ├── core/                     config + logging
│   │   ├── llm/                      models, prompts/, workflows/copilot/ (agent + tools)
│   │   ├── services/                 Bullseye sign-in
│   │   └── utils/                    SSE streaming + per-chat workspace
│   ├── tests/unit/                   path-confinement test (no API key needed)
│   ├── run.py                        dev entry point (uvicorn on :8000)
│   ├── pyproject.toml / requirements.txt
│   └── project_structure.md          detailed module map
├── frontend/                         React UI (Vite) — chat + artifact panel
├── bullseye-mcp/                     bundled Bullseye MCP server (spawned over stdio)
├── prompts/                          system prompt (loaded at startup)
└── knowledge/help/                   help-center snapshot (surfaced as ./help)
```

See [`backend/project_structure.md`](backend/project_structure.md) for the full
module-by-module map.

## Architecture

| Concern | How it works |
|---|---|
| Engine | `langchain.agents.create_agent` — a ReAct agent running on LangGraph |
| Bullseye data tools | the bundled MCP server (`bullseye-mcp/`), spawned over stdio and adapted via `langchain-mcp-adapters` |
| File tools | `llm/workflows/copilot/tools/files.py` — Read/Write/Edit confined to the per-chat workspace |
| Bash / Python | `llm/workflows/copilot/tools/bash.py` — runs with `cwd` set to the workspace (**not yet an OS-level sandbox — see below**) |
| Web | `llm/workflows/copilot/tools/web.py` — `web_fetch` + optional Tavily `web_search` |
| Confirm before write | enforced via the system prompt (prose confirmation); an optional hard interrupt is available (`BULLSEYE_ENABLE_HITL=1`) |
| Conversation memory | LangGraph checkpointer keyed by `thread_id = session_id` |
| Streaming | `agent.astream_events` → SSE events (`tool` · `text` · `result`) |
| Per-user isolation | per-turn MCP subprocess env + per-request tool closures |

Two ids per conversation: **`chat_id`** is the artifact workspace folder
(file-tool isolation boundary), **`session_id`** is the LangGraph `thread_id`
used by the checkpointer for memory.

## Running it (dev)

Prerequisites: the bundled **`bullseye-mcp/`** needs its own venv (the backend
spawns it over stdio) and its own `.env` (Bullseye sign-in for the data tools).

**Bullseye MCP server** (one-time setup — the backend launches it for you)
```bash
cd bullseye-mcp
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                            # then fill in BULLSEYE_* values
```

**Backend**
```bash
cd langgraph-copilot/backend
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt                 # or: pip install -e .
# .env is already seeded from the repo .env (ANTHROPIC_API_KEY, BULLSEYE_BASE_URL,
# LangSmith). Edit it if you need to change anything.
python run.py                                   # serves on http://127.0.0.1:8000
```

**Frontend**
```bash
cd langgraph-copilot/frontend
npm install
npm run dev                                     # Vite proxies /api → 127.0.0.1:8000
```

**Tests** (path confinement — no API key required)
```bash
cd langgraph-copilot/backend
python tests/unit/test_file_scope.py            # or: pytest
```

## ⚠️ Security status — the Bash sandbox

`llm/workflows/copilot/tools/bash.py` runs commands with `cwd` set to the
workspace, but does **not** confine them at the OS level — a hostile command
could read outside the workspace or reach the network. This is the single
hardest part of the tool layer and **must be hardened before any real
deployment** (e.g. `bubblewrap`/`nsjail` with no network namespace and a
read-only bind of just the workspace + `./help`, or a locked-down container).
File **tool** access is already confined (see `tests/unit/test_file_scope.py`); the
gap is arbitrary shell execution.

## Notes / TODO

- **Tracing:** LangSmith is **on by default** — `backend/.env` sets
  `LANGSMITH_TRACING=true` + the API key, and LangChain auto-traces every agent
  run to the `bullseye-local-hamim` project. No code involved; set
  `LANGSMITH_TRACING=false` (or remove the key) to disable.
- **Persistence:** `MemorySaver` keeps conversation memory in-process; threads
  are lost on restart. Swap for `langgraph-checkpoint-sqlite`/`-postgres` for
  production.
- **Cost reporting:** `cost_usd` is returned as `null` (the frontend tolerates
  it). Wire up usage→price accounting if needed.
- **Enforced confirm-before-write:** set `BULLSEYE_ENABLE_HITL=1` to add a hard
  interrupt before `next_steps_write` — but the frontend must first learn to
  resume an interrupted thread (`Command(resume=…)`). Off by default so behaviour
  matches the prose-confirmation flow.
