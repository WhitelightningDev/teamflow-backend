from fastapi import APIRouter, Depends
from app.db.session import get_db
from app.core.security import get_current_user
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
def get_profile(current_user=Depends(get_current_user), db=Depends(get_db)):
    return {
        "id": current_user["id"],
        "first_name": current_user["first_name"],
        "last_name": current_user["last_name"],
        "email": current_user["email"],
        "title": "Engineer",
        "phone": None,
        "timezone": "UTC",
    }


@router.put("/profile", response_model=ProfileOut)
def update_profile(payload: ProfileIn, current_user=Depends(get_current_user), db=Depends(get_db)):
    return {
        "id": current_user["id"],
        **payload.model_dump(),
    }


@router.post("/password")
def change_password(payload: PasswordChangeIn, current_user=Depends(get_current_user), db=Depends(get_db)):
    return {"status": "changed"}


@router.get("/company", response_model=CompanyOut)
def get_company_settings(current_user=Depends(get_current_user), db=Depends(get_db)):
    return {
        "id": 1,
        "name": "TeamFlow Inc",
        "domain": "teamflow.example.com",
        "timezone": "UTC",
    }


@router.patch("/company", response_model=CompanyOut)
def update_company_settings(payload: CompanyUpdate, current_user=Depends(get_current_user), db=Depends(get_db)):
    base = {
        "id": 1,
        "name": "TeamFlow Inc",
        "domain": "teamflow.example.com",
        "timezone": "UTC",
    }
    return {**base, **payload.model_dump(exclude_unset=True)}


@router.get("/notifications", response_model=NotificationSettingsOut)
def get_notifications(current_user=Depends(get_current_user), db=Depends(get_db)):
    return {"email_notifications": True, "push_notifications": False}


@router.patch("/notifications", response_model=NotificationSettingsOut)
def update_notifications(payload: NotificationSettingsUpdate, current_user=Depends(get_current_user), db=Depends(get_db)):
    base = {"email_notifications": True, "push_notifications": False}
    return {**base, **payload.model_dump(exclude_unset=True)}
