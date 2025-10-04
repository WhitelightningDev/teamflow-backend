from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class LookupDocument(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    category: str  # e.g., "leave_types", "roles", "leave_statuses"
    code: str      # e.g., "annual", "sick", "approved"
    label: str     # e.g., "Annual Leave", "Sick Leave"
    sequence: Optional[int] = None  # optional ordering
    extra: Optional[dict] = None    # optional metadata

    model_config = ConfigDict(populate_by_name=True)

