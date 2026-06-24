"""Typed MCP outputs for the Authentication feature."""

from typing import Optional

from pydantic import BaseModel, Field


class AuthResult(BaseModel):
    token_cached: bool
    user: dict = Field(default_factory=dict)
    note: Optional[str] = None
