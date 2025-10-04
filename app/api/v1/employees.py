from typing import Optional
from datetime import datetime, date as _date
from enum import Enum
from fastapi import APIRouter, Depends, Query, Path, status, HTTPException
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongo import get_mongo_db
from app.core.security import get_current_user
from app.schemas.employee_schema import (
    EmployeeIn,
    EmployeeOut,
    EmployeeUpdate,
    EmployeeListOut,
)

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=EmployeeListOut)
async def list_employees(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    company_oid = ObjectId(current_user["company_id"])
    q: dict = {"company_id": company_oid}
    if search:
        q["$or"] = [
            {"first_name": {"$regex": search, "$options": "i"}},
            {"last_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]
    total = await db["employees"].count_documents(q)
    cursor = (
        db["employees"].find(q).skip((page - 1) * size).limit(size).sort("created_at", -1)
    )
    items = []
    async for doc in cursor:
        items.append(
            {
                "id": str(doc["_id"]),
                "first_name": doc.get("first_name", ""),
                "last_name": doc.get("last_name", ""),
                "email": doc.get("email", ""),
                "role": doc.get("role", "employee"),
                "title": doc.get("title"),
                "start_date": doc.get("start_date"),
                "manager_id": doc.get("manager_id"),
                "is_active": doc.get("is_active", True),
            }
        )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(
    employee_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    doc = await db["employees"].find_one({"_id": ObjectId(employee_id), "company_id": ObjectId(current_user["company_id"])})
    if not doc:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {
        "id": str(doc["_id"]),
        "first_name": doc.get("first_name", ""),
        "last_name": doc.get("last_name", ""),
        "email": doc.get("email", ""),
        "role": doc.get("role", "employee"),
        "title": doc.get("title"),
        "start_date": doc.get("start_date"),
        "manager_id": doc.get("manager_id"),
        "is_active": doc.get("is_active", True),
    }


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
async def create_employee(
    payload: EmployeeIn,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    doc = payload.model_dump()
    doc.update({
        "company_id": ObjectId(current_user["company_id"]),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })
    # Ensure Mongo stores datetimes, not date-only
    if isinstance(doc.get("start_date"), _date) and not isinstance(doc.get("start_date"), datetime):
        sd = doc["start_date"]
        doc["start_date"] = datetime(sd.year, sd.month, sd.day)
    # Ensure role is stored as a primitive
    if isinstance(doc.get("role"), Enum):
        doc["role"] = doc["role"].value
    res = await db["employees"].insert_one(doc)
    return {"id": str(res.inserted_id), **payload.model_dump(), "is_active": payload.model_dump().get("is_active", True)}


@router.put("/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    payload: EmployeeUpdate,
    employee_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    update["updated_at"] = datetime.utcnow()
    # Coerce date-only to datetime for Mongo storage
    if isinstance(update.get("start_date"), _date) and not isinstance(update.get("start_date"), datetime):
        sd = update["start_date"]
        update["start_date"] = datetime(sd.year, sd.month, sd.day)
    # Coerce Enum to its value
    if isinstance(update.get("role"), Enum):
        update["role"] = update["role"].value
    await db["employees"].update_one(
        {"_id": ObjectId(employee_id), "company_id": ObjectId(current_user["company_id"])},
        {"$set": update},
    )
    doc = await db["employees"].find_one({"_id": ObjectId(employee_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {
        "id": str(doc["_id"]),
        "first_name": doc.get("first_name", ""),
        "last_name": doc.get("last_name", ""),
        "email": doc.get("email", ""),
        "role": doc.get("role", "employee"),
        "title": doc.get("title"),
        "start_date": doc.get("start_date"),
        "manager_id": doc.get("manager_id"),
        "is_active": doc.get("is_active", True),
    }


@router.delete("/{employee_id}")
async def delete_employee(
    employee_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    await db["employees"].delete_one({"_id": ObjectId(employee_id), "company_id": ObjectId(current_user["company_id"])})
    return {"status": "deleted", "id": employee_id}
