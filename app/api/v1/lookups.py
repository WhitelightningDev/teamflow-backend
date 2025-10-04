from typing import List
from fastapi import APIRouter, Depends
from app.db.session import get_db
from app.core.security import get_current_user

router = APIRouter(prefix="/lookups", tags=["lookups"])


@router.get("/leave-types", response_model=List[str])
def get_leave_types(db=Depends(get_db), current_user=Depends(get_current_user)):
    return ["annual", "sick", "unpaid", "maternity", "paternity"]


@router.get("/statuses", response_model=List[str])
def get_statuses(db=Depends(get_db), current_user=Depends(get_current_user)):
    return ["pending", "approved", "rejected", "cancelled"]


@router.get("/roles", response_model=List[str])
def get_roles(db=Depends(get_db), current_user=Depends(get_current_user)):
    return ["admin", "manager", "employee"]

