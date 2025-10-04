from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel


class LeaveIn(BaseModel):
    employee_id: int
    leave_type: str
    start_date: date
    end_date: date
    reason: Optional[str] = None


class LeaveOut(BaseModel):
    id: int
    employee_id: int
    leave_type: str
    start_date: date
    end_date: date
    reason: Optional[str] = None
    status: Literal["pending", "approved", "rejected"]
    created_at: datetime


class LeaveDecisionIn(BaseModel):
    action: Literal["approve", "reject"]
    comment: Optional[str] = None


class LeaveListOut(BaseModel):
    items: list[LeaveOut]
    total: int
    page: int
    size: int

