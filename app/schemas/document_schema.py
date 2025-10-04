from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from .common import Role


class DocumentOut(BaseModel):
    id: str
    filename: str
    content_type: str | None
    size: int
    uploaded_by: int | str | None
    uploaded_at: datetime


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int
    size: int


# MongoDB user document schema (for TeamFlow)
class UserDocument(BaseModel):
    # Use string IDs in API; map to Mongo's _id via alias
    id: Optional[str] = Field(default=None, alias="_id")
    email: EmailStr
    password_hash: str
    first_name: str
    last_name: str
    role: Role
    company_id: str  # ObjectId as string in API layer
    created_at: datetime
    updated_at: datetime
    is_active: bool
    # optional fields
    last_login: Optional[datetime] = None
    profile_photo_url: Optional[str] = None

    # Allow population by field name and alias
    model_config = ConfigDict(populate_by_name=True)


# MongoDB documents collection schema
class DocumentDocument(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    company_id: str
    employee_id: Optional[str] = None
    category: str
    filename: str
    file_url: str
    mime_type: str
    size_bytes: int
    uploaded_by: str
    uploaded_at: datetime
    updated_at: datetime

    model_config = ConfigDict(populate_by_name=True)
