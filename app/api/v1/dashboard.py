from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import get_current_user
from app.core.rbac import is_admin_like
from app.core.feature_flags import features
from app.db.mongo import get_mongo_db
from app.schemas.dashboard_schema import (
    SummaryMetrics,
    AlertItem,
    TrendSeries,
    TrendPoint,
    ScorecardRow,
    DrilldownResponse,
    DrilldownRow,
)


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=SummaryMetrics)
async def dashboard_summary(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    company_id = ObjectId(current_user["company_id"])
    # Employees
    employees = await db["employees"].count_documents({"company_id": company_id})
    # Pending leaves
    pending_leaves = await db["leaves"].count_documents({"company_id": company_id, "status": "requested"})
    # Documents uploaded this week
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    documents_this_week = await db["documents"].count_documents({"company_id": company_id, "uploaded_at": {"$gte": week_ago}})
    # On leave today (approved)
    start_of_day = datetime(now.year, now.month, now.day)
    end_of_day = start_of_day + timedelta(days=1)
    on_leave_today = await db["leaves"].count_documents({
        "company_id": company_id,
        "status": "approved",
        "start_date": {"$lt": end_of_day},
        "end_date": {"$gte": start_of_day},
    })
    return SummaryMetrics(
        employees=employees,
        pending_leaves=pending_leaves,
        documents_this_week=documents_this_week,
        on_leave_today=on_leave_today,
    )


@router.get("/alerts", response_model=list[AlertItem])
async def dashboard_alerts(
    pending_leave_threshold: int = Query(5, ge=0),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    if not features.alerts:
        raise HTTPException(status_code=404, detail="Alerts disabled")
    company_id = ObjectId(current_user["company_id"])
    alerts: list[AlertItem] = []
    # Pending leaves
    pending_leaves = await db["leaves"].count_documents({"company_id": company_id, "status": "requested"})
    if pending_leaves > pending_leave_threshold:
        alerts.append(AlertItem(
            key="pending_leaves",
            label="Pending leave requests",
            value=pending_leaves,
            threshold=pending_leave_threshold,
            severity="warning" if pending_leaves <= pending_leave_threshold * 2 else "critical",
            status="alert",
            hint="Review leave requests to reduce backlog",
        ))
    return alerts


@router.get("/trends", response_model=list[TrendSeries])
async def dashboard_trends(
    months: int = Query(6, ge=1, le=24),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    if not features.trends:
        raise HTTPException(status_code=404, detail="Trends disabled")
    company_id = ObjectId(current_user["company_id"])
    # Employee headcount over last N months
    now = datetime.utcnow()
    start_month = datetime(now.year, now.month, 1)
    points: list[TrendPoint] = []
    for i in range(months - 1, -1, -1):
        # Compute month window
        year = start_month.year
        month = start_month.month
        # subtract i months
        m = month - i
        y = year
        while m <= 0:
            m += 12
            y -= 1
        start = datetime(y, m, 1)
        # next month
        nm = m + 1
        ny = y + (1 if nm == 13 else 0)
        nm = 1 if nm == 13 else nm
        end = datetime(ny, nm, 1)
        # Count active employees as of end of this month
        count = await db["employees"].count_documents({
            "company_id": company_id,
            "$and": [
                {"date_hired": {"$lt": end}},
                {"$or": [
                    {"date_terminated": None},
                    {"date_terminated": {"$gte": start}},
                ]},
            ],
        })
        points.append(TrendPoint(period=f"{y:04d}-{m:02d}", value=int(count)))
    return [TrendSeries(key="employees", label="Employees", points=points)]


@router.get("/scorecards", response_model=list[ScorecardRow])
async def dashboard_scorecards(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    if not features.scorecards:
        raise HTTPException(status_code=404, detail="Scorecards disabled")
    if not is_admin_like(str(current_user.get("role", ""))):
        raise HTTPException(status_code=403, detail="Forbidden")
    company_id = ObjectId(current_user["company_id"])

    # Map employee -> department
    dept_by_emp: dict[ObjectId, str] = {}
    cursor = (await get_mongo_db())["employees"].find({"company_id": company_id})
    async for e in cursor:
        meta = e.get("metadata") or {}
        dept = meta.get("department") or "Unassigned"
        dept_by_emp[e["_id"]] = dept

    # Initialize rows
    rows: dict[str, ScorecardRow] = {}
    for d in set(dept_by_emp.values()) or {"Unassigned"}:
        rows[d] = ScorecardRow(group=d, employees=0, pending_leaves=0, active_assignments=0)

    # Employees per dept
    for d in dept_by_emp.values():
        rows.setdefault(d, ScorecardRow(group=d, employees=0, pending_leaves=0, active_assignments=0))
        rows[d].employees += 1

    # Pending leaves per dept
    cursor = db["leaves"].find({"company_id": company_id, "status": "requested"})
    async for l in cursor:
        d = dept_by_emp.get(l.get("employee_id")) or "Unassigned"
        rows.setdefault(d, ScorecardRow(group=d, employees=0, pending_leaves=0, active_assignments=0))
        rows[d].pending_leaves += 1

    # Active assignments per dept
    cursor = db["job_assignments"].aggregate([
        {"$match": {"company_id": company_id}},
        {"$group": {"_id": "$employee_id", "count": {"$sum": 1}}},
    ])
    async for row in cursor:
        d = dept_by_emp.get(row.get("_id")) or "Unassigned"
        rows.setdefault(d, ScorecardRow(group=d, employees=0, pending_leaves=0, active_assignments=0))
        rows[d].active_assignments += int(row.get("count", 0))

    # Return sorted by dept name
    return [rows[k] for k in sorted(rows.keys())]


@router.get("/drilldown", response_model=DrilldownResponse)
async def dashboard_drilldown(
    metric: str = Query(..., description="supported: pending_leaves, documents_this_week, on_leave_today"),
    group_by: str = Query("department", description="supported: department"),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    if not features.drilldown:
        raise HTTPException(status_code=404, detail="Drilldown disabled")
    company_id = ObjectId(current_user["company_id"])
    if group_by != "department":
        raise HTTPException(status_code=400, detail="Unsupported group_by")

    # Build employee -> department map
    dept_by_emp: dict[ObjectId, str] = {}
    async for e in db["employees"].find({"company_id": company_id}):
        meta = e.get("metadata") or {}
        dept_by_emp[e["_id"]] = meta.get("department") or "Unassigned"

    rows: dict[str, int] = {}
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    if metric == "pending_leaves":
        cursor = db["leaves"].find({"company_id": company_id, "status": "requested"})
        async for l in cursor:
            d = dept_by_emp.get(l.get("employee_id")) or "Unassigned"
            rows[d] = rows.get(d, 0) + 1
    elif metric == "documents_this_week":
        # Need employee_id on documents to map to department, else bucket into Unassigned
        cursor = db["documents"].find({"company_id": company_id, "uploaded_at": {"$gte": week_ago}})
        async for doc in cursor:
            d = dept_by_emp.get(doc.get("employee_id")) or "Unassigned"
            rows[d] = rows.get(d, 0) + 1
    elif metric == "on_leave_today":
        start_of_day = datetime(now.year, now.month, now.day)
        end_of_day = start_of_day + timedelta(days=1)
        cursor = db["leaves"].find({
            "company_id": company_id,
            "status": "approved",
            "start_date": {"$lt": end_of_day},
            "end_date": {"$gte": start_of_day},
        })
        async for l in cursor:
            d = dept_by_emp.get(l.get("employee_id")) or "Unassigned"
            rows[d] = rows.get(d, 0) + 1
    else:
        raise HTTPException(status_code=400, detail="Unsupported metric")

    out = [DrilldownRow(group=k, value=v) for k, v in sorted(rows.items(), key=lambda kv: kv[0])]
    return DrilldownResponse(metric=metric, group_by=group_by, rows=out)


@router.get("/export.csv")
async def dashboard_export_csv(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    if not features.export:
        raise HTTPException(status_code=404, detail="Export disabled")
    # Simple CSV of summary metrics
    m = await dashboard_summary(db=db, current_user=current_user)  # type: ignore[arg-type]
    lines = [
        ["metric", "value"],
        ["employees", str(m.employees)],
        ["pending_leaves", str(m.pending_leaves)],
        ["documents_this_week", str(m.documents_this_week)],
        ["on_leave_today", str(m.on_leave_today)],
    ]
    # RFC 4180: quote values and double-quote embedded quotes
    csv = "\n".join(
        ",".join('"' + c.replace('"', '""') + '"' for c in row)
        for row in lines
    )
    return PlainTextResponse(content=csv, media_type="text/csv; charset=utf-8")

