from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from .common import Role


class EmployeeIn(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    role: Role = Role.employee
    title: Optional[str] = None
    start_date: date
    manager_id: Optional[int] = None
    is_active: bool = True


class EmployeeUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[Role] = None
    title: Optional[str] = None
    start_date: Optional[date] = None
    manager_id: Optional[int] = None
    is_active: Optional[bool] = None


class EmployeeOut(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: EmailStr
    role: Role
    title: Optional[str] = None
    start_date: date
    manager_id: Optional[int] = None
    is_active: bool


class EmployeeListOut(BaseModel):
    items: list[EmployeeOut]
    total: int
    page: int
    size: int


# MongoDB employees collection document schema
class EmployeeDocument(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    company_id: str  # ObjectId as string
    first_name: str
    last_name: str
    email: EmailStr
    role: Role  # e.g., manager, hr, staff
    status: str  # e.g., active, terminated, on_leave
    date_hired: date
    date_terminated: Optional[date] = None
    profile_photo: Optional[str] = None
    # Location (e.g., South African province)
    province: Optional[str] = None
    # Optional metadata/tags
    metadata: Optional[dict] = None
    tags: Optional[list[str]] = None
    created_at: datetime
    updated_at: datetime

    # Allow population by field name and alias
    model_config = ConfigDict(populate_by_name=True)
