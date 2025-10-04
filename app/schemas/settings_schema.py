from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict


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


# MongoDB settings collection document schema
class SettingsNotification(BaseModel):
    email: bool
    push: bool


class SettingsDocument(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    company_id: str
    notification_settings: SettingsNotification
    updated_at: datetime
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)
