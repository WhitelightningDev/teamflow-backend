from pydantic import BaseModel, Field


class AcceptInviteIn(BaseModel):
    token: str = Field(..., min_length=10)
    password: str = Field(..., min_length=6)

