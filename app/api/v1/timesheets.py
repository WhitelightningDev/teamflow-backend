from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import get_current_user
from app.core.rbac import is_admin_like
from app.db.mongo import get_mongo_db
from app.schemas.job_schema import JobIn, JobUpdate, JobOut, JobRateIn, JobRateOut
from app.schemas.time_entry_schema import (
    ManualTimeEntryIn,
    ManualTimeEntryUpdate,
    ClockInPayload,
    TimeEntryOut,
)


router = APIRouter(prefix="/time", tags=["time"])


async def _get_current_employee_id(db: AsyncIOMotorDatabase, user: dict) -> ObjectId:
    me = await db["employees"].find_one({
        "company_id": ObjectId(user["company_id"]),
        "user_id": ObjectId(user["id"]),
    })
    if not me:
        raise HTTPException(status_code=400, detail="No employee profile linked to your account")
    return me["_id"]


async def _get_effective_rate(db: AsyncIOMotorDatabase, company_id: ObjectId, job_id: ObjectId, employee_id: ObjectId) -> float:
    jr = await db["job_rates"].find_one({
        "company_id": company_id,
        "job_id": job_id,
        "employee_id": employee_id,
    })
    if jr and isinstance(jr.get("rate"), (int, float)):
        return float(jr["rate"])
    job = await db["jobs"].find_one({"_id": job_id, "company_id": company_id})
    return float(job.get("default_rate", 0.0)) if job else 0.0


# ---------------------- Jobs ----------------------


@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job(payload: JobIn, db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    # Admin/manager/HR only
    if not is_admin_like(str(current_user.get("role", ""))):
        raise HTTPException(status_code=403, detail="Forbidden")
    doc = {
        "company_id": ObjectId(current_user["company_id"]),
        "name": payload.name,
        "client_name": payload.client_name,
        "default_rate": float(payload.default_rate or 0.0),
        "active": bool(payload.active),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    # Enforce unique name per company
    existing = await db["jobs"].find_one({"company_id": doc["company_id"], "name": doc["name"]})
    if existing:
        raise HTTPException(status_code=400, detail="Job with this name already exists")
    res = await db["jobs"].insert_one(doc)
    return JobOut(
        id=str(res.inserted_id),
        name=doc["name"],
        client_name=doc.get("client_name"),
        default_rate=doc.get("default_rate", 0.0),
        active=doc.get("active", True),
    )


@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(
    active: Optional[bool] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    q = {"company_id": ObjectId(current_user["company_id"])}
    if active is not None:
        q["active"] = bool(active)
    cursor = db["jobs"].find(q).sort("created_at", -1)
    out: list[JobOut] = []
    async for j in cursor:
        out.append(JobOut(
            id=str(j["_id"]),
            name=j.get("name", ""),
            client_name=j.get("client_name"),
            default_rate=float(j.get("default_rate", 0.0)),
            active=bool(j.get("active", True)),
        ))
    return out


@router.patch("/jobs/{job_id}", response_model=JobOut)
async def update_job(
    payload: JobUpdate,
    job_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    if not is_admin_like(str(current_user.get("role", ""))):
        raise HTTPException(status_code=403, detail="Forbidden")
    company_id = ObjectId(current_user["company_id"])
    update: dict = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if "default_rate" in update and update["default_rate"] is not None:
        update["default_rate"] = float(update["default_rate"])  # normalize
    update["updated_at"] = datetime.utcnow()
    if "name" in update:
        # keep unique per company
        exists = await db["jobs"].find_one({"company_id": company_id, "name": update["name"], "_id": {"$ne": ObjectId(job_id)}})
        if exists:
            raise HTTPException(status_code=400, detail="Job with this name already exists")
    res = await db["jobs"].update_one({"_id": ObjectId(job_id), "company_id": company_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    j = await db["jobs"].find_one({"_id": ObjectId(job_id)})
    return JobOut(
        id=str(j["_id"]),
        name=j.get("name", ""),
        client_name=j.get("client_name"),
        default_rate=float(j.get("default_rate", 0.0)),
        active=bool(j.get("active", True)),
    )


@router.post("/jobs/{job_id}/rates", response_model=JobRateOut)
async def set_job_rate(
    payload: JobRateIn,
    job_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    if not is_admin_like(str(current_user.get("role", ""))):
        raise HTTPException(status_code=403, detail="Forbidden")
    company_id = ObjectId(current_user["company_id"])
    job_oid = ObjectId(job_id)
    emp_oid = ObjectId(payload.employee_id)
    # Ensure job exists
    job = await db["jobs"].find_one({"_id": job_oid, "company_id": company_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    now = datetime.utcnow()
    doc = {
        "company_id": company_id,
        "job_id": job_oid,
        "employee_id": emp_oid,
        "rate": float(payload.rate),
        "updated_at": now,
        "created_at": now,
    }
    # Upsert unique per (company, job, employee)
    await db["job_rates"].update_one(
        {"company_id": company_id, "job_id": job_oid, "employee_id": emp_oid},
        {"$set": {"rate": doc["rate"], "updated_at": now}, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    jr = await db["job_rates"].find_one({"company_id": company_id, "job_id": job_oid, "employee_id": emp_oid})
    return JobRateOut(id=str(jr["_id"]), job_id=str(job_oid), employee_id=str(emp_oid), rate=float(jr.get("rate", 0.0)))


@router.get("/jobs/{job_id}/rates", response_model=list[JobRateOut])
async def list_job_rates(job_id: str = Path(...), db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    if not is_admin_like(str(current_user.get("role", ""))):
        raise HTTPException(status_code=403, detail="Forbidden")
    company_id = ObjectId(current_user["company_id"])
    job_oid = ObjectId(job_id)
    cursor = db["job_rates"].find({"company_id": company_id, "job_id": job_oid}).sort("updated_at", -1)
    out: list[JobRateOut] = []
    async for r in cursor:
        out.append(JobRateOut(id=str(r["_id"]), job_id=str(job_oid), employee_id=str(r["employee_id"]), rate=float(r.get("rate", 0.0))))
    return out


# ---------------------- Time entries ----------------------


def _start_of_day(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, dt.day)


@router.post("/entries/clock-in", response_model=TimeEntryOut)
async def clock_in(payload: ClockInPayload, db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    company_id = ObjectId(current_user["company_id"])
    employee_id = await _get_current_employee_id(db, current_user)
    job_oid = ObjectId(payload.job_id)
    job = await db["jobs"].find_one({"_id": job_oid, "company_id": company_id, "active": True})
    if not job:
        raise HTTPException(status_code=400, detail="Invalid or inactive job")
    # ensure no other active entry
    active = await db["time_entries"].find_one({"company_id": company_id, "employee_id": employee_id, "is_active": True})
    if active:
        raise HTTPException(status_code=400, detail="You already have an active time entry")
    now = datetime.utcnow()
    doc = {
        "company_id": company_id,
        "employee_id": employee_id,
        "job_id": job_oid,
        "date": _start_of_day(now),
        "start_ts": now,
        "end_ts": None,
        "break_minutes": 0,
        "break_started_at": None,
        "is_active": True,
        "note": payload.note,
        "source": "clock",
        "created_at": now,
        "updated_at": now,
    }
    res = await db["time_entries"].insert_one(doc)
    rate = await _get_effective_rate(db, company_id, job_oid, employee_id)
    return TimeEntryOut(
        id=str(res.inserted_id),
        job_id=str(job_oid),
        employee_id=str(employee_id),
        start_ts=doc["start_ts"],
        end_ts=None,
        break_minutes=0,
        is_active=True,
        on_break=False,
        note=doc.get("note"),
        rate=rate,
    )


@router.post("/entries/break/start", response_model=TimeEntryOut)
async def break_start(db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    company_id = ObjectId(current_user["company_id"])
    employee_id = await _get_current_employee_id(db, current_user)
    ent = await db["time_entries"].find_one({"company_id": company_id, "employee_id": employee_id, "is_active": True})
    if not ent:
        raise HTTPException(status_code=400, detail="No active time entry to start a break")
    if ent.get("break_started_at"):
        raise HTTPException(status_code=400, detail="Already on a break")
    now = datetime.utcnow()
    await db["time_entries"].update_one({"_id": ent["_id"]}, {"$set": {"break_started_at": now, "updated_at": now}})
    ent = await db["time_entries"].find_one({"_id": ent["_id"]})
    rate = await _get_effective_rate(db, company_id, ent["job_id"], employee_id)
    return TimeEntryOut(
        id=str(ent["_id"]),
        job_id=str(ent["job_id"]),
        employee_id=str(employee_id),
        start_ts=ent.get("start_ts"),
        end_ts=ent.get("end_ts"),
        break_minutes=int(ent.get("break_minutes", 0)),
        is_active=True,
        on_break=True,
        note=ent.get("note"),
        rate=rate,
    )


@router.post("/entries/break/end", response_model=TimeEntryOut)
async def break_end(db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    company_id = ObjectId(current_user["company_id"])
    employee_id = await _get_current_employee_id(db, current_user)
    ent = await db["time_entries"].find_one({"company_id": company_id, "employee_id": employee_id, "is_active": True})
    if not ent or not ent.get("break_started_at"):
        raise HTTPException(status_code=400, detail="Not currently on a break")
    now = datetime.utcnow()
    delta = now - ent["break_started_at"]
    add_minutes = max(0, int(delta.total_seconds() // 60))
    new_total = int(ent.get("break_minutes", 0)) + add_minutes
    await db["time_entries"].update_one({"_id": ent["_id"]}, {"$set": {"break_minutes": new_total, "break_started_at": None, "updated_at": now}})
    ent = await db["time_entries"].find_one({"_id": ent["_id"]})
    rate = await _get_effective_rate(db, company_id, ent["job_id"], employee_id)
    return TimeEntryOut(
        id=str(ent["_id"]),
        job_id=str(ent["job_id"]),
        employee_id=str(employee_id),
        start_ts=ent.get("start_ts"),
        end_ts=ent.get("end_ts"),
        break_minutes=int(ent.get("break_minutes", 0)),
        is_active=True,
        on_break=False,
        note=ent.get("note"),
        rate=rate,
    )


@router.post("/entries/clock-out", response_model=TimeEntryOut)
async def clock_out(db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    company_id = ObjectId(current_user["company_id"])
    employee_id = await _get_current_employee_id(db, current_user)
    ent = await db["time_entries"].find_one({"company_id": company_id, "employee_id": employee_id, "is_active": True})
    if not ent:
        raise HTTPException(status_code=400, detail="No active time entry to clock out")
    now = datetime.utcnow()
    # If currently on break, end break
    if ent.get("break_started_at"):
        delta = now - ent["break_started_at"]
        add_minutes = max(0, int(delta.total_seconds() // 60))
        ent["break_minutes"] = int(ent.get("break_minutes", 0)) + add_minutes
        ent["break_started_at"] = None
    duration_minutes = max(0, int((now - ent["start_ts"]).total_seconds() // 60) - int(ent.get("break_minutes", 0)))
    await db["time_entries"].update_one(
        {"_id": ent["_id"]},
        {"$set": {"end_ts": now, "is_active": False, "break_minutes": int(ent.get("break_minutes", 0)), "duration_minutes": duration_minutes, "updated_at": now, "break_started_at": None}},
    )
    ent = await db["time_entries"].find_one({"_id": ent["_id"]})
    rate = await _get_effective_rate(db, company_id, ent["job_id"], employee_id)
    amount = round((float(duration_minutes) / 60.0) * rate, 2) if duration_minutes else 0.0
    return TimeEntryOut(
        id=str(ent["_id"]),
        job_id=str(ent["job_id"]),
        employee_id=str(employee_id),
        start_ts=ent.get("start_ts"),
        end_ts=ent.get("end_ts"),
        break_minutes=int(ent.get("break_minutes", 0)),
        is_active=False,
        on_break=False,
        duration_minutes=int(ent.get("duration_minutes", 0)),
        note=ent.get("note"),
        rate=rate,
        amount=amount,
    )


@router.post("/entries", response_model=TimeEntryOut, status_code=status.HTTP_201_CREATED)
async def create_manual_time_entry(payload: ManualTimeEntryIn, db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    company_id = ObjectId(current_user["company_id"])
    employee_id = await _get_current_employee_id(db, current_user)
    job_oid = ObjectId(payload.job_id)
    job = await db["jobs"].find_one({"_id": job_oid, "company_id": company_id})
    if not job:
        raise HTTPException(status_code=400, detail="Invalid job")
    if payload.end_ts <= payload.start_ts:
        raise HTTPException(status_code=400, detail="end_ts must be after start_ts")
    duration_minutes = max(0, int((payload.end_ts - payload.start_ts).total_seconds() // 60) - int(payload.break_minutes or 0))
    now = datetime.utcnow()
    doc = {
        "company_id": company_id,
        "employee_id": employee_id,
        "job_id": job_oid,
        "date": _start_of_day(payload.start_ts),
        "start_ts": payload.start_ts,
        "end_ts": payload.end_ts,
        "break_minutes": int(payload.break_minutes or 0),
        "duration_minutes": duration_minutes,
        "is_active": False,
        "break_started_at": None,
        "note": payload.note,
        "source": "manual",
        "created_at": now,
        "updated_at": now,
    }
    res = await db["time_entries"].insert_one(doc)
    rate = await _get_effective_rate(db, company_id, job_oid, employee_id)
    amount = round((float(duration_minutes) / 60.0) * rate, 2) if duration_minutes else 0.0
    return TimeEntryOut(
        id=str(res.inserted_id),
        job_id=str(job_oid),
        employee_id=str(employee_id),
        start_ts=doc["start_ts"],
        end_ts=doc["end_ts"],
        break_minutes=doc["break_minutes"],
        is_active=False,
        on_break=False,
        duration_minutes=duration_minutes,
        note=doc.get("note"),
        rate=rate,
        amount=amount,
    )


@router.patch("/entries/{entry_id}", response_model=TimeEntryOut)
async def update_manual_time_entry(
    payload: ManualTimeEntryUpdate,
    entry_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    company_id = ObjectId(current_user["company_id"])
    employee_id = await _get_current_employee_id(db, current_user)
    ent = await db["time_entries"].find_one({"_id": ObjectId(entry_id), "company_id": company_id, "employee_id": employee_id})
    if not ent:
        raise HTTPException(status_code=404, detail="Time entry not found")
    if ent.get("source") != "manual":
        raise HTTPException(status_code=400, detail="Only manual entries can be edited")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    # recompute duration if start/end/break changed
    start = update.get("start_ts", ent.get("start_ts"))
    end = update.get("end_ts", ent.get("end_ts"))
    break_m = int(update.get("break_minutes", ent.get("break_minutes", 0)) or 0)
    if end <= start:
        raise HTTPException(status_code=400, detail="end_ts must be after start_ts")
    duration_minutes = max(0, int((end - start).total_seconds() // 60) - break_m)
    update["duration_minutes"] = duration_minutes
    update["date"] = _start_of_day(start)
    update["updated_at"] = datetime.utcnow()
    await db["time_entries"].update_one({"_id": ent["_id"]}, {"$set": update})
    ent = await db["time_entries"].find_one({"_id": ent["_id"]})
    rate = await _get_effective_rate(db, company_id, ent["job_id"], employee_id)
    amount = round((float(ent.get("duration_minutes", 0)) / 60.0) * rate, 2) if ent.get("duration_minutes") else 0.0
    return TimeEntryOut(
        id=str(ent["_id"]),
        job_id=str(ent["job_id"]),
        employee_id=str(employee_id),
        start_ts=ent.get("start_ts"),
        end_ts=ent.get("end_ts"),
        break_minutes=int(ent.get("break_minutes", 0)),
        is_active=False,
        on_break=False,
        duration_minutes=int(ent.get("duration_minutes", 0)),
        note=ent.get("note"),
        rate=rate,
        amount=amount,
    )


@router.delete("/entries/{entry_id}")
async def delete_time_entry(entry_id: str = Path(...), db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    company_id = ObjectId(current_user["company_id"])
    employee_id = await _get_current_employee_id(db, current_user)
    res = await db["time_entries"].delete_one({"_id": ObjectId(entry_id), "company_id": company_id, "employee_id": employee_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Time entry not found")
    return {"status": "deleted", "id": entry_id}


@router.get("/entries/me")
async def my_time_entries(
    job_id: Optional[str] = Query(None),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    company_id = ObjectId(current_user["company_id"])
    employee_id = await _get_current_employee_id(db, current_user)
    q: dict = {"company_id": company_id, "employee_id": employee_id}
    if job_id:
        q["job_id"] = ObjectId(job_id)
    if from_:
        q["date"] = {"$gte": _start_of_day(datetime.fromisoformat(from_))}
    if to:
        q.setdefault("date", {}).update({"$lte": _start_of_day(datetime.fromisoformat(to))})
    total = await db["time_entries"].count_documents(q)
    cursor = db["time_entries"].find(q).skip((page - 1) * limit).limit(limit).sort("date", -1)
    items = []
    async for doc in cursor:
        rate = await _get_effective_rate(db, company_id, doc["job_id"], employee_id)
        dur = int(doc.get("duration_minutes") or (int(((doc.get("end_ts") or datetime.utcnow()) - doc.get("start_ts")).total_seconds() // 60) - int(doc.get("break_minutes", 0))) if doc.get("is_active") else 0)
        amount = round((float(dur) / 60.0) * rate, 2) if dur else 0.0
        items.append({
            "id": str(doc["_id"]),
            "job_id": str(doc.get("job_id")),
            "employee_id": str(doc.get("employee_id")),
            "start_ts": doc.get("start_ts"),
            "end_ts": doc.get("end_ts"),
            "break_minutes": int(doc.get("break_minutes", 0)),
            "is_active": bool(doc.get("is_active", False)),
            "on_break": bool(doc.get("break_started_at") is not None),
            "duration_minutes": dur or None,
            "note": doc.get("note"),
            "rate": rate,
            "amount": amount,
        })
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.get("/reports/billing")
async def billing_report(
    month: str = Query(..., description="YYYY-MM month, e.g., 2025-10"),
    job_id: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    # Admin-like only
    if not is_admin_like(str(current_user.get("role", ""))):
        raise HTTPException(status_code=403, detail="Forbidden")
    company_id = ObjectId(current_user["company_id"])
    try:
        year, mon = [int(x) for x in month.split("-")]
        start = datetime(year, mon, 1)
        end = datetime(year + (1 if mon == 12 else 0), 1 if mon == 12 else mon + 1, 1)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid month format") from exc

    q: dict = {"company_id": company_id, "date": {"$gte": _start_of_day(start), "$lt": _start_of_day(end)}}
    if job_id:
        q["job_id"] = ObjectId(job_id)

    # Aggregate by job and employee
    pipeline = [
        {"$match": q},
        {"$group": {
            "_id": {"job_id": "$job_id", "employee_id": "$employee_id"},
            "minutes": {"$sum": {"$ifNull": ["$duration_minutes", 0]}},
        }},
    ]
    agg = db["time_entries"].aggregate(pipeline)
    results = {}
    async for row in agg:
        job_oid = row["_id"]["job_id"]
        emp_oid = row["_id"]["employee_id"]
        minutes = int(row.get("minutes", 0))
        rate = await _get_effective_rate(db, company_id, job_oid, emp_oid)
        amount = round((float(minutes) / 60.0) * rate, 2)
        key = str(job_oid)
        results.setdefault(key, {"job_id": key, "minutes": 0, "amount": 0.0, "by_employee": []})
        results[key]["minutes"] += minutes
        results[key]["amount"] = round(results[key]["amount"] + amount, 2)
        results[key]["by_employee"].append({"employee_id": str(emp_oid), "minutes": minutes, "rate": rate, "amount": amount})

    # Attach job info
    out = []
    for jid, data in results.items():
        job = await db["jobs"].find_one({"_id": ObjectId(jid)})
        out.append({
            "job_id": jid,
            "job_name": job.get("name", "") if job else "",
            "client_name": job.get("client_name") if job else None,
            "minutes": data["minutes"],
            "hours": round(data["minutes"] / 60.0, 2),
            "amount": data["amount"],
            "by_employee": data["by_employee"],
        })
    return {"month": month, "jobs": out}
