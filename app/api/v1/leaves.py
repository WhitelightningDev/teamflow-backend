from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, Path
from app.db.session import get_db
from app.core.security import get_current_user
from app.schemas.leave_schema import (
    LeaveIn,
    LeaveOut,
    LeaveDecisionIn,
    LeaveListOut,
)

router = APIRouter(prefix="/leaves", tags=["leaves"])


@router.get("", response_model=LeaveListOut)
def list_leaves(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    status: Optional[str] = Query(None),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    items = [
        {
            "id": 1,
            "employee_id": 1,
            "leave_type": "annual",
            "start_date": "2024-03-01",
            "end_date": "2024-03-05",
            "reason": "Family trip",
            "status": "pending",
            "created_at": datetime(2024, 2, 1, 10, 0, 0),
        }
    ]
    return {"items": items, "total": len(items), "page": page, "size": size}


@router.get("/{leave_id}", response_model=LeaveOut)
def get_leave(
    leave_id: int = Path(..., ge=1),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    return {
        "id": leave_id,
        "employee_id": 1,
        "leave_type": "annual",
        "start_date": "2024-03-01",
        "end_date": "2024-03-05",
        "reason": "Family trip",
        "status": "pending",
        "created_at": datetime(2024, 2, 1, 10, 0, 0),
    }


@router.post("", response_model=LeaveOut)
def create_leave(payload: LeaveIn, db=Depends(get_db), current_user=Depends(get_current_user)):
    return {
        "id": 2,
        **payload.model_dump(),
        "status": "pending",
        "created_at": datetime(2024, 2, 15, 9, 0, 0),
    }


@router.patch("/{leave_id}", response_model=LeaveOut)
def decide_leave(
    payload: LeaveDecisionIn,
    leave_id: int = Path(..., ge=1),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    status_out = "approved" if payload.action == "approve" else "rejected"
    base = {
        "id": leave_id,
        "employee_id": 1,
        "leave_type": "annual",
        "start_date": "2024-03-01",
        "end_date": "2024-03-05",
        "reason": "Family trip",
        "created_at": datetime(2024, 2, 1, 10, 0, 0),
    }
    return {**base, "status": status_out}


@router.delete("/{leave_id}")
def delete_leave(
    leave_id: int = Path(..., ge=1),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    return {"status": "deleted", "id": leave_id}
