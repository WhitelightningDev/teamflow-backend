import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import Header, HTTPException, status
from bson import ObjectId

from app.core.config import settings
from app.db.mongo import get_mongo_db


ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    _ = expires_delta or timedelta(minutes=60)
    token = secrets.token_urlsafe(32)
    return f"tok_{token}"


def create_jwt(payload: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = payload.copy()
    if expires_delta is None:
        expires_delta = timedelta(hours=12)
    exp = datetime.utcnow() + expires_delta
    to_encode.update({"exp": exp})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    payload = decode_jwt(token)
    uid = payload.get("sub")
    company_id = payload.get("company_id")
    if not uid or not company_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    db = get_mongo_db()
    user = await db["users"].find_one({"_id": ObjectId(uid)})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return {
        "id": str(user["_id"]),
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "email": user.get("email", ""),
        "company_id": str(company_id),
        "role": user.get("role", "user"),
    }


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    # Placeholder implementation: returns a random token string
    _ = expires_delta or timedelta(minutes=15)
    token = secrets.token_urlsafe(32)
    # In a real setup, you would sign a JWT here with SECRET_KEY
    return f"tok_{token}"
