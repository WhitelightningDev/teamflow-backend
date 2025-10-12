from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongo import get_mongo_db
from app.core.security import get_current_user, hash_password, verify_password, create_jwt
from app.schemas.auth_schema import UserIn, LoginIn, UserOut, AuthResponse, ForgotPasswordIn, ResetPasswordIn
from app.utils.email import send_password_reset_email
import secrets, hashlib
from app.schemas.invite_schema import AcceptInviteIn
from app.core.config import settings
import httpx

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


def _external_base(request: Request) -> str:
    if settings.BACKEND_EXTERNAL_BASE_URL:
        return settings.BACKEND_EXTERNAL_BASE_URL.rstrip('/')
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    return f"{proto}://{host}" if host else str(request.base_url).rstrip('/')


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


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordIn, db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    """Request a password reset link. Always returns success to avoid user enumeration."""
    user = await db["users"].find_one({"email": payload.email})
    if user:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = datetime.utcnow()
        expires = now + timedelta(hours=24)
        await db["password_resets"].insert_one({
            "user_id": user["_id"],
            "email": user["email"],
            "token_hash": token_hash,
            "used": False,
            "created_at": now,
            "expires_at": expires,
        })
        # Build reset URL
        from app.core.config import settings as cfg
        base = (cfg.FRONTEND_BASE_URL or "").rstrip('/') or "http://localhost:5173"
        url = f"{base}/reset-password?token={token}"
        try:
            send_password_reset_email(to=user["email"], reset_url=url, company_name="TeamFlow", first_name=user.get("first_name"))
        except Exception:
            # Email failures are non-fatal to avoid leaking existence
            pass
    return {"status": "ok"}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordIn, db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    rec = await db["password_resets"].find_one({"token_hash": token_hash})
    if not rec or rec.get("used") or (rec.get("expires_at") and rec["expires_at"] < datetime.utcnow()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")
    user = await db["users"].find_one({"_id": rec["user_id"], "email": rec["email"]})
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")
    await db["users"].update_one({"_id": user["_id"]}, {"$set": {"password_hash": hash_password(payload.new_password), "updated_at": datetime.utcnow()}})
    await db["password_resets"].update_one({"_id": rec["_id"]}, {"$set": {"used": True, "used_at": datetime.utcnow()}})
    # Invalidate other outstanding reset tokens for this user
    try:
        await db["password_resets"].update_many({"user_id": user["_id"], "used": False}, {"$set": {"used": True, "used_at": datetime.utcnow()}})
    except Exception:
        pass
    return {"status": "reset"}


# ---------------------- OAuth: Google ----------------------


@router.get("/oauth/google/start")
async def google_oauth_start(request: Request, next: str = "/dashboard", db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=400, detail="Google OAuth not configured")
    state = secrets.token_urlsafe(32)
    await db["oauth_states"].insert_one({"state": state, "provider": "google", "next": next, "created_at": datetime.utcnow()})
    redirect_uri = f"{_external_base(request)}/api/v1/auth/oauth/google/callback"
    qp = httpx.QueryParams({"redirect_uri": redirect_uri})
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={qp['redirect_uri']}"
        "&response_type=code&scope=openid%20email%20profile"
        f"&state={state}"
        "&access_type=offline&prompt=consent"
    )
    return RedirectResponse(auth_url, status_code=302)


@router.get("/oauth/google/callback")
async def google_oauth_callback(request: Request, code: str = "", state: str = "", db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    rec = await db["oauth_states"].find_one({"state": state, "provider": "google"})
    if not rec:
        raise HTTPException(status_code=400, detail="Invalid state")
    try:
        await db["oauth_states"].delete_one({"_id": rec["_id"]})
    except Exception:
        pass
    redirect_uri = f"{_external_base(request)}/api/v1/auth/oauth/google/callback"
    token_url = "https://oauth2.googleapis.com/token"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(token_url, data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="OAuth exchange failed")
        tok = resp.json()
        access_token = tok.get("access_token")
        uinfo = {}
        try:
            ures = await client.get("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {access_token}"})
            if ures.status_code == 200:
                uinfo = ures.json()
        except Exception:
            pass
    email = (uinfo.get("email") if uinfo else None)
    first_name = (uinfo.get("given_name") if uinfo else None) or ""
    last_name = (uinfo.get("family_name") if uinfo else None) or ""
    if not email:
        raise HTTPException(status_code=400, detail="Email not available from provider")
    user = await db["users"].find_one({"email": email})
    now = datetime.utcnow()
    if not user:
        company = {"name": f"{email.split('@')[-1]}", "created_at": now, "updated_at": now, "timezone": "UTC"}
        cres = await db["companies"].insert_one(company)
        user_doc = {
            "email": email,
            "password_hash": hash_password(secrets.token_urlsafe(16)),
            "first_name": first_name,
            "last_name": last_name,
            "role": "admin",
            "company_id": cres.inserted_id,
            "created_at": now,
            "updated_at": now,
            "is_active": True,
            "last_login": now,
            "profile_photo_url": None,
            "oauth_provider": "google",
        }
        ures = await db["users"].insert_one(user_doc)
        user = await db["users"].find_one({"_id": ures.inserted_id})
    else:
        await db["users"].update_one({"_id": user["_id"]}, {"$set": {"last_login": now, "oauth_provider": "google"}})
    token = create_jwt({"sub": str(user["_id"]), "company_id": str(user["company_id"])})
    next_path = rec.get("next") or "/dashboard"
    qp_next = httpx.QueryParams({"n": next_path})
    dest = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/oauth/callback?token={token}&next={qp_next['n']}"
    return RedirectResponse(dest, status_code=302)


# ---------------------- OAuth: Microsoft ----------------------


@router.get("/oauth/microsoft/start")
async def ms_oauth_start(request: Request, next: str = "/dashboard", db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    if not settings.MS_CLIENT_ID or not settings.MS_CLIENT_SECRET:
        raise HTTPException(status_code=400, detail="Microsoft OAuth not configured")
    state = secrets.token_urlsafe(32)
    await db["oauth_states"].insert_one({"state": state, "provider": "microsoft", "next": next, "created_at": datetime.utcnow()})
    redirect_uri = f"{_external_base(request)}/api/v1/auth/oauth/microsoft/callback"
    qp = httpx.QueryParams({"redirect_uri": redirect_uri})
    auth_url = (
        "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        f"?client_id={settings.MS_CLIENT_ID}"
        f"&redirect_uri={qp['redirect_uri']}"
        "&response_type=code&scope=openid%20email%20profile&response_mode=query"
        f"&state={state}"
    )
    return RedirectResponse(auth_url, status_code=302)


@router.get("/oauth/microsoft/callback")
async def ms_oauth_callback(request: Request, code: str = "", state: str = "", db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    rec = await db["oauth_states"].find_one({"state": state, "provider": "microsoft"})
    if not rec:
        raise HTTPException(status_code=400, detail="Invalid state")
    try:
        await db["oauth_states"].delete_one({"_id": rec["_id"]})
    except Exception:
        pass
    redirect_uri = f"{_external_base(request)}/api/v1/auth/oauth/microsoft/callback"
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(token_url, data={
            "client_id": settings.MS_CLIENT_ID,
            "client_secret": settings.MS_CLIENT_SECRET,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="OAuth exchange failed")
        tok = resp.json()
        access_token = tok.get("access_token")
        uinfo = {}
        try:
            ures = await client.get("https://graph.microsoft.com/oidc/userinfo", headers={"Authorization": f"Bearer {access_token}"})
            if ures.status_code == 200:
                uinfo = ures.json()
        except Exception:
            pass
    email = (uinfo.get("email") or uinfo.get("preferred_username")) if uinfo else None
    first_name = (uinfo.get("given_name") if uinfo else None) or ""
    last_name = (uinfo.get("family_name") if uinfo else None) or ""
    if not email:
        raise HTTPException(status_code=400, detail="Email not available from provider")
    user = await db["users"].find_one({"email": email})
    now = datetime.utcnow()
    if not user:
        company = {"name": f"{email.split('@')[-1]}", "created_at": now, "updated_at": now, "timezone": "UTC"}
        cres = await db["companies"].insert_one(company)
        user_doc = {
            "email": email,
            "password_hash": hash_password(secrets.token_urlsafe(16)),
            "first_name": first_name,
            "last_name": last_name,
            "role": "admin",
            "company_id": cres.inserted_id,
            "created_at": now,
            "updated_at": now,
            "is_active": True,
            "last_login": now,
            "profile_photo_url": None,
            "oauth_provider": "microsoft",
        }
        ures = await db["users"].insert_one(user_doc)
        user = await db["users"].find_one({"_id": ures.inserted_id})
    else:
        await db["users"].update_one({"_id": user["_id"]}, {"$set": {"last_login": now, "oauth_provider": "microsoft"}})
    token = create_jwt({"sub": str(user["_id"]), "company_id": str(user["company_id"])})
    next_path = rec.get("next") or "/dashboard"
    qp_next = httpx.QueryParams({"n": next_path})
    dest = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/oauth/callback?token={token}&next={qp_next['n']}"
    return RedirectResponse(dest, status_code=302)
