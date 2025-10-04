from datetime import date
from typing import Optional
from pydantic import BaseModel, EmailStr


class EmployeeIn(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    role: str = "employee"
    title: Optional[str] = None
    start_date: date
    manager_id: Optional[int] = None
    is_active: bool = True


class EmployeeUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[date] = None
    manager_id: Optional[int] = None
    is_active: Optional[bool] = None


class EmployeeOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: EmailStr
    role: str
    title: Optional[str] = None
    start_date: date
    manager_id: Optional[int] = None
    is_active: bool


class EmployeeListOut(BaseModel):
    items: list[EmployeeOut]
    total: int
    page: int
    size: int

