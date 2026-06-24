"""
`BullseyeSession` — all HTTP I/O for one logical user session, plus the
process-default session lifecycle.

Pure transport: auth state, the pooled httpx client, and the verbs features call
(`get`, `write`, `safe_get`). Domain parsing lives in feature `endpoints.py`. The
stdio harness uses one default session (`session()`); under the Agent SDK, build
one per connection so user JWTs never cross sessions.
"""

import os
import time
from typing import Any, Optional

import httpx
from fastmcp.exceptions import ToolError

from core.app import BASE, TIMEOUT, log
from core.helpers import clean_params

# Endpoints that take no school_id (and must not have one injected).
_NEEDS_SCHOOL_HINT = (
    "needs a school_id — call get_school_context first (or pass school_id explicitly)."
)


class BullseyeSession:
    """Auth state + shared HTTP client for one logical user session."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        self.token: Optional[str] = None
        self.school_id: Optional[int] = None
        self._email: Optional[str] = None
        self._password: Optional[str] = None

    # -- auth --------------------------------------------------------------
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def use_token(self, token: str) -> None:
        """Adopt a pre-issued JWT (per-user passthrough). No password stored, so a
        401 surfaces instead of triggering a re-auth."""
        self.token = token.replace("Bearer ", "").strip()
        self._email = self._password = None

    def _can_reauth(self) -> bool:
        return bool(self._email and self._password)

    async def authenticate(self, email: Optional[str] = None,
                           password: Optional[str] = None) -> dict:
        email = email or os.getenv("BULLSEYE_EMAIL")
        password = password or os.getenv("BULLSEYE_PASSWORD")
        if not (email and password):
            raise ToolError("No credentials: set BULLSEYE_EMAIL/PASSWORD or pass them in.")

        t0 = time.perf_counter()
        r = await self._client.post(
            "/api/v1/users/sign_in",
            json={"user": {"email": email, "password": password}},
        )
        log.info("POST /users/sign_in -> %s (%.0f ms)", r.status_code, (time.perf_counter() - t0) * 1000)
        if r.status_code >= 400:
            raise ToolError(f"Sign-in failed: {r.status_code} {r.text[:200]}")

        # JWT is in the Authorization response *header*, not the body.
        self.token = r.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if not self.token:
            raise ToolError("Sign-in returned no Authorization header — cannot continue.")
        self._email, self._password = email, password
        return r.json()

    # -- core request verbs ------------------------------------------------
    async def get(self, path: str, *, params: Optional[dict] = None,
                  needs_school: bool = True, _retried: bool = False) -> Any:
        """GET an endpoint, returning the unwrapped `data`. Injects school_id when
        required; raises ToolError on HTTP error; re-auths once on 401."""
        params = dict(params or {})
        if needs_school and "school_id" not in params:
            if self.school_id is None:
                raise ToolError(f"{path} {_NEEDS_SCHOOL_HINT}")
            params["school_id"] = self.school_id

        t0 = time.perf_counter()
        r = await self._client.get(path, params=params, headers=self._headers())
        log.info("GET %s school=%s -> %s (%.0f ms)",
                 path, params.get("school_id"), r.status_code, (time.perf_counter() - t0) * 1000)

        if r.status_code == 401 and not _retried and self._can_reauth():
            log.warning("401 on %s — re-authenticating and retrying once", path)
            await self.authenticate(self._email, self._password)
            return await self.get(path, params=params, needs_school=False, _retried=True)
        if r.status_code >= 400:
            raise ToolError(f"Bullseye GET {path} failed: {r.status_code} {r.text[:200]}")

        data = r.json().get("data", {})
        return data if data is not None else {}

    async def safe_get(self, path: str, *, params: Optional[dict] = None) -> Any:
        """GET an optional sub-resource that may legitimately 403/404 (e.g. draft
        comments); degrade to {} instead of failing the whole tool."""
        try:
            return await self.get(path, params=params)
        except ToolError as e:
            log.info("optional %s skipped (%s)", path, str(e)[:80])
            return {}

    async def write(self, method: str, path: str, *,
                    json_body: Optional[dict] = None,
                    params: Optional[dict] = None,
                    needs_school: bool = True, _retried: bool = False) -> dict:
        """POST/PATCH an endpoint, returning the full {success, message, data} body
        (writes carry meaning in message/success). Injects school_id into the JSON
        body (where these endpoints expect it); raises on error; re-auths once on 401."""
        body = dict(json_body or {})
        if needs_school and "school_id" not in body:
            if self.school_id is None:
                raise ToolError(f"{path} {_NEEDS_SCHOOL_HINT}")
            body["school_id"] = self.school_id

        t0 = time.perf_counter()
        r = await self._client.request(method, path, json=body,
                                       params=clean_params(params),
                                       headers=self._headers())
        log.info("%s %s school=%s -> %s (%.0f ms)", method, path,
                 body.get("school_id"), r.status_code, (time.perf_counter() - t0) * 1000)

        if r.status_code == 401 and not _retried and self._can_reauth():
            log.warning("401 on %s — re-authenticating and retrying once", path)
            await self.authenticate(self._email, self._password)
            return await self.write(method, path, json_body=body, params=params,
                                    needs_school=False, _retried=True)
        if r.status_code >= 400:
            raise ToolError(f"Bullseye {method} {path} failed: {r.status_code} {r.text[:200]}")

        try:
            return r.json()
        except ValueError:
            return {}


# ── Session lifecycle ───────────────────────────────────────────────────────

_session: Optional[BullseyeSession] = None


def session() -> BullseyeSession:
    """Process-default session (lazy shared client). Under the Agent SDK, swap for
    a per-connection lookup so each user gets an isolated session + JWT."""
    global _session
    if _session is None:
        client = httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT)
        _session = BullseyeSession(client)
        # Gateway injects a pre-issued JWT and the user's current school at spawn
        # time; adopt them so the first tool call works without interactive setup.
        env_token = os.getenv("BULLSEYE_TOKEN")
        if env_token:
            _session.use_token(env_token)
        env_school = os.getenv("BULLSEYE_SCHOOL_ID")
        if env_school:
            try:
                _session.school_id = int(env_school)
            except ValueError:
                log.warning("ignoring non-integer BULLSEYE_SCHOOL_ID=%r", env_school)
    return _session
