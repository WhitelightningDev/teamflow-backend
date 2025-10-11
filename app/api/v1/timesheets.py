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
    PausePayload,
    AbandonPayload,
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


async def _backfill_assignment_activity(db: AsyncIOMotorDatabase, company_id: ObjectId, employee_id: ObjectId) -> None:
    """Ensure there is at least one 'assigned' activity for each existing assignment.
    Non-fatal on errors; designed to run quickly per-employee.
    """
    try:
        cursor = db["job_assignments"].find({"company_id": company_id, "employee_id": employee_id})
        async for a in cursor:
            job_id = a.get("job_id")
            if not isinstance(job_id, ObjectId):
                continue
            exists = await db["assignment_activity"].find_one({
                "company_id": company_id,
                "employee_id": employee_id,
                "job_id": job_id,
                "action": "assigned",
            })
            if exists:
                continue
            # Build synthetic assigned event from assignment timestamps
            created = a.get("created_at") or a.get("updated_at") or datetime.utcnow()
            job = await db["jobs"].find_one({"_id": job_id, "company_id": company_id})
            await db["assignment_activity"].insert_one({
                "company_id": company_id,
                "employee_id": employee_id,
                "job_id": job_id,
                "job_name": (job or {}).get("name"),
                "action": "assigned",
                "actor_user_id": None,
                "created_at": created,
            })
    except Exception:
        # Best-effort backfill; ignore failures
        pass


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
    assigned_to_me: Optional[bool] = Query(False, description="If true, only return jobs assigned to the current employee"),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    q = {"company_id": ObjectId(current_user["company_id"])}
    if active is not None:
        q["active"] = bool(active)
    # If non-admin asks for assigned_to_me, filter to assigned job_ids for this employee
    if assigned_to_me and not is_admin_like(str(current_user.get("role", ""))):
        employee_id = await _get_current_employee_id(db, current_user)
        assigned_job_ids: list[ObjectId] = []
        async for a in db["job_assignments"].find({
            "company_id": ObjectId(current_user["company_id"]),
            "employee_id": employee_id,
        }, {"job_id": 1}):
            jid = a.get("job_id")
            if isinstance(jid, ObjectId):
                assigned_job_ids.append(jid)
        if assigned_job_ids:
            q["_id"] = {"$in": assigned_job_ids}
        else:
            # No assignments: return empty list explicitly
            return []
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


# ---------------------- Job assignments ----------------------


@router.get("/jobs/{job_id}/assignments")
async def list_job_assignments(job_id: str = Path(...), db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    if not is_admin_like(str(current_user.get("role", ""))):
        raise HTTPException(status_code=403, detail="Forbidden")
    company_id = ObjectId(current_user["company_id"])
    job_oid = ObjectId(job_id)
    cursor = db["job_assignments"].find({"company_id": company_id, "job_id": job_oid}).sort("created_at", -1)
    items: list[dict] = []
    async for a in cursor:
        items.append({"id": str(a["_id"]), "job_id": str(job_oid), "employee_id": str(a.get("employee_id"))})
    return items


@router.post("/jobs/{job_id}/assign")
async def assign_job(job_id: str = Path(...), payload: dict = None, db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    if not is_admin_like(str(current_user.get("role", ""))):
        raise HTTPException(status_code=403, detail="Forbidden")
    company_id = ObjectId(current_user["company_id"])
    job_oid = ObjectId(job_id)
    if not payload:
        raise HTTPException(status_code=400, detail="Missing body")
    emp_oid: ObjectId | None = None
    if payload.get("employee_id"):
        emp_oid = ObjectId(payload["employee_id"])
    elif payload.get("employee_email"):
        emp_doc = await db["employees"].find_one({"company_id": company_id, "email": payload["employee_email"]})
        if not emp_doc:
            raise HTTPException(status_code=404, detail="Employee with this email not found")
        emp_oid = emp_doc["_id"]
    else:
        raise HTTPException(status_code=400, detail="employee_id or employee_email is required")
    # Ensure job exists
    job = await db["jobs"].find_one({"_id": job_oid, "company_id": company_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    now = datetime.utcnow()
    result = await db["job_assignments"].update_one(
        {"company_id": company_id, "job_id": job_oid, "employee_id": emp_oid},
        {"$set": {"updated_at": now}, "$setOnInsert": {"created_at": now, "state": "assigned", "state_changed_at": now}},
        upsert=True,
    )
    a = await db["job_assignments"].find_one({"company_id": company_id, "job_id": job_oid, "employee_id": emp_oid})
    # Log assignment activity only on new upsert (first-time assignment)
    try:
        if getattr(result, "upserted_id", None) is not None:
            await db["assignment_activity"].insert_one({
                "company_id": company_id,
                "employee_id": emp_oid,
                "job_id": job_oid,
                "job_name": job.get("name"),
                "action": "assigned",
                "actor_user_id": ObjectId(current_user["id"]),
                "created_at": now,
            })
            # Notify the employee about the new assignment (if user linked)
            emp_doc = await db["employees"].find_one({"_id": emp_oid, "company_id": company_id})
            if emp_doc and emp_doc.get("user_id"):
                await db["notifications"].insert_one({
                    "user_id": emp_doc["user_id"],
                    "type": "job_assignment",
                    "payload": {"action": "assigned", "job_id": str(job_oid), "job_name": job.get("name")},
                    "read": False,
                    "created_at": now,
                })
    except Exception:
        # Activity logging is non-fatal
        pass
    return {"id": str(a["_id"]), "job_id": str(job_oid), "employee_id": str(emp_oid)}


@router.delete("/jobs/{job_id}/assign/{employee_id}")
async def unassign_job(job_id: str = Path(...), employee_id: str = Path(...), db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    if not is_admin_like(str(current_user.get("role", ""))):
        raise HTTPException(status_code=403, detail="Forbidden")
    company_id = ObjectId(current_user["company_id"])
    job_oid = ObjectId(job_id)
    emp_oid = ObjectId(employee_id)
    # Mark state canceled before removal for audit trail
    try:
        await db["job_assignments"].update_one(
            {"company_id": company_id, "job_id": job_oid, "employee_id": emp_oid},
            {"$set": {"state": "canceled", "state_changed_at": datetime.utcnow()}},
        )
    except Exception:
        pass
    res = await db["job_assignments"].delete_one({"company_id": company_id, "job_id": job_oid, "employee_id": emp_oid})
    # Log unassignment activity only if something was deleted
    if getattr(res, "deleted_count", 0) > 0:
        try:
            job = await db["jobs"].find_one({"_id": job_oid, "company_id": company_id})
            await db["assignment_activity"].insert_one({
                "company_id": company_id,
                "employee_id": emp_oid,
                "job_id": job_oid,
                "job_name": (job or {}).get("name"),
                "action": "canceled",
                "actor_user_id": ObjectId(current_user["id"]),
                "created_at": datetime.utcnow(),
            })
            # Notify the employee of unassignment (if user linked)
            emp_doc = await db["employees"].find_one({"_id": emp_oid, "company_id": company_id})
            if emp_doc and emp_doc.get("user_id"):
                await db["notifications"].insert_one({
                    "user_id": emp_doc["user_id"],
                    "type": "job_assignment",
                    "payload": {"action": "unassigned", "job_id": str(job_oid), "job_name": (job or {}).get("name")},
                    "read": False,
                    "created_at": datetime.utcnow(),
                })
        except Exception:
            pass
    return {"status": "unassigned", "job_id": job_id, "employee_id": employee_id}


@router.get("/assignments/activity")
async def my_assignment_activity(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    employee_id: Optional[str] = Query(None, description="Admin-only: filter by employee_id"),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    """List assignment activity for the current employee; admin can filter by employee_id."""
    company_id = ObjectId(current_user["company_id"])
    # Default to current user's employee id
    me_emp_id = await _get_current_employee_id(db, current_user)
    target_emp_oid = me_emp_id
    # Allow admins to query for another employee
    if employee_id and is_admin_like(str(current_user.get("role", ""))):
        try:
            target_emp_oid = ObjectId(employee_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid employee_id")
    # Best-effort backfill to surface existing assignments as activity
    await _backfill_assignment_activity(db, company_id, target_emp_oid)
    q = {"company_id": company_id, "employee_id": target_emp_oid}
    total = await db["assignment_activity"].count_documents(q)
    cursor = db["assignment_activity"].find(q).skip((page - 1) * limit).limit(limit).sort("created_at", -1)
    items: list[dict] = []
    async for ev in cursor:
        items.append({
            "id": str(ev["_id"]),
            "job_id": str(ev.get("job_id")) if ev.get("job_id") else None,
            "job_name": ev.get("job_name"),
            "action": ev.get("action"),
            "created_at": ev.get("created_at"),
        })
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.get("/my/assignments")
async def my_assignments(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    """List current user's job assignments with state and job info."""
    company_id = ObjectId(current_user["company_id"])
    employee_id = await _get_current_employee_id(db, current_user)
    # Backfill default state for missing
    try:
        await db["job_assignments"].update_many(
            {"company_id": company_id, "employee_id": employee_id, "state": {"$exists": False}},
            {"$set": {"state": "assigned", "state_changed_at": datetime.utcnow()}},
        )
    except Exception:
        pass
    cursor = db["job_assignments"].find({"company_id": company_id, "employee_id": employee_id})
    items: list[dict] = []
    async for a in cursor:
        job = await db["jobs"].find_one({"_id": a.get("job_id"), "company_id": company_id})
        items.append({
            "job_id": str(a.get("job_id")),
            "job_name": (job or {}).get("name", ""),
            "client_name": (job or {}).get("client_name"),
            "state": a.get("state", "assigned"),
            "state_changed_at": a.get("state_changed_at"),
        })
    return {"items": items}


@router.get("/assignments")
async def list_company_assignments(
    state: Optional[str] = Query(None, description="Filter by state: assigned|in_progress|done|canceled"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    """Admin: list all assignments with current state, job and employee info."""
    if not is_admin_like(str(current_user.get("role", ""))):
        raise HTTPException(status_code=403, detail="Forbidden")
    company_id = ObjectId(current_user["company_id"])
    q: dict = {"company_id": company_id}
    if state:
        if state not in {"assigned", "in_progress", "done", "canceled"}:
            raise HTTPException(status_code=400, detail="Invalid state")
        q["state"] = state
    total = await db["job_assignments"].count_documents(q)
    cursor = db["job_assignments"].find(q).skip((page - 1) * limit).limit(limit).sort("state_changed_at", -1)
    items: list[dict] = []
    async for a in cursor:
        job = await db["jobs"].find_one({"_id": a.get("job_id"), "company_id": company_id})
        emp = await db["employees"].find_one({"_id": a.get("employee_id"), "company_id": company_id})
        # latest activity action
        act = await db["assignment_activity"].find_one({
            "company_id": company_id,
            "employee_id": a.get("employee_id"),
            "job_id": a.get("job_id"),
        }, sort=[("created_at", -1)])
        items.append({
            "job_id": str(a.get("job_id")),
            "job_name": (job or {}).get("name", ""),
            "client_name": (job or {}).get("client_name"),
            "employee_id": str(a.get("employee_id")),
            "employee_name": (f"{(emp or {}).get('first_name','')} {(emp or {}).get('last_name','')}").strip() or (emp or {}).get("email"),
            "state": a.get("state", "assigned"),
            "state_changed_at": a.get("state_changed_at"),
            "last_activity": (act or {}).get("action"),
            "last_activity_at": (act or {}).get("created_at"),
        })
    return {"items": items, "total": total, "page": page, "limit": limit}


# ---------------------- Admin assignment details ----------------------


@router.get("/assignments/details")
async def assignment_details(
    employee_id: str = Query(..., description="Employee id (string ObjectId)"),
    job_id: str = Query(..., description="Job id (string ObjectId)"),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    """Detailed audit of a specific job assignment for an employee.
    Includes timeline events, time entries, and rollups. Admin-like roles only.
    """
    if not is_admin_like(str(current_user.get("role", ""))):
        raise HTTPException(status_code=403, detail="Forbidden")
    company_id = ObjectId(current_user["company_id"])
    emp_oid = ObjectId(employee_id)
    job_oid = ObjectId(job_id)

    # Core docs
    job = await db["jobs"].find_one({"_id": job_oid, "company_id": company_id})
    emp = await db["employees"].find_one({"_id": emp_oid, "company_id": company_id})
    assign = await db["job_assignments"].find_one({"company_id": company_id, "job_id": job_oid, "employee_id": emp_oid})

    # Timeline events
    events_cursor = db["assignment_activity"].find({
        "company_id": company_id,
        "job_id": job_oid,
        "employee_id": emp_oid,
    }).sort("created_at", 1)
    events: list[dict] = []
    actor_ids: set[ObjectId] = set()
    async for ev in events_cursor:
        actor_id = ev.get("actor_user_id")
        if actor_id:
            actor_ids.add(actor_id)
        events.append({
            "action": ev.get("action"),
            "created_at": ev.get("created_at"),
            "note": ev.get("note"),
            "actor_user_id": str(actor_id) if actor_id else None,
        })
    # Resolve actor names
    actors: dict[str, str] = {}
    if actor_ids:
        cursor = db["users"].find({"_id": {"$in": list(actor_ids)}})
        async for u in cursor:
            actors[str(u["_id"])]= f"{u.get('first_name','')} {u.get('last_name','')}".strip() or u.get("email","user")
    for ev in events:
        ev["actor_name"] = actors.get(ev["actor_user_id"] or "", None)

    # Time entries for this job/employee
    q = {"company_id": company_id, "job_id": job_oid, "employee_id": emp_oid}
    ten_cursor = db["time_entries"].find(q).sort("start_ts", 1)
    entries: list[dict] = []
    totals = {"entries": 0, "minutes": 0, "break_minutes": 0, "paused_minutes": 0, "amount": 0.0}
    async for t in ten_cursor:
        # Compute duration if missing
        if t.get("duration_minutes") is None and t.get("end_ts"):
            dur = max(0, int(((t.get("end_ts") - t.get("start_ts")).total_seconds() // 60) - int(t.get("break_minutes", 0)) - int(t.get("paused_minutes", 0))))
        elif t.get("is_active"):
            paused_total = int(t.get("paused_minutes", 0))
            if t.get("paused_started_at"):
                paused_total += max(0, int(((datetime.utcnow() - t.get("paused_started_at")).total_seconds() // 60)))
            dur = max(0, int(((datetime.utcnow() - t.get("start_ts")).total_seconds() // 60) - int(t.get("break_minutes", 0)) - paused_total))
        else:
            dur = int(t.get("duration_minutes") or 0)
        # Effective rate
        rate = await _get_effective_rate(db, company_id, t["job_id"], t["employee_id"])
        amount = round((float(dur) / 60.0) * rate, 2) if dur else 0.0
        totals["entries"] += 1
        totals["minutes"] += int(dur)
        totals["break_minutes"] += int(t.get("break_minutes", 0))
        totals["paused_minutes"] += int(t.get("paused_minutes", 0))
        totals["amount"] = round(totals["amount"] + amount, 2)
        entries.append({
            "id": str(t["_id"]),
            "start_ts": t.get("start_ts"),
            "end_ts": t.get("end_ts"),
            "break_minutes": int(t.get("break_minutes", 0)),
            "paused_minutes": int(t.get("paused_minutes", 0)),
            "duration_minutes": dur or None,
            "is_active": bool(t.get("is_active", False)),
            "on_break": bool(t.get("break_started_at") is not None),
            "on_pause": bool(t.get("paused_started_at") is not None),
            "state": ("abandoned" if (t.get("end_ts") and t.get("abandoned_reason")) else ("completed" if t.get("end_ts") else ("paused" if t.get("paused_started_at") else "active"))),
            "note": t.get("note"),
            "pause_reason": t.get("pause_last_reason"),
            "abandoned_reason": t.get("abandoned_reason"),
            "planned_resume_at": t.get("planned_resume_at"),
            "rate": rate,
            "amount": amount,
        })

    # Build response
    return {
        "job": {"id": job_id, "name": (job or {}).get("name", ""), "client_name": (job or {}).get("client_name")},
        "employee": {"id": employee_id, "name": f"{(emp or {}).get('first_name','')} {(emp or {}).get('last_name','')}".strip() or (emp or {}).get("email")},
        "assignment": {
            "state": (assign or {}).get("state", "assigned"),
            "state_changed_at": (assign or {}).get("state_changed_at"),
            "created_at": (assign or {}).get("created_at"),
            "updated_at": (assign or {}).get("updated_at"),
        },
        "timeline": events,
        "entries": entries,
        "totals": totals,
    }


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
    # If assignments exist for this job, enforce assignment for non-admin users
    if not is_admin_like(str(current_user.get("role", ""))):
        has_assign = await db["job_assignments"].count_documents({"company_id": company_id, "job_id": job_oid})
        if has_assign:
            mine = await db["job_assignments"].count_documents({"company_id": company_id, "job_id": job_oid, "employee_id": employee_id})
            if mine == 0:
                raise HTTPException(status_code=403, detail="You are not assigned to this job")
    doc = {
        "company_id": company_id,
        "employee_id": employee_id,
        "job_id": job_oid,
        "date": _start_of_day(now),
        "start_ts": now,
        "end_ts": None,
        "break_minutes": 0,
        "break_started_at": None,
        "paused_minutes": 0,
        "paused_started_at": None,
        "pause_last_reason": None,
        "planned_resume_at": None,
        "abandoned_reason": None,
        "is_active": True,
        "note": payload.note,
        "source": "clock",
        "created_at": now,
        "updated_at": now,
    }
    res = await db["time_entries"].insert_one(doc)
    rate = await _get_effective_rate(db, company_id, job_oid, employee_id)
    # Update assignment state to in_progress and log activity
    try:
        now2 = datetime.utcnow()
        await db["job_assignments"].update_one(
            {"company_id": company_id, "job_id": job_oid, "employee_id": employee_id},
            {"$set": {"state": "in_progress", "state_changed_at": now2, "updated_at": now2}},
        )
        await db["assignment_activity"].insert_one({
            "company_id": company_id,
            "employee_id": employee_id,
            "job_id": job_oid,
            "job_name": job.get("name"),
            "action": "started",
            "actor_user_id": ObjectId(current_user["id"]),
            "created_at": now2,
        })
    except Exception:
        pass
    return TimeEntryOut(
        id=str(res.inserted_id),
        job_id=str(job_oid),
        employee_id=str(employee_id),
        start_ts=doc["start_ts"],
        end_ts=None,
        break_minutes=0,
        paused_minutes=0,
        is_active=True,
        on_break=False,
        on_pause=False,
        state="active",
        note=doc.get("note"),
        planned_resume_at=None,
        rate=rate,
    )


@router.post("/entries/break/start", response_model=TimeEntryOut)
async def break_start(db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    company_id = ObjectId(current_user["company_id"])
    employee_id = await _get_current_employee_id(db, current_user)
    ent = await db["time_entries"].find_one({"company_id": company_id, "employee_id": employee_id, "is_active": True})
    if not ent:
        raise HTTPException(status_code=400, detail="No active time entry to start a break")
    if ent.get("paused_started_at"):
        raise HTTPException(status_code=400, detail="Cannot start a break while job is paused")
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
        paused_minutes=int(ent.get("paused_minutes", 0)),
        is_active=True,
        on_break=True,
        on_pause=False,
        note=ent.get("note"),
        planned_resume_at=ent.get("planned_resume_at"),
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
        paused_minutes=int(ent.get("paused_minutes", 0)),
        is_active=True,
        on_break=False,
        on_pause=bool(ent.get("paused_started_at")),
        note=ent.get("note"),
        planned_resume_at=ent.get("planned_resume_at"),
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
    # If currently paused, end pause
    if ent.get("paused_started_at"):
        delta = now - ent["paused_started_at"]
        add_minutes = max(0, int(delta.total_seconds() // 60))
        ent["paused_minutes"] = int(ent.get("paused_minutes", 0)) + add_minutes
        ent["paused_started_at"] = None
    duration_minutes = max(0, int((now - ent["start_ts"]).total_seconds() // 60) - int(ent.get("break_minutes", 0)))
    # Subtract paused time as well
    duration_minutes = max(0, duration_minutes - int(ent.get("paused_minutes", 0)))
    await db["time_entries"].update_one(
        {"_id": ent["_id"]},
        {"$set": {"end_ts": now, "is_active": False, "break_minutes": int(ent.get("break_minutes", 0)), "duration_minutes": duration_minutes, "updated_at": now, "break_started_at": None}},
    )
    ent = await db["time_entries"].find_one({"_id": ent["_id"]})
    rate = await _get_effective_rate(db, company_id, ent["job_id"], employee_id)
    amount = round((float(duration_minutes) / 60.0) * rate, 2) if duration_minutes else 0.0
    # Update assignment state to done and log activity
    try:
        now2 = datetime.utcnow()
        await db["job_assignments"].update_one(
            {"company_id": company_id, "job_id": ent["job_id"], "employee_id": employee_id},
            {"$set": {"state": "done", "state_changed_at": now2, "updated_at": now2}},
        )
        job = await db["jobs"].find_one({"_id": ent["job_id"], "company_id": company_id})
        await db["assignment_activity"].insert_one({
            "company_id": company_id,
            "employee_id": employee_id,
            "job_id": ent["job_id"],
            "job_name": (job or {}).get("name"),
            "action": "done",
            "actor_user_id": ObjectId(current_user["id"]),
            "created_at": now2,
        })
    except Exception:
        pass
    return TimeEntryOut(
        id=str(ent["_id"]),
        job_id=str(ent["job_id"]),
        employee_id=str(employee_id),
        start_ts=ent.get("start_ts"),
        end_ts=ent.get("end_ts"),
        break_minutes=int(ent.get("break_minutes", 0)),
        paused_minutes=int(ent.get("paused_minutes", 0)),
        is_active=False,
        on_break=False,
        on_pause=False,
        duration_minutes=int(ent.get("duration_minutes", 0)),
        note=ent.get("note"),
        planned_resume_at=None,
        rate=rate,
        amount=amount,
    )


@router.post("/entries/pause", response_model=TimeEntryOut)
async def pause_job(payload: PausePayload, db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    company_id = ObjectId(current_user["company_id"])
    employee_id = await _get_current_employee_id(db, current_user)
    ent = await db["time_entries"].find_one({"company_id": company_id, "employee_id": employee_id, "is_active": True})
    if not ent:
        raise HTTPException(status_code=400, detail="No active time entry to pause")
    if ent.get("paused_started_at"):
        raise HTTPException(status_code=400, detail="Job already paused")
    now = datetime.utcnow()
    # End break if on break
    if ent.get("break_started_at"):
        delta = now - ent["break_started_at"]
        add_minutes = max(0, int(delta.total_seconds() // 60))
        ent["break_minutes"] = int(ent.get("break_minutes", 0)) + add_minutes
        ent["break_started_at"] = None
    await db["time_entries"].update_one({"_id": ent["_id"]}, {"$set": {
        "paused_started_at": now,
        "pause_last_reason": (payload.reason or None),
        "planned_resume_at": (payload.resume_at or None),
        "updated_at": now,
    }})
    ent = await db["time_entries"].find_one({"_id": ent["_id"]})
    rate = await _get_effective_rate(db, company_id, ent["job_id"], employee_id)
    # Update assignment state and log
    try:
        job = await db["jobs"].find_one({"_id": ent["job_id"], "company_id": company_id})
        await db["job_assignments"].update_one(
            {"company_id": company_id, "job_id": ent["job_id"], "employee_id": employee_id},
            {"$set": {"state": "paused", "state_changed_at": now, "updated_at": now}},
        )
        await db["assignment_activity"].insert_one({
            "company_id": company_id,
            "employee_id": employee_id,
            "job_id": ent["job_id"],
            "job_name": (job or {}).get("name"),
            "action": "paused",
            "actor_user_id": ObjectId(current_user["id"]),
            "note": payload.reason,
            "created_at": now,
        })
    except Exception:
        pass
    return TimeEntryOut(
        id=str(ent["_id"]),
        job_id=str(ent["job_id"]),
        employee_id=str(employee_id),
        start_ts=ent.get("start_ts"),
        end_ts=ent.get("end_ts"),
        break_minutes=int(ent.get("break_minutes", 0)),
        paused_minutes=int(ent.get("paused_minutes", 0)),
        is_active=True,
        on_break=False,
        on_pause=True,
        state="paused",
        note=ent.get("note"),
        planned_resume_at=ent.get("planned_resume_at"),
        pause_reason=ent.get("pause_last_reason"),
        rate=rate,
    )


@router.post("/entries/resume", response_model=TimeEntryOut)
async def resume_job(db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    company_id = ObjectId(current_user["company_id"])
    employee_id = await _get_current_employee_id(db, current_user)
    ent = await db["time_entries"].find_one({"company_id": company_id, "employee_id": employee_id, "is_active": True})
    if not ent or not ent.get("paused_started_at"):
        raise HTTPException(status_code=400, detail="No paused time entry to resume")
    now = datetime.utcnow()
    delta = now - ent["paused_started_at"]
    add_minutes = max(0, int(delta.total_seconds() // 60))
    new_total = int(ent.get("paused_minutes", 0)) + add_minutes
    await db["time_entries"].update_one({"_id": ent["_id"]}, {"$set": {"paused_minutes": new_total, "paused_started_at": None, "planned_resume_at": None, "updated_at": now}})
    ent = await db["time_entries"].find_one({"_id": ent["_id"]})
    rate = await _get_effective_rate(db, company_id, ent["job_id"], employee_id)
    # Update assignment state and log
    try:
        job = await db["jobs"].find_one({"_id": ent["job_id"], "company_id": company_id})
        await db["job_assignments"].update_one(
            {"company_id": company_id, "job_id": ent["job_id"], "employee_id": employee_id},
            {"$set": {"state": "in_progress", "state_changed_at": now, "updated_at": now}},
        )
        await db["assignment_activity"].insert_one({
            "company_id": company_id,
            "employee_id": employee_id,
            "job_id": ent["job_id"],
            "job_name": (job or {}).get("name"),
            "action": "resumed",
            "actor_user_id": ObjectId(current_user["id"]),
            "created_at": now,
        })
    except Exception:
        pass
    return TimeEntryOut(
        id=str(ent["_id"]),
        job_id=str(ent["job_id"]),
        employee_id=str(employee_id),
        start_ts=ent.get("start_ts"),
        end_ts=ent.get("end_ts"),
        break_minutes=int(ent.get("break_minutes", 0)),
        paused_minutes=int(ent.get("paused_minutes", 0)),
        is_active=True,
        on_break=False,
        on_pause=False,
        state="active",
        note=ent.get("note"),
        planned_resume_at=None,
        pause_reason=None,
        rate=rate,
    )


@router.post("/entries/abandon", response_model=TimeEntryOut)
async def abandon_job(payload: AbandonPayload, db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    company_id = ObjectId(current_user["company_id"])
    employee_id = await _get_current_employee_id(db, current_user)
    ent = await db["time_entries"].find_one({"company_id": company_id, "employee_id": employee_id, "is_active": True})
    if not ent:
        raise HTTPException(status_code=400, detail="No active time entry to abandon")
    now = datetime.utcnow()
    # End break if on break
    if ent.get("break_started_at"):
        delta = now - ent["break_started_at"]
        add_minutes = max(0, int(delta.total_seconds() // 60))
        ent["break_minutes"] = int(ent.get("break_minutes", 0)) + add_minutes
        ent["break_started_at"] = None
    # End pause if paused
    if ent.get("paused_started_at"):
        delta = now - ent["paused_started_at"]
        add_minutes = max(0, int(delta.total_seconds() // 60))
        ent["paused_minutes"] = int(ent.get("paused_minutes", 0)) + add_minutes
        ent["paused_started_at"] = None
    duration_minutes = max(0, int((now - ent["start_ts"]).total_seconds() // 60) - int(ent.get("break_minutes", 0)) - int(ent.get("paused_minutes", 0)))
    await db["time_entries"].update_one(
        {"_id": ent["_id"]},
        {"$set": {"end_ts": now, "is_active": False, "break_minutes": int(ent.get("break_minutes", 0)), "paused_minutes": int(ent.get("paused_minutes", 0)), "duration_minutes": duration_minutes, "updated_at": now, "abandoned_reason": (payload.reason or None)}},
    )
    ent = await db["time_entries"].find_one({"_id": ent["_id"]})
    rate = await _get_effective_rate(db, company_id, ent["job_id"], employee_id)
    amount = round((float(duration_minutes) / 60.0) * rate, 2) if duration_minutes else 0.0
    # Update assignment state and log
    try:
        job = await db["jobs"].find_one({"_id": ent["job_id"], "company_id": company_id})
        await db["job_assignments"].update_one(
            {"company_id": company_id, "job_id": ent["job_id"], "employee_id": employee_id},
            {"$set": {"state": "canceled", "state_changed_at": now, "updated_at": now}},
        )
        await db["assignment_activity"].insert_one({
            "company_id": company_id,
            "employee_id": employee_id,
            "job_id": ent["job_id"],
            "job_name": (job or {}).get("name"),
            "action": "abandoned",
            "actor_user_id": ObjectId(current_user["id"]),
            "note": payload.reason,
            "created_at": now,
        })
    except Exception:
        pass
    return TimeEntryOut(
        id=str(ent["_id"]),
        job_id=str(ent["job_id"]),
        employee_id=str(employee_id),
        start_ts=ent.get("start_ts"),
        end_ts=ent.get("end_ts"),
        break_minutes=int(ent.get("break_minutes", 0)),
        paused_minutes=int(ent.get("paused_minutes", 0)),
        is_active=False,
        on_break=False,
        on_pause=False,
        state="abandoned",
        duration_minutes=int(ent.get("duration_minutes", 0)),
        note=ent.get("note"),
        planned_resume_at=None,
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
        # Prefer stored duration; compute from timestamps if missing (for both active and completed entries)
        dur_val = doc.get("duration_minutes")
        if isinstance(dur_val, int) and dur_val > 0:
            dur = int(dur_val)
        else:
            if doc.get("end_ts"):
                dur = max(0, int(((doc.get("end_ts") - doc.get("start_ts")).total_seconds() // 60) - int(doc.get("break_minutes", 0)) - int(doc.get("paused_minutes", 0))))
            elif doc.get("is_active"):
                # If paused right now, add current paused span to paused total for display purposes
                paused_total = int(doc.get("paused_minutes", 0))
                if doc.get("paused_started_at"):
                    paused_total += max(0, int(((datetime.utcnow() - doc.get("paused_started_at")).total_seconds() // 60)))
                dur = max(0, int(((datetime.utcnow() - doc.get("start_ts")).total_seconds() // 60) - int(doc.get("break_minutes", 0)) - paused_total))
            else:
                dur = 0
        amount = round((float(dur) / 60.0) * rate, 2) if dur else 0.0
        items.append({
            "id": str(doc["_id"]),
            "job_id": str(doc.get("job_id")),
            "employee_id": str(doc.get("employee_id")),
            "start_ts": doc.get("start_ts"),
            "end_ts": doc.get("end_ts"),
            "break_minutes": int(doc.get("break_minutes", 0)),
            "paused_minutes": int(doc.get("paused_minutes", 0)),
            "is_active": bool(doc.get("is_active", False)),
            "on_break": bool(doc.get("break_started_at") is not None),
            "on_pause": bool(doc.get("paused_started_at") is not None),
            "state": ("abandoned" if (doc.get("end_ts") and doc.get("abandoned_reason")) else ("completed" if doc.get("end_ts") else ("paused" if doc.get("paused_started_at") else "active"))),
            "planned_resume_at": doc.get("planned_resume_at"),
            "pause_reason": doc.get("pause_last_reason"),
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
