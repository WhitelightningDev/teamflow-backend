from typing import Iterable
from fastapi import HTTPException, status


def is_admin_like(role: str) -> bool:
    return role in {"admin", "manager", "hr"}


def require_roles(user: dict, allowed: Iterable[str]) -> None:
    role = str(user.get("role", ""))
    if role not in set(allowed):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def can_view_employee_scope(user: dict, employee_id: str | None) -> bool:
    if is_admin_like(str(user.get("role", ""))):
        return True
    # employee/staff can only see their own employee_id
    return bool(employee_id) and str(user.get("employee_id", "")) == str(employee_id)

