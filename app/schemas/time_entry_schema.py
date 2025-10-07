from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ManualTimeEntryIn(BaseModel):
    job_id: str
    start_ts: datetime
    end_ts: datetime
    break_minutes: int = Field(default=0, ge=0)
    note: Optional[str] = None


class ManualTimeEntryUpdate(BaseModel):
    start_ts: Optional[datetime] = None
    end_ts: Optional[datetime] = None
    break_minutes: Optional[int] = Field(default=None, ge=0)
    note: Optional[str] = None


class ClockInPayload(BaseModel):
    job_id: str
    note: Optional[str] = None


class TimeEntryOut(BaseModel):
    id: str
    job_id: str
    employee_id: str
    start_ts: Optional[datetime] = None
    end_ts: Optional[datetime] = None
    break_minutes: int
    is_active: bool
    on_break: bool
    duration_minutes: Optional[int] = None
    note: Optional[str] = None
    rate: Optional[float] = None
    amount: Optional[float] = None

