from pydantic import BaseModel, Field
from typing import Optional


class JobIn(BaseModel):
    name: str
    client_name: Optional[str] = None
    default_rate: float = Field(ge=0, default=0.0)
    active: bool = True


class JobUpdate(BaseModel):
    name: Optional[str] = None
    client_name: Optional[str] = None
    default_rate: Optional[float] = Field(default=None, ge=0)
    active: Optional[bool] = None


class JobOut(BaseModel):
    id: str
    name: str
    client_name: Optional[str] = None
    default_rate: float
    active: bool


class JobRateIn(BaseModel):
    employee_id: str
    rate: float = Field(ge=0)


class JobRateOut(BaseModel):
    id: str
    job_id: str
    employee_id: str
    rate: float

