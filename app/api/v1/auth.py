from fastapi import APIRouter, Depends
from app.db.session import get_db
from app.core.security import create_access_token, get_current_user
from app.schemas.auth_schema import UserIn, LoginIn, UserOut, AuthResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
def register(payload: UserIn, db=Depends(get_db)):
    user = {
        "id": 1,
        "first_name": payload.first_name,
        "last_name": payload.last_name,
        "email": payload.email,
    }
    token = create_access_token(subject=str(user["id"]))
    return {"user": user, "token": token}


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginIn, db=Depends(get_db)):
    # Placeholder: accept any credentials and return a token
    user = {
        "id": 1,
        "first_name": "Demo",
        "last_name": "User",
        "email": payload.email,
    }
    token = create_access_token(subject=str(user["id"]))
    return {"user": user, "token": token}


@router.get("/me", response_model=UserOut)
def get_me(current_user=Depends(get_current_user), db=Depends(get_db)):
    return current_user

