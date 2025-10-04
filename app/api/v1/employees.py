from typing import Optional
from fastapi import APIRouter, Depends, Query, Path, status
from app.db.session import get_db
from app.core.security import get_current_user
from app.schemas.employee_schema import (
    EmployeeIn,
    EmployeeOut,
    EmployeeUpdate,
    EmployeeListOut,
)

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=EmployeeListOut)
def list_employees(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    items = [
        {
            "id": 1,
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice@example.com",
            "role": "employee",
            "title": "Engineer",
            "start_date": "2024-01-01",
            "manager_id": None,
            "is_active": True,
        }
    ]
    return {"items": items, "total": len(items), "page": page, "size": size}


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(
    employee_id: int = Path(..., ge=1),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    return {
        "id": employee_id,
        "first_name": "Alice",
        "last_name": "Smith",
        "email": "alice@example.com",
        "role": "employee",
        "title": "Engineer",
        "start_date": "2024-01-01",
        "manager_id": None,
        "is_active": True,
    }


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: EmployeeIn,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    return {"id": 2, **payload.model_dump()}


@router.put("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    payload: EmployeeUpdate,
    employee_id: int = Path(..., ge=1),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    base = {
        "id": employee_id,
        "first_name": "Alice",
        "last_name": "Smith",
        "email": "alice@example.com",
        "role": "employee",
        "title": "Engineer",
        "start_date": "2024-01-01",
        "manager_id": None,
        "is_active": True,
    }
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    return {**base, **update}


@router.delete("/{employee_id}")
def delete_employee(
    employee_id: int = Path(..., ge=1),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    return {"status": "deleted", "id": employee_id}
