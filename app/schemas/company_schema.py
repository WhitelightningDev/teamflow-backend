from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict


class CompanyNotificationsSettings(BaseModel):
    email: bool
    push: bool


class CompanySettings(BaseModel):
    notifications: CompanyNotificationsSettings


class CompanyDocument(BaseModel):
    # Expose Mongo's _id as string via alias
    id: Optional[str] = Field(default=None, alias="_id")
    name: str
    address: Optional[str] = None
    contact_email: EmailStr
    created_at: datetime
    updated_at: datetime
    logo_url: Optional[str] = None
    timezone: Optional[str] = None
    settings: Optional[CompanySettings] = None

    # Allow population by field name and alias
    model_config = ConfigDict(populate_by_name=True)

