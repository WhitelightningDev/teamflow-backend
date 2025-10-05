from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class LeaveIn(BaseModel):
    employee_id: Optional[str] = None  # ignored for employees
    leave_type: Optional[str] = None
    type_id: Optional[str] = None
    start_date: date
    end_date: date
    reason: Optional[str] = None
    half_day: Optional[bool] = None


class LeaveOut(BaseModel):
    id: str
    employee_id: str
    leave_type: str
    start_date: date
    end_date: date
    reason: Optional[str] = None
    status: Literal["requested", "approved", "rejected", "cancelled"]
    created_at: datetime


class LeaveDecisionIn(BaseModel):
    action: Literal["approve", "reject"]
    comment: Optional[str] = None


class LeaveStatusIn(BaseModel):
    status: Literal["approved", "rejected", "cancelled"]
    comment: Optional[str] = None


class LeaveListOut(BaseModel):
    items: list[LeaveOut]
    total: int
    page: int
    size: int


# MongoDB leaves collection document schema
class LeaveDocument(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    company_id: str
    employee_id: str
    leave_type: str  # could also be an ObjectId string to a lookup
    start_date: date
    end_date: date
    reason: Optional[str] = None
    status: Literal["requested", "approved", "rejected", "cancelled"]
    requested_on: datetime
    decided_on: Optional[datetime] = None
    approver_id: Optional[str] = None
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Allow using field names or aliases
    model_config = ConfigDict(populate_by_name=True)
