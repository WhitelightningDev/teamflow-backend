from pydantic import BaseModel


class Team(BaseModel):
    id: int
    name: str
    description: str | None = None


class TeamCreate(BaseModel):
    name: str
    description: str | None = None

