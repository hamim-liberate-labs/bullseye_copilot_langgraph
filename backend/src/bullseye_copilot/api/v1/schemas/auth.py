"""Auth request models."""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str
