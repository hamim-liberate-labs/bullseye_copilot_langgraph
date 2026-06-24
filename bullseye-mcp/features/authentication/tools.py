"""Authentication tool. The auth machinery (sign-in, token cache, 401 re-auth)
lives on BullseyeSession in core.session; this is just the thin wrapper."""

from core.app import mcp
from core.annotations import MUTATING
from core.session import session

from .models import AuthResult


@mcp.tool(tags={"authentication"}, annotations=MUTATING)
async def get_auth_token(email: str = None, password: str = None,
                         token: str = None) -> AuthResult:
    """
    Sign in to Bullseye and cache the JWT for all subsequent tool calls. Call this
    first. Pass `token` to adopt a pre-issued JWT (per-user passthrough) instead
    of signing in with a password.
    """
    s = session()
    if token:
        s.use_token(token)
        return {"token_cached": True, "user": {}, "note": "Using supplied token"}
    data = await s.authenticate(email, password)
    return {"token_cached": bool(s.token), "user": data.get("data", {}).get("user", {})}
