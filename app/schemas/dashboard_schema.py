from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SummaryMetrics(BaseModel):
    employees: int = 0
    pending_leaves: int = 0
    documents_this_week: int = 0
    on_leave_today: int = 0


class AlertItem(BaseModel):
    key: str
    label: str
    value: float | int
    threshold: float | int
    severity: Literal["info", "warning", "critical"] = "warning"
    status: Literal["ok", "alert"] = "alert"
    hint: Optional[str] = None


class TrendPoint(BaseModel):
    period: str  # e.g., YYYY-MM
    value: float | int


class TrendSeries(BaseModel):
    key: str
    label: str
    points: list[TrendPoint]


class ScorecardRow(BaseModel):
    group: str = Field(description="Department or manager name")
    employees: int
    pending_leaves: int
    active_assignments: int


class DrilldownRow(BaseModel):
    group: str
    value: float | int


class DrilldownResponse(BaseModel):
    metric: str
    group_by: str
    rows: list[DrilldownRow]

