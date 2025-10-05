from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import get_current_user
from app.core.rbac import is_admin_like
from app.db.mongo import get_mongo_db


router = APIRouter(prefix="/announcements", tags=["announcements"])


def _audiences_for_role(role: str) -> set[str]:
    role = str(role)
    allowed = {"company"}
    if role in {"admin", "manager", "hr"}:
        allowed.add("managers")
    if role in {"employee", "staff", "admin", "manager", "hr"}:
        allowed.add("employees")
    return allowed


@router.post("")
async def create_announcement(
    payload: dict,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    if not is_admin_like(str(current_user.get("role", ""))):
        raise HTTPException(status_code=403, detail="Forbidden")
    title = (payload.get("title") or '').strip()
    body = (payload.get("body") or '').strip()
    audience = payload.get("audience") or 'company'
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    if audience not in {"company", "managers", "employees"}:
        raise HTTPException(status_code=400, detail="invalid audience")
    now = datetime.utcnow()
    doc = {
        "company_id": ObjectId(current_user["company_id"]),
        "title": title,
        "body": body,
        "author_user_id": ObjectId(current_user["id"]),
        "audience": audience,
        "created_at": now,
        "updated_at": now,
    }
    res = await db["announcements"].insert_one(doc)
    # Emit notifications to audience
    roles = {
        "company": ["admin", "manager", "hr", "employee", "staff"],
        "managers": ["admin", "manager", "hr"],
        "employees": ["employee", "staff"],
    }[audience]
    cursor = db["users"].find({"company_id": ObjectId(current_user["company_id"]), "role": {"$in": roles}})
    async for u in cursor:
        await db["notifications"].insert_one({
            "user_id": u["_id"],
            "type": "announcement",
            "payload": {"title": title},
            "read": False,
            "created_at": now,
        })
    return {"id": str(res.inserted_id), **{k: v for k, v in doc.items() if k != "company_id"}}


@router.get("")
async def list_announcements(
    audience: Optional[str] = Query("me"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    allowed = _audiences_for_role(current_user.get("role", ""))
    q = {"company_id": ObjectId(current_user["company_id"])}
    if audience and audience != "me":
        if audience not in {"company", "managers", "employees"}:
            raise HTTPException(status_code=400, detail="invalid audience")
        q["audience"] = audience
    else:
        q["audience"] = {"$in": list(allowed)}
    total = await db["announcements"].count_documents(q)
    cursor = db["announcements"].find(q).skip((page-1)*limit).limit(limit).sort("created_at", -1)
    items = []
    async for a in cursor:
        items.append({
            "id": str(a["_id"]),
            "title": a.get("title"),
            "body": a.get("body"),
            "audience": a.get("audience"),
            "created_at": a.get("created_at"),
        })
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.delete("/{announcement_id}")
async def delete_announcement(
    announcement_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    if not is_admin_like(str(current_user.get("role", ""))):
        raise HTTPException(status_code=403, detail="Forbidden")
    await db["announcements"].delete_one({
        "_id": ObjectId(announcement_id),
        "company_id": ObjectId(current_user["company_id"]),
    })
    return {"status": "deleted", "id": announcement_id}

