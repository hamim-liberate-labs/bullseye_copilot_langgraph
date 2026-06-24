"""Typed MCP outputs for the People feature.

The paginated learner record lists (sessions / objectives / notes / checklist
items) are served by one tool, `get_person_records`, which returns a dict (it
offloads in gateway mode), so they have no dedicated model here."""

from typing import Optional

from pydantic import BaseModel, Field


class ActiveGoal(BaseModel):
    person_id: int
    goal: Optional[str] = None          # cleaned text
    goal_html: Optional[str] = None      # raw HTML for rendering
    objectives: list[dict] = Field(default_factory=list)


class GoalHistory(BaseModel):
    goals: list[dict] = Field(default_factory=list)


class ObjectiveDetail(BaseModel):
    person_id: int
    objective_id: int
    objective: dict = Field(default_factory=dict)
    scores: list[dict] = Field(default_factory=list)
    learning_resources: list[dict] = Field(default_factory=list)
    score_band: Optional[int] = None
    pagination: dict = Field(default_factory=dict)
