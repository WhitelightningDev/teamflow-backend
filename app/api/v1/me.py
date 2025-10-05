from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import get_current_user
from app.db.mongo import get_mongo_db


router = APIRouter(prefix="/me", tags=["me"])


@router.get("/profile")
async def my_profile(db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    emp = await db["employees"].find_one({
        "company_id": ObjectId(current_user["company_id"]),
        "user_id": ObjectId(current_user["id"]),
    })
    return {"user": current_user, "employee": {"id": str(emp["_id"]) if emp else None, **({k: emp.get(k) for k in ("first_name","last_name","email","phone","address","emergency_contact")} if emp else {})}}


@router.patch("/profile")
async def update_my_profile(payload: dict, db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    emp = await db["employees"].find_one({
        "company_id": ObjectId(current_user["company_id"]),
        "user_id": ObjectId(current_user["id"]),
    })
    if not emp:
        return {"status": "no_employee"}
    update = {k: v for k, v in payload.items() if k in {"phone","address","emergency_contact"}}
    update["updated_at"] = datetime.utcnow()
    await db["employees"].update_one({"_id": emp["_id"]}, {"$set": update})
    return {"status": "ok"}


@router.get("/leaves/balances")
async def my_leave_balances(db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    emp = await db["employees"].find_one({
        "company_id": ObjectId(current_user["company_id"]),
        "user_id": ObjectId(current_user["id"]),
    })
    if not emp:
        return {"balances": {}}
    # Simple counts by leave_type for approved leaves in current year
    start_year = datetime(datetime.utcnow().year, 1, 1)
    q = {"company_id": ObjectId(current_user["company_id"]), "employee_id": emp["_id"], "status": "approved", "start_date": {"$gte": start_year}}
    cursor = db["leaves"].find(q)
    balances: dict[str, int] = {}
    async for l in cursor:
        lt = l.get("leave_type", "annual")
        days = 1
        try:
            sd = l.get("start_date"); ed = l.get("end_date")
            if sd and ed:
                days = max(1, int((ed - sd).days) + 1)
        except Exception:
            pass
        balances[lt] = balances.get(lt, 0) + days
    balances["totalDays"] = sum(v for k, v in balances.items() if k != "totalDays")
    return {"balances": balances}

