from typing import Optional
from pydantic import BaseModel, EmailStr


class ProfileIn(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    title: Optional[str] = None
    phone: Optional[str] = None
    timezone: Optional[str] = None


class ProfileOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: EmailStr
    title: Optional[str] = None
    phone: Optional[str] = None
    timezone: Optional[str] = None


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    timezone: Optional[str] = None


class CompanyOut(BaseModel):
    id: int
    name: str
    domain: str
    timezone: str


class NotificationSettingsUpdate(BaseModel):
    email_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None


class NotificationSettingsOut(BaseModel):
    email_notifications: bool
    push_notifications: bool

