from datetime import datetime
from fastapi import APIRouter, Depends
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongo import get_mongo_db
from app.core.security import get_current_user, verify_password, hash_password
from app.schemas.settings_schema import (
    ProfileOut,
    ProfileIn,
    PasswordChangeIn,
    CompanyOut,
    CompanyUpdate,
    NotificationSettingsOut,
    NotificationSettingsUpdate,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/profile", response_model=ProfileOut)
async def get_profile(current_user=Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    user = await db["users"].find_one({"_id": ObjectId(current_user["id"])})
    return {
        "id": current_user["id"],
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "email": user.get("email", ""),
        "title": user.get("title"),
        "phone": user.get("phone"),
        "timezone": user.get("timezone", "UTC"),
    }


@router.put("/profile", response_model=ProfileOut)
async def update_profile(payload: ProfileIn, current_user=Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    data = payload.model_dump()
    data["updated_at"] = datetime.utcnow()
    await db["users"].update_one({"_id": ObjectId(current_user["id"])}, {"$set": data})
    return {"id": current_user["id"], **payload.model_dump()}


@router.post("/password")
async def change_password(payload: PasswordChangeIn, current_user=Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    user = await db["users"].find_one({"_id": ObjectId(current_user["id"])})
    if not user or not verify_password(payload.current_password, user.get("password_hash", "")):
        return {"status": "invalid_current_password"}
    await db["users"].update_one({"_id": user["_id"]}, {"$set": {"password_hash": hash_password(payload.new_password), "updated_at": datetime.utcnow()}})
    return {"status": "changed"}


@router.get("/company", response_model=CompanyOut)
async def get_company_settings(current_user=Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    company = await db["companies"].find_one({"_id": ObjectId(current_user["company_id"])})
    return {
        "id": str(company["_id"]),
        "name": company.get("name", ""),
        "domain": company.get("domain", ""),
        "timezone": company.get("timezone", "UTC"),
    }


@router.patch("/company", response_model=CompanyOut)
async def update_company_settings(payload: CompanyUpdate, current_user=Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    update = payload.model_dump(exclude_unset=True)
    update["updated_at"] = datetime.utcnow()
    await db["companies"].update_one({"_id": ObjectId(current_user["company_id"])}, {"$set": update})
    company = await db["companies"].find_one({"_id": ObjectId(current_user["company_id"])})
    return {
        "id": str(company["_id"]),
        "name": company.get("name", ""),
        "domain": company.get("domain", ""),
        "timezone": company.get("timezone", "UTC"),
    }


@router.get("/notifications", response_model=NotificationSettingsOut)
async def get_notifications(current_user=Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    s = await db["settings"].find_one({"company_id": ObjectId(current_user["company_id"])})
    if not s:
        return {"email_notifications": True, "push_notifications": False}
    ns = s.get("notification_settings", {"email": True, "push": False})
    return {"email_notifications": bool(ns.get("email", True)), "push_notifications": bool(ns.get("push", False))}


@router.patch("/notifications", response_model=NotificationSettingsOut)
async def update_notifications(payload: NotificationSettingsUpdate, current_user=Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    patch = payload.model_dump(exclude_unset=True)
    s = await db["settings"].find_one({"company_id": ObjectId(current_user["company_id"])})
    ns = (s or {}).get("notification_settings", {"email": True, "push": False})
    if "email_notifications" in patch:
        ns["email"] = bool(patch["email_notifications"])
    if "push_notifications" in patch:
        ns["push"] = bool(patch["push_notifications"])
    await db["settings"].update_one(
        {"company_id": ObjectId(current_user["company_id"])},
        {"$set": {"notification_settings": ns, "updated_at": datetime.utcnow(), "created_at": s.get("created_at", datetime.utcnow())}},
        upsert=True,
    )
    return {"email_notifications": bool(ns.get("email", True)), "push_notifications": bool(ns.get("push", False))}
