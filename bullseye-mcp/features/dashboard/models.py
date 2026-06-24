"""Typed MCP output for the Dashboard feature."""

from pydantic import BaseModel, Field


class Dashboard(BaseModel):
    active_goal_data: dict = Field(default_factory=dict)
    next_step_list: list[dict] = Field(default_factory=list)
    recent_session_data: list[dict] = Field(default_factory=list)
    current_school_specific_data: dict = Field(default_factory=dict)
