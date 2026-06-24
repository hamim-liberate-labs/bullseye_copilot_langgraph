# Project Structure

Bullseye Copilot Backend — a FastAPI service that runs the Bullseye Copilot on
**LangGraph + LangChain v1**: a ReAct agent over the Bullseye data tools and a
per-chat file/bash/web workspace, streamed to the frontend over SSE. Layout
follows the `src/<package>/` convention.

```
langgraph-copilot/backend/
├── .env                              # secrets (gitignored) — seeded from repo .env
├── .env.example
├── .python-version
├── pyproject.toml                    # package metadata + deps (src layout)
├── requirements.txt                  # pip convenience mirror of pyproject deps
├── run.py                            # dev entrypoint (uvicorn on :8000, reload)
├── project_structure.md
│
├── src/bullseye_copilot/             # main application package
│   ├── __init__.py
│   ├── main.py                       # FastAPI app: CORS, router, frontend serving
│   │
│   ├── api/                          # HTTP API layer
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py             # aggregates the v1 endpoint routers
│   │       ├── endpoints/            # route handlers
│   │       │   ├── auth.py           # POST /api/login
│   │       │   ├── chat.py           # POST /api/chat, /api/chat/stream (SSE)
│   │       │   └── artifacts.py      # GET  /api/artifacts/{chat_id}/{thread}
│   │       └── schemas/              # request/response Pydantic models
│   │           ├── auth.py           # LoginRequest
│   │           └── chat.py           # ChatRequest
│   │
│   ├── core/                         # cross-cutting concerns
│   │   ├── config.py                 # env + paths (repo-bundled prompt/help/MCP)
│   │   └── logging_config.py
│   │
│   ├── llm/                          # LLM orchestration
│   │   ├── models.py                 # model alias + effort → ChatAnthropic
│   │   ├── prompts/
│   │   │   └── loader.py             # system-prompt load + {{placeholder}} fill
│   │   └── workflows/                # LangGraph agent workflows, one pkg per feature
│   │       └── copilot/              # the Bullseye Copilot ReAct agent
│   │           ├── agent.py          # create_agent() assembly + shared checkpointer
│   │           ├── middleware.py     # confirm-before-write (optional enforced HITL)
│   │           └── tools/
│   │               ├── bullseye_mcp.py  # bundled MCP server → LangChain tools
│   │               ├── files.py         # workspace-scoped Read/Write/Edit
│   │               ├── bash.py          # workspace-confined shell/python (*see note)
│   │               └── web.py           # web_fetch + optional Tavily web_search
│   │
│   ├── services/                     # external integrations
│   │   └── bullseye_auth.py          # Bullseye sign-in (JWT)
│   │
│   └── utils/                        # shared helpers
│       ├── streaming.py              # SSE framing, tool labels, <artifact> filter
│       └── workspace.py              # per-chat workspace, artifact marker + scan
│
└── tests/                            # test suite
    └── unit/
        └── test_file_scope.py        # file-tool path confinement (no API key needed)
```

## Layout overview

| Path | Purpose |
| --- | --- |
| `src/bullseye_copilot/main.py` | FastAPI application entrypoint |
| `src/bullseye_copilot/api/v1/` | HTTP routes (`endpoints/`) and request models (`schemas/`) |
| `src/bullseye_copilot/core/` | Config and logging |
| `src/bullseye_copilot/llm/models.py` | Model alias + effort → configured `ChatAnthropic` |
| `src/bullseye_copilot/llm/prompts/` | System-prompt loading utility |
| `src/bullseye_copilot/llm/workflows/copilot/` | The ReAct agent (`agent.py` + `tools/` + `middleware.py`) |
| `src/bullseye_copilot/services/` | External integrations (the Bullseye API) |
| `src/bullseye_copilot/utils/` | Streaming plumbing and the conversation workspace |
| `tests/` | `unit/` tier (extend with `integration/`, `e2e/` as coverage grows) |

## Request flow

```
frontend ──POST /api/chat/stream──▶ api/v1/endpoints/chat.py
                                       │ ensure workspace (utils/workspace)
                                       │ open MCP session (llm/.../tools/bullseye_mcp)
                                       │ build_agent (llm/.../copilot/agent)
                                       │   model  = llm/models
                                       │   prompt = llm/prompts/loader
                                       │   tools  = bullseye_mcp + files + bash + web
                                       ▼
                                  agent.astream_events
                                       │ → SSE events (utils/streaming): tool · text · result
                                       ▼
                                  frontend renders reply + artifact panel
```

> The two-id model is preserved: **`chat_id`** is the artifact workspace folder
> (file-tool isolation boundary); **`session_id`** is the LangGraph `thread_id`
> used by the checkpointer for conversation memory.
>
> *The Bash tool is `cwd`-confined but not yet an OS-level sandbox — see the
> security note in `tools/bash.py` and the top-level README.*
