"""Bullseye sign-in. Pure transport: exchange email/password for the JWT Bullseye
returns in the Authorization header, and fold the active school into the user
object so it round-trips per turn."""

import logging

import httpx
from fastapi import HTTPException

from bullseye_copilot.core.config import BULLSEYE_BASE_URL

log = logging.getLogger("copilot.auth")


async def login(email: str, password: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BULLSEYE_BASE_URL}/api/v1/users/sign_in",
            json={"user": {"email": email, "password": password}},
        )

    if r.status_code >= 400:
        log.warning("login failed · email=%s status=%s", email, r.status_code)
        raise HTTPException(status_code=401, detail="Bullseye sign-in failed")

    # Bullseye returns the JWT in the Authorization response header.
    token = r.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        log.error("login: no token in Bullseye response headers")
        raise HTTPException(status_code=502, detail="no token in Bullseye response")

    data = r.json().get("data", {})
    user = data.get("user", {})
    # Bullseye returns the active school as a sibling of `user`; fold it in so it
    # round-trips back to us each chat turn and we can scope MCP calls to it.
    current_school = data.get("current_school")
    if current_school:
        user["current_school"] = current_school
    log.info(
        "login ok · user=%s (id=%s, admin=%s, school=%s)",
        user.get("full_name"), user.get("id"), user.get("admin"),
        (current_school or {}).get("id"),
    )
    return {"authenticated": True, "token": token, "user": user}
