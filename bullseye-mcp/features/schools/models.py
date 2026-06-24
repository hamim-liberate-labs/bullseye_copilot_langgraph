"""Typed MCP outputs for the Schools feature."""

from typing import Optional

from pydantic import BaseModel, Field


class SchoolContext(BaseModel):
    schools: list[dict] = Field(default_factory=list)
    active_school_id: Optional[int] = None
    count: int = 0
