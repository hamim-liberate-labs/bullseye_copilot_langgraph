"""
Shared MCP tool-annotation presets — behavioural hints clients/agents use to
reason about a tool (e.g. is it safe to retry, does it mutate, does it hit an
external system). Reused across features so the signalling stays consistent.
"""

from fastmcp.tools.tool import ToolAnnotations

# Read-only GET against the Bullseye API.
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

# Creates/changes Bullseye data via POST/PATCH (non-destructive, non-idempotent).
MUTATING = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                           idempotentHint=False, openWorldHint=True)

# A write surface that can DELETE (irreversible) alongside create/update — flag
# destructive so clients gate/double-confirm, and non-idempotent since it can create.
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                              idempotentHint=False, openWorldHint=True)

# Local session-state change only — no external call (e.g. set_active_school).
LOCAL_STATE = ToolAnnotations(readOnlyHint=False, idempotentHint=True,
                              openWorldHint=False)
