from datetime import datetime, date as _date
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import get_current_user
from app.core.rbac import require_roles, is_admin_like
from app.db.mongo import get_mongo_db


router = APIRouter(prefix="/attendance", tags=["attendance"])


def _start_of_day(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, dt.day)


async def _get_current_employee_id(db: AsyncIOMotorDatabase, user: dict) -> ObjectId:
    me = await db["employees"].find_one({
        "company_id": ObjectId(user["company_id"]),
        "user_id": ObjectId(user["id"]),
    })
    if not me:
        raise HTTPException(status_code=400, detail="No employee profile linked to your account")
    return me["_id"]


@router.post("/clock-in")
async def clock_in(db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    # derive employee_id
    employee_id = await _get_current_employee_id(db, current_user)
    today = _start_of_day(datetime.utcnow())
    q = {"company_id": ObjectId(current_user["company_id"]), "employee_id": employee_id, "date": today}
    att = await db["attendance"].find_one(q)
    now = datetime.utcnow()
    if att:
        # if already clocked in, return record
        if att.get("clock_in_ts"):
            return {"status": "ok", "record": {
                "id": str(att["_id"]),
                "date": att.get("date"),
                "clock_in_ts": att.get("clock_in_ts"),
                "clock_out_ts": att.get("clock_out_ts"),
            }}
        await db["attendance"].update_one(q, {"$set": {"clock_in_ts": now, "updated_at": now}})
        att = await db["attendance"].find_one(q)
    else:
        await db["attendance"].insert_one({
            "company_id": ObjectId(current_user["company_id"]),
            "employee_id": employee_id,
            "date": today,
            "clock_in_ts": now,
            "clock_out_ts": None,
            "created_at": now,
            "updated_at": now,
        })
        att = await db["attendance"].find_one(q)
    return {"status": "ok", "record": {
        "id": str(att["_id"]),
        "date": att.get("date"),
        "clock_in_ts": att.get("clock_in_ts"),
        "clock_out_ts": att.get("clock_out_ts"),
    }}


@router.post("/clock-out")
async def clock_out(db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    employee_id = await _get_current_employee_id(db, current_user)
    today = _start_of_day(datetime.utcnow())
    q = {"company_id": ObjectId(current_user["company_id"]), "employee_id": employee_id, "date": today}
    att = await db["attendance"].find_one(q)
    now = datetime.utcnow()
    if not att:
        raise HTTPException(status_code=400, detail="Not clocked in today")
    if att.get("clock_out_ts"):
        return {"status": "ok", "record": {
            "id": str(att["_id"]),
            "date": att.get("date"),
            "clock_in_ts": att.get("clock_in_ts"),
            "clock_out_ts": att.get("clock_out_ts"),
        }}
    await db["attendance"].update_one(q, {"$set": {"clock_out_ts": now, "updated_at": now}})
    att = await db["attendance"].find_one(q)
    return {"status": "ok", "record": {
        "id": str(att["_id"]),
        "date": att.get("date"),
        "clock_in_ts": att.get("clock_in_ts"),
        "clock_out_ts": att.get("clock_out_ts"),
    }}


@router.get("/me")
async def my_attendance(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    employee_id = await _get_current_employee_id(db, current_user)
    q: dict = {"company_id": ObjectId(current_user["company_id"]), "employee_id": employee_id}
    if from_:
        start = _start_of_day(datetime.fromisoformat(from_))
        q["date"] = {"$gte": start}
    if to:
        end = _start_of_day(datetime.fromisoformat(to))
        q.setdefault("date", {}).update({"$lte": end})
    total = await db["attendance"].count_documents(q)
    cursor = db["attendance"].find(q).skip((page-1)*limit).limit(limit).sort("date", -1)
    items = []
    async for doc in cursor:
        items.append({
            "id": str(doc["_id"]),
            "date": doc.get("date"),
            "clock_in_ts": doc.get("clock_in_ts"),
            "clock_out_ts": doc.get("clock_out_ts"),
        })
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.get("")
async def company_attendance(
    employee_id: Optional[str] = None,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    if not is_admin_like(str(current_user.get("role", ""))):
        raise HTTPException(status_code=403, detail="Forbidden")
    q: dict = {"company_id": ObjectId(current_user["company_id"])}
    if employee_id:
        q["employee_id"] = ObjectId(employee_id)
    if from_:
        start = _start_of_day(datetime.fromisoformat(from_))
        q["date"] = {"$gte": start}
    if to:
        end = _start_of_day(datetime.fromisoformat(to))
        q.setdefault("date", {}).update({"$lte": end})
    total = await db["attendance"].count_documents(q)
    cursor = db["attendance"].find(q).skip((page-1)*limit).limit(limit).sort("date", -1)
    items = []
    async for doc in cursor:
        items.append({
            "id": str(doc["_id"]),
            "employee_id": str(doc.get("employee_id")),
            "date": doc.get("date"),
            "clock_in_ts": doc.get("clock_in_ts"),
            "clock_out_ts": doc.get("clock_out_ts"),
        })
    return {"items": items, "total": total, "page": page, "limit": limit}

