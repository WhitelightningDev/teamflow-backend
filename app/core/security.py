import hashlib
import secrets
from datetime import datetime, timedelta


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

