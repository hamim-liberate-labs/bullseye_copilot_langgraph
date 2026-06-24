# Bullseye Copilot — LangGraph build

A re-implementation of the Bullseye Copilot on **LangGraph + LangChain v1**,
replacing the Anthropic **Claude Agent SDK** engine while keeping the user
experience, the HTTP contract, and the frontend **identical**. This is the
migration described in [`docs/langgraph-migration-plan.md`](docs/langgraph-migration-plan.md).

This repo is **self-contained**: the Bullseye MCP server, the system prompt, and
the help-center snapshot are bundled here (they originated in the parent
`bullseye-copilot-exp` repo and are kept in sync as needed).

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
├── frontend/                         the existing React UI, copied unchanged
├── bullseye-mcp/                     bundled Bullseye MCP server (spawned over stdio)
├── prompts/                          system prompt (loaded at startup)
├── knowledge/help/                   help-center snapshot (surfaced as ./help)
└── docs/                             migration plan
```

See [`backend/project_structure.md`](backend/project_structure.md) for the full
module-by-module map.

## How it maps to the old build

| Concern | Agent SDK build | This build |
|---|---|---|
| Engine | `claude_agent_sdk.query()` | `langchain.agents.create_agent` (ReAct, on LangGraph) |
| Bullseye data tools | MCP server over stdio | **Same MCP server**, adapted via `langchain-mcp-adapters` (Phase 2) |
| File tools | SDK built-ins, path-scoped | `llm/workflows/copilot/tools/files.py`, confined to the workspace (Phase 4) |
| Bash / Python | SDK sandbox (offline, confined) | `llm/workflows/copilot/tools/bash.py` — confined `cwd`, **sandbox hardening is Phase 5, see below** |
| Confirm before write | Prompt instruction | Same prompt instruction (default); optional enforced interrupt (Phase 6) |
| Conversation memory | SDK `resume=session_id` | LangGraph checkpointer keyed by `thread_id = session_id` (Phase 7) |
| Streaming | SDK `StreamEvent`s → SSE | `agent.astream_events` → the **same** SSE events (Phase 9) |
| Per-user isolation | per-request MCP subprocess env | per-turn MCP subprocess env + per-request tool closures (Phase 8) |
| Frontend | `frontend/` | byte-for-byte copy — the wire contract is unchanged |

The two-id model is preserved: **`chat_id`** is the artifact workspace folder,
**`session_id`** is the LangGraph `thread_id` for memory.

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

## ⚠️ Security status — the Bash sandbox (Phase 5)

The Agent SDK gave us an OS-level sandbox for free: no network, writes confined
to the workspace, auto-approved. `llm/workflows/copilot/tools/bash.py` currently runs commands
with `cwd` set to the workspace but does **not** reproduce those guarantees — a
hostile command could read outside the workspace or reach the network. Per the
migration plan this is the single hardest part and **must be hardened before any
real deployment** (e.g. `bubblewrap`/`nsjail` with no network namespace and a
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
- **Enforced confirm-before-write (Phase 6):** set `BULLSEYE_ENABLE_HITL=1` to
  add a hard interrupt before `next_steps_write` — but the frontend must first
  learn to resume an interrupted thread (`Command(resume=…)`). Off by default so
  behaviour matches today's prose-confirmation flow.
