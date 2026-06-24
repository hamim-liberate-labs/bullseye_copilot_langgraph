# Architecture & conventions

How this server is structured and the rules for adding to it. For the user-facing
overview (setup, tool list, behaviour) see `README.md`.

## Layers

```
core/        shared infra, nothing feature-specific
  app.py         config (BASE/TIMEOUT/WORKDIR/OFFLOAD_MIN_BYTES), logger, the FastMCP instance
  session.py     BullseyeSession — all HTTP I/O (get / write / safe_get) + the default session()
  helpers.py     strip_html / clean_params / as_list / page_of / shape_of / offload
  annotations.py READ_ONLY / MUTATING / LOCAL_STATE tool-annotation presets
features/<name>/
  endpoints.py   HTTP/domain calls — async funcs taking a BullseyeSession, return plain dicts
  tools.py       @mcp.tool wrappers (registered on `mcp`); thin, no business logic
  models.py      Pydantic output models (typed MCP schema) — omit if the tool returns a dict
```

Dependency direction: `features → core`; within core, `session/helpers → app` (no cycles).

## Adding a feature

1. Create `features/<name>/` with `endpoints.py` + `tools.py` (+ `models.py` if typed).
2. Import its `tools` module in `server.py` so its `@mcp.tool` functions register.
3. Follow the conventions below.

## Tool-design conventions

- **Consolidate, don't 1:1-map endpoints.** Wrapping every REST endpoint as its own
  tool bloats the context and degrades selection. Group cohesive operations behind one
  tool with an `action` / `record_type` parameter (see `get_person_records`, which
  covers 4 endpoints). Use `typing.Literal[...]` for those params so they render as a
  schema enum. **But** keep reads that return genuinely different shapes as separate
  tools — don't merge into a mega-tool with a sprawling param union.
- **Mutations consolidate best.** Many small PATCH/POST endpoints on one resource (e.g.
  the individual-assessment `update_*` set) should collapse into a few field/action-
  parameterised write tools.
- **Tags:** every tool gets `tags={"<feature>", "read"|"write"}` (auth/state tools just
  the feature tag). Enables tag-based filtering / progressive disclosure as we scale.
- **Annotations:** use the `core.annotations` presets — `READ_ONLY` for GETs, `MUTATING`
  for POST/PATCH that change Bullseye data, `LOCAL_STATE` for session-only changes.
- **Bulk results use `offload`.** List/detail tools that can return many records call
  `offload(name, payload, summary)`; it returns counts + pagination + a `preview` + an
  auto-derived `schema` (the payload's shape) in gateway mode, and inlines small
  payloads. Keeps large data out of the model's context.
- **HTML hygiene at the boundary.** Any goal/notes HTML from the API is cleaned with
  `strip_html` into a `*_text` field, with the raw value kept alongside.
- **Learner context for person/people tools.** `person_id` is the LEARNER profile id (the
  observed/coached person, == `student_id`), not the coach. Say so in the tool docstring
  and frame results as data ABOUT the learner (sessions conducted ON them, notes written
  ABOUT them). The docstring is what the model reads.
- **Keep tool docstrings informative** — they are the model-facing descriptions. Trim
  module/implementation comments, not these.

## Scaling roadmap

- **Now (≤ ~30 tools):** consolidation + tags + annotations (done).
- **~30–40 tools:** progressive disclosure — expose a lean default tool set and gate
  feature groups behind tags (`include_tags`/`exclude_tags`), or add a `search_tools`
  meta-tool. (Cursor and some clients hard-cap at 40 tools.)
- **Agent SDK port:** code execution with MCP — expose `features/*/endpoints.py` as an
  importable code API + a code-execution tool instead of N MCP tools; keep `offload` as
  the results pattern. The endpoints-as-plain-functions design already enables this.
