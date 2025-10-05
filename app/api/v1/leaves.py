from typing import Optional
from datetime import datetime, date as _date
from fastapi import APIRouter, Depends, Query, Path, HTTPException
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongo import get_mongo_db
from app.core.security import get_current_user
from app.core.rbac import is_admin_like
from app.schemas.leave_schema import (
    LeaveIn,
    LeaveOut,
    LeaveDecisionIn,
    LeaveListOut,
    LeaveStatusIn,
)

router = APIRouter(prefix="/leaves", tags=["leaves"])


@router.get("", response_model=LeaveListOut)
async def list_leaves(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    status: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    q: dict = {"company_id": ObjectId(current_user["company_id"])}
    if status:
        q["status"] = status
    # Restrict employees to their own requests
    if str(current_user.get("role")) in {"employee", "staff"}:
        me = await db["employees"].find_one({
            "company_id": ObjectId(current_user["company_id"]),
            "user_id": ObjectId(current_user["id"]),
        })
        if me:
            q["employee_id"] = me["_id"]
    total = await db["leaves"].count_documents(q)
    cursor = db["leaves"].find(q).skip((page - 1) * size).limit(size).sort("created_at", -1)
    items = []
    async for doc in cursor:
        items.append(
            {
                "id": str(doc["_id"]),
                "employee_id": str(doc.get("employee_id")),
                "leave_type": doc.get("leave_type", "annual"),
                "start_date": doc.get("start_date"),
                "end_date": doc.get("end_date"),
                "reason": doc.get("reason"),
                "comment": doc.get("comment"),
                "status": doc.get("status", "requested"),
                "created_at": doc.get("created_at", datetime.utcnow()),
            }
        )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{leave_id}", response_model=LeaveOut)
async def get_leave(
    leave_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    doc = await db["leaves"].find_one({"_id": ObjectId(leave_id), "company_id": ObjectId(current_user["company_id"])})
    if not doc:
        raise HTTPException(status_code=404, detail="Leave not found")
    return {
        "id": str(doc["_id"]),
        "employee_id": str(doc.get("employee_id")),
        "leave_type": doc.get("leave_type", "annual"),
        "start_date": doc.get("start_date"),
        "end_date": doc.get("end_date"),
        "reason": doc.get("reason"),
        "comment": doc.get("comment"),
        "status": doc.get("status", "requested"),
        "created_at": doc.get("created_at", datetime.utcnow()),
    }


@router.post("", response_model=LeaveOut)
async def create_leave(payload: LeaveIn, db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    now = datetime.utcnow()
    doc = payload.model_dump()
    doc.update({
        "company_id": ObjectId(current_user["company_id"]),
        "status": "requested",
        "created_at": now,
        "updated_at": now,
    })
    # Derive employee_id for employee role; else allow provided ID
    if str(current_user.get("role")) in {"employee", "staff"}:
        me = await db["employees"].find_one({
            "company_id": ObjectId(current_user["company_id"]),
            "user_id": ObjectId(current_user["id"]),
        })
        if not me:
            raise HTTPException(status_code=400, detail="No employee profile linked to your account")
        doc["employee_id"] = me["_id"]
    else:
        if doc.get("employee_id") is not None:
            doc["employee_id"] = ObjectId(str(doc["employee_id"]))
        else:
            # For non-employee roles, an explicit employee_id must be provided
            raise HTTPException(status_code=400, detail="employee_id is required")
    # Convert date-only fields to datetimes for Mongo
    for k in ("start_date", "end_date"):
        v = doc.get(k)
        if isinstance(v, _date) and not isinstance(v, datetime):
            doc[k] = datetime(v.year, v.month, v.day)
    res = await db["leaves"].insert_one(doc)
    # Notify approvers
    roles = ["admin", "manager", "hr"]
    cursor = db["users"].find({"company_id": ObjectId(current_user["company_id"]), "role": {"$in": roles}})
    now = datetime.utcnow()
    async for u in cursor:
        await db["notifications"].insert_one({
            "user_id": u["_id"],
            "type": "leave_requested",
            "payload": {"leave_id": str(res.inserted_id)},
            "read": False,
            "created_at": now,
        })
    return {
        "id": str(res.inserted_id),
        "employee_id": str(doc.get("employee_id")),
        "leave_type": doc.get("leave_type", "annual"),
        "start_date": doc.get("start_date"),
        "end_date": doc.get("end_date"),
        "reason": doc.get("reason"),
        "status": "requested",
        "created_at": now,
    }


@router.patch("/{leave_id}", response_model=LeaveOut)
async def decide_leave(
    payload: LeaveStatusIn,
    leave_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    # Guard
    if str(current_user.get("role")) not in {"admin", "manager", "hr", "supervisor"}:
        return HTTPException(status_code=403, detail="Insufficient permissions")
    status_out = payload.status
    now = datetime.utcnow()
    await db["leaves"].update_one(
        {"_id": ObjectId(leave_id), "company_id": ObjectId(current_user["company_id"])},
        {"$set": {"status": status_out, "decided_on": now, "updated_at": now, "comment": payload.comment, "approver_id": ObjectId(current_user["id"]) }},
    )
    doc = await db["leaves"].find_one({"_id": ObjectId(leave_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Leave not found")
    # Notify owner when status changes
    emp = await db["employees"].find_one({"_id": doc.get("employee_id")})
    if emp and emp.get("user_id"):
        await db["notifications"].insert_one({
            "user_id": emp["user_id"],
            "type": "leave_status",
            "payload": {"leave_id": leave_id, "status": status_out, "comment": payload.comment},
            "read": False,
            "created_at": now,
        })
    return {
        "id": str(doc["_id"]),
        "employee_id": str(doc.get("employee_id")),
        "leave_type": doc.get("leave_type", "annual"),
        "start_date": doc.get("start_date"),
        "end_date": doc.get("end_date"),
        "reason": doc.get("reason"),
        "comment": doc.get("comment"),
        "status": doc.get("status", status_out),
        "created_at": doc.get("created_at", now),
    }


@router.delete("/{leave_id}")
async def delete_leave(
    leave_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    await db["leaves"].delete_one({"_id": ObjectId(leave_id), "company_id": ObjectId(current_user["company_id"])})
    return {"status": "deleted", "id": leave_id}
