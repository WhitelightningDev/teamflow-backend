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
    return [
        "admin",
        "manager",
        "supervisor",
        "hr",
        "employee",
        "staff",
        "guest",
        "viewer",
        "payroll",
        "recruiter",
        "trainer",
        "benefit_admin",
    ]


@router.get("/time-reasons")
def get_time_reasons(db=Depends(get_db), current_user=Depends(get_current_user)):
    """Predefined reasons for pausing/abandoning jobs (suggested list)."""
    return {
        "pause": [
            "Network/Wi-Fi outage",
            "Blocked by dependency",
            "Awaiting approvals",
            "Equipment failure",
            "Power outage",
            "Weather conditions",
            "Site access issues",
        ],
        "abandon": [
            "Job canceled",
            "Client canceled",
            "Reassigned",
            "Duplicate work",
            "Scope changed",
            "Unable to proceed",
        ],
    }


@router.get("/provinces", response_model=List[str])
def get_provinces(db=Depends(get_db), current_user=Depends(get_current_user)):
    # South African provinces (ISO 3166-2:ZA region names)
    return [
        "Eastern Cape",
        "Free State",
        "Gauteng",
        "KwaZulu-Natal",
        "Limpopo",
        "Mpumalanga",
        "North West",
        "Northern Cape",
        "Western Cape",
    ]
