from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import get_current_user
from app.db.mongo import get_mongo_db


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    read: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    q = {"user_id": ObjectId(current_user["id"])}
    if read is not None:
        q["read"] = bool(read)
    total = await db["notifications"].count_documents(q)
    cursor = db["notifications"].find(q).skip((page-1)*limit).limit(limit).sort("created_at", -1)
    items = []
    async for n in cursor:
        items.append({
            "id": str(n["_id"]),
            "type": n.get("type"),
            "payload": n.get("payload"),
            "read": bool(n.get("read", False)),
            "created_at": n.get("created_at"),
        })
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    await db["notifications"].update_one({
        "_id": ObjectId(notification_id),
        "user_id": ObjectId(current_user["id"]),
    }, {"$set": {"read": True}})
    return {"status": "ok"}

