from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongo import get_mongo_db
from app.core.security import get_current_user, hash_password, verify_password, create_jwt
from app.schemas.auth_schema import UserIn, LoginIn, UserOut, AuthResponse
from app.schemas.invite_schema import AcceptInviteIn

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
async def register(payload: UserIn, db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    now = datetime.utcnow()
    # Create or find company by name
    company = await db["companies"].find_one({"name": payload.company_name})
    if not company:
        company_doc = {
            "name": payload.company_name,
            "address": "",
            "contact_email": payload.email,
            "created_at": now,
            "updated_at": now,
            "logo_url": None,
            "timezone": "UTC",
            "settings": {"notifications": {"email": True, "push": False}},
        }
        r = await db["companies"].insert_one(company_doc)
        company_id = r.inserted_id
    else:
        company_id = company["_id"]

    existing = await db["users"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user_doc = {
        "email": payload.email,
        "password_hash": hash_password(payload.password),
        "first_name": payload.first_name,
        "last_name": payload.last_name,
        "role": "admin",
        "company_id": company_id,
        "created_at": now,
        "updated_at": now,
        "is_active": True,
        "last_login": None,
        "profile_photo_url": None,
    }
    result = await db["users"].insert_one(user_doc)
    uid = result.inserted_id
    token = create_jwt({"sub": str(uid), "company_id": str(company_id)})
    user_out = {"id": str(uid), "first_name": payload.first_name, "last_name": payload.last_name, "email": payload.email, "role": "admin"}
    return {"user": user_out, "token": token}


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginIn, db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    user = await db["users"].find_one({"email": payload.email})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_jwt({"sub": str(user["_id"]), "company_id": str(user["company_id"])})
    user_out = {"id": str(user["_id"]), "first_name": user.get("first_name", ""), "last_name": user.get("last_name", ""), "email": user["email"], "role": user.get("role", "employee")}
    # Update last_login
    await db["users"].update_one({"_id": user["_id"]}, {"$set": {"last_login": datetime.utcnow()}})
    return {"user": user_out, "token": token}


@router.get("/me", response_model=UserOut)
async def get_me(current_user=Depends(get_current_user)):
    return current_user


@router.post("/accept-invite", response_model=AuthResponse)
async def accept_invite(payload: AcceptInviteIn, db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    inv = await db["invites"].find_one({"token": payload.token})
    if not inv:
        raise HTTPException(status_code=400, detail="Invalid token")
    if inv.get("used"):
        raise HTTPException(status_code=400, detail="Invite already used")
    if inv.get("expires_at") and inv["expires_at"] < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invite expired")

    employee = await db["employees"].find_one({"_id": inv["employee_id"], "company_id": inv["company_id"]})
    if not employee:
        raise HTTPException(status_code=400, detail="Employee not found")

    user = await db["users"].find_one({"email": inv["email"], "company_id": inv["company_id"]})
    now = datetime.utcnow()
    if not user:
        user_doc = {
            "email": inv["email"],
            "password_hash": hash_password(payload.password),
            "first_name": employee.get("first_name", ""),
            "last_name": employee.get("last_name", ""),
            "role": "employee",
            "company_id": inv["company_id"],
            "created_at": now,
            "updated_at": now,
            "is_active": True,
        }
        res = await db["users"].insert_one(user_doc)
        user_id = res.inserted_id
    else:
        user_id = user["_id"]
        await db["users"].update_one({"_id": user_id}, {"$set": {"password_hash": hash_password(payload.password), "updated_at": now}})

    # Link employee to user
    await db["employees"].update_one({"_id": inv["employee_id"]}, {"$set": {"user_id": user_id, "updated_at": now}})
    # Mark invite used
    await db["invites"].update_one({"_id": inv["_id"]}, {"$set": {"used": True, "used_at": now}})

    token = create_jwt({"sub": str(user_id), "company_id": str(inv["company_id"])})
    u = await db["users"].find_one({"_id": user_id})
    user_out = {"id": str(user_id), "first_name": u.get("first_name", ""), "last_name": u.get("last_name", ""), "email": u.get("email", ""), "role": u.get("role", "employee")}
    return {"user": user_out, "token": token}
