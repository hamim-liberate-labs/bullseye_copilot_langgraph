"""Aggregates the v1 endpoint routers. Routes keep their full `/api/...` paths
(no prefix) to match the existing frontend contract exactly."""

from fastapi import APIRouter

from bullseye_copilot.api.v1.endpoints import artifacts, auth, chat

api_router = APIRouter()
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(artifacts.router, tags=["artifacts"])
