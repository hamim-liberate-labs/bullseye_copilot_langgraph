"""Auth endpoint: exchange Bullseye credentials for a JWT + user object."""

from fastapi import APIRouter

from bullseye_copilot.api.v1.schemas.auth import LoginRequest
from bullseye_copilot.services import bullseye_auth

router = APIRouter()


@router.post("/api/login")
async def login(body: LoginRequest) -> dict:
    return await bullseye_auth.login(body.email, body.password)
