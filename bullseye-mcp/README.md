# Bullseye Copilot — MCP Server

FastMCP server exposing the Bullseye Copilot tool layer: **12 tools** (1 auth
bootstrap, 8 read GETs, the 2-tool `next_steps` read/write pair that dispatches
8 next-step endpoints, plus a local `set_active_school`). This is the layer that
carries forward into the Anthropic Agent SDK — only the transport changes.

The server is organised into a shared `core/` (transport + infra) and one package
per Bullseye feature under `features/`, so it scales as more of the API is wired in.

## Layout

```
bullseye-mcp/
  server.py                  entry point — imports each feature's tools, runs mcp
  core/
    app.py                   config (BASE/TIMEOUT/WORKDIR), logger, the FastMCP instance
    session.py               BullseyeSession (all HTTP I/O) + the default session()
    helpers.py               strip_html / clean_params / as_list / page_of / offload
  features/<feature>/
    endpoints.py             HTTP/domain calls (take a BullseyeSession)
    tools.py                 @mcp.tool wrappers (registered on `mcp`)
    models.py                Pydantic output models (typed MCP schema)
  requirements.txt           fastmcp, httpx, python-dotenv, pydantic
  .env.example               template for the required + optional env vars
```

Features: `authentication`, `schools`, `my_sessions`, `individual_assessments`,
`people`, `next_steps`, `dashboard`.

**Add a feature:** create `features/<name>/` with `endpoints.py` + `tools.py`
(+ `models.py`), then import its `tools` module in `server.py` so its `@mcp.tool`
functions register.

## Setup

`requirements.txt` is the single source of dependencies. Two ways to run:

- **Claude Code** launches it via `uv` (see `.mcp.json`) — no manual venv needed;
  `uv` builds a cached env from `requirements.txt` on first use.
- **The gateway** (`main.py`) launches it from `bullseye-mcp/.venv`, so for that
  path create the venv once:

  ```bash
  python -m venv .venv
  .venv/Scripts/python.exe -m pip install -r requirements.txt   # bin/python on macOS/Linux
  ```

```bash
cp .env.example .env   # then fill in credentials
```

`.env` is loaded from this folder regardless of the launcher's cwd. See
`.env.example` for the optional vars (`BULLSEYE_TIMEOUT`, `BULLSEYE_LOG_LEVEL`,
`BULLSEYE_TOKEN`, `BULLSEYE_SCHOOL_ID`, `BULLSEYE_WORKDIR`).

## Tools → endpoints (by feature)

Each `features/<name>/` package owns its tools (`tools.py`) and the HTTP/domain
calls behind them (`endpoints.py`). Below, tools are grouped by that package, in
the order `server.py` registers them. **12 tools total** across 7 features.

### `authentication` — bootstrap

| Tool | Kind | Endpoint |
|---|---|---|
| `get_auth_token` | mutating | `POST /api/v1/users/sign_in` (or adopt a pre-issued JWT) |

### `schools` — school context

| Tool | Kind | Endpoint |
|---|---|---|
| `get_school_context` | read | `GET /api/v1/schools` |
| `set_active_school` | local state | — (sets `session.school_id`; no HTTP call) |

### `my_sessions` — the user's own sessions

| Tool | Kind | Endpoint |
|---|---|---|
| `list_sessions` | read | `GET /api/v1/my_sessions` |

### `individual_assessments` — one session in full

| Tool | Kind | Endpoint |
|---|---|---|
| `get_session` | read | `GET /api/v1/individual_assessments/{id}` + `…/comments` (concurrent) |

### `people` — the learner profile (data ABOUT the learner)

| Tool | Kind | Endpoint |
|---|---|---|
| `get_active_goal` | read | `GET /api/v1/people/{id}/get_active_goal` |
| `get_goal_history` | read | `GET /api/v1/people/{id}/active_goal_history` |
| `get_person_records` | read | `GET /api/v1/people/{id}/{sessions\|objectives\|notes\|checklist_items}` |
| `get_objective_detail` | read | `GET /api/v1/people/{id}/objectives/{objective_id}` |

### `next_steps` — action items

Two action-dispatching tools cover all eight endpoints — split read from write so
the read-only vs destructive annotation stays honest. The agent picks the `action`.

| Tool | Kind | `action` → Endpoint |
|---|---|---|
| `next_steps_read` | read | `get` → `GET /api/v1/next_steps/{id}` |
| | | `new_form` → `GET /api/v1/next_steps/new` |
| | | `edit_data` → `GET /api/v1/next_steps/{id}/edit` |
| | | `list_completed` → `GET /api/v1/next_steps/completed_next_steps_history` |
| `next_steps_write` | write (destructive) | `create` → `POST /api/v1/next_steps` |
| | | `update` → `PATCH /api/v1/next_steps/{id}` |
| | | `delete` → `DELETE /api/v1/next_steps/{id}` |
| | | `toggle_completion` → `PATCH /api/v1/next_steps/{id}/completion_toggle` |

### `dashboard` — staff home overview

| Tool | Kind | Endpoint |
|---|---|---|
| `get_dashboard` | read | `GET /api/v1/dashboards` |

## Cross-cutting behaviour (all in `core/`)

- **State is encapsulated in `BullseyeSession`, not globals.** The stdio harness
  uses one default session; under the SDK build one per connection (see
  `core.session.session()`) so user JWTs never cross sessions.
- **One pooled httpx client** with an explicit timeout.
- **Errors surface as `ToolError`** — every call checks status; a 401 on a
  password session re-authenticates once and retries (self-healing JWT). Token-
  passthrough sessions surface the 401 instead (no stored secret).
- **`school_id` is injected** into every call except sign-in / schools — query
  param for GETs, JSON body for writes.
- **HTML hygiene at the boundary** — goal text and notes are stripped to clean
  `*_text`, raw HTML kept alongside for rendering.
- **Typed structured output** — most tools return Pydantic models, so MCP clients
  get an output schema; direct callers still receive plain dicts. The `next_steps`
  dispatchers are the exception: their shape varies by `action`, so they return
  plain dicts.
- **Gateway mode** (`BULLSEYE_WORKDIR` set) — bulk tools (`list_sessions`,
  `get_session`) offload full payloads to `data/*.json` and return a compact view:
  counts, pagination, a curated `preview`, and an auto-derived **`schema`** (the
  payload's shape — every field, arrays collapsed to one item + length) so the
  agent can query the file for just what it needs instead of reading it whole.
  Small payloads (< `BULLSEYE_OFFLOAD_MIN_BYTES`, default 4096) stay inline
  (`helpers.offload` / `helpers.shape_of`).
- **Structured logging** of method, path, school, status, and latency per call.

## Use inside Claude Code

The root `.mcp.json` registers this server. It launches via
`uv run --no-project --with-requirements bullseye-mcp/requirements.txt
bullseye-mcp/server.py` — portable, no hardcoded paths, deps resolved from
`requirements.txt` (requires `uv` on PATH):

1. Restart Claude Code from the project root
2. Approve: *"New MCP server found in `.mcp.json`: bullseye"*
3. `/mcp` should list `bullseye` connected with 12 tools
4. Smoke-test: *"Call get_auth_token, then get_school_context"*

## Endpoint notes / gotchas

- **`people/{id}` is the learner profile** — the observed/coached person (assessee),
  not the coach. `person_id` == `student_id` (the dashboard's
  `current_staff.student_id` is the signed-in staff member's own learner id, for
  self-queries). So `get_person_records(person_id, "sessions")` returns sessions
  conducted ON that learner, `record_type="notes"` returns notes written ABOUT
  them — never what they authored as an observer.
- JWT is in the **`Authorization` response header**, not the JSON body.
- `school_id` is required on nearly every call or it 401s.
- Draft sessions return empty comments (degraded to `[]`).
- Goal text / notes come back as **HTML** — cleaned at the boundary, raw kept.
- `/my_sessions` and the person-scoped lists are **paginated** (~20/page) — page
  through `pagination.total_pages`; narrow large pulls with a date window or
  `search_value`.
- `completed_next_steps_history` **requires** `completion_location_id` (the
  session id) plus `completion_location_type` (defaults to `Session`) — a bare
  call 400s.

## Validation status

- **Live-validated ✅:** auth (JWT from header), schools, goal history, session
  detail + comments.
- **Mock-validated, live-validation pending ⏳:** `/my_sessions`, the person-scoped
  endpoints, `/dashboards`, `/people/{id}/get_active_goal`, and the 3 next-step
  writes. Shapes are parsed defensively (`as_list`, key fallbacks); confirm
  against the live API before relying on these.
