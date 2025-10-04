from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, Path, HTTPException
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongo import get_mongo_db
from app.core.security import get_current_user
from app.schemas.leave_schema import (
    LeaveIn,
    LeaveOut,
    LeaveDecisionIn,
    LeaveListOut,
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
                "status": doc.get("status", "pending"),
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
        "status": doc.get("status", "pending"),
        "created_at": doc.get("created_at", datetime.utcnow()),
    }


@router.post("", response_model=LeaveOut)
async def create_leave(payload: LeaveIn, db: AsyncIOMotorDatabase = Depends(get_mongo_db), current_user=Depends(get_current_user)):
    now = datetime.utcnow()
    doc = payload.model_dump()
    doc.update({
        "company_id": ObjectId(current_user["company_id"]),
        "employee_id": ObjectId(str(doc["employee_id"])) if doc.get("employee_id") is not None else None,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
    })
    res = await db["leaves"].insert_one(doc)
    return {
        "id": str(res.inserted_id),
        **payload.model_dump(),
        "status": "pending",
        "created_at": now,
    }


@router.patch("/{leave_id}", response_model=LeaveOut)
async def decide_leave(
    payload: LeaveDecisionIn,
    leave_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    status_out = "approved" if payload.action == "approve" else "rejected"
    now = datetime.utcnow()
    await db["leaves"].update_one(
        {"_id": ObjectId(leave_id), "company_id": ObjectId(current_user["company_id"])},
        {"$set": {"status": status_out, "decided_on": now, "updated_at": now}},
    )
    doc = await db["leaves"].find_one({"_id": ObjectId(leave_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Leave not found")
    return {
        "id": str(doc["_id"]),
        "employee_id": str(doc.get("employee_id")),
        "leave_type": doc.get("leave_type", "annual"),
        "start_date": doc.get("start_date"),
        "end_date": doc.get("end_date"),
        "reason": doc.get("reason"),
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
