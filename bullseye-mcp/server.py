"""
Bullseye Copilot — MCP server entry point.

The tool layer for the Bullseye Copilot: 12 tools (auth bootstrap, read GETs,
write POST/PATCH/DELETEs, plus a local set_active_school). The gateway spawns this
server over stdio and adapts its tools into LangChain.

Layout:
  core/                shared infra: app (config + FastMCP), session (HTTP I/O), helpers
  features/<name>/     one package per Bullseye area:
    endpoints.py       HTTP/domain calls (take a BullseyeSession)
    tools.py           @mcp.tool wrappers that register on `mcp`
    models.py          Pydantic output models (typed MCP schema)

Add a feature: create features/<name>/, then import its `tools` module below so
its @mcp.tool functions register. See README.md for cross-cutting behaviour.
"""

from core.app import mcp

# Import each feature's tools module so its @mcp.tool functions register on `mcp`.
# (Imported for side effects; the names themselves are not used here.)
from features.authentication import tools as _authentication_tools          # noqa: F401
from features.schools import tools as _schools_tools                        # noqa: F401
from features.my_sessions import tools as _my_sessions_tools                # noqa: F401
from features.individual_assessments import tools as _individual_assessments_tools  # noqa: F401
from features.people import tools as _people_tools                          # noqa: F401
from features.next_steps import tools as _next_steps_tools                  # noqa: F401
from features.dashboard import tools as _dashboard_tools                    # noqa: F401


if __name__ == "__main__":
    mcp.run()
