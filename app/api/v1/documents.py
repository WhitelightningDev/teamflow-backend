from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path, UploadFile, File, Form, HTTPException
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongo import get_mongo_db
from app.core.security import get_current_user
from app.schemas.document_schema import DocumentOut, DocumentListOut

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=DocumentListOut)
async def list_documents(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    employee_id: Optional[str] = Query(None),
    leave_id: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    q: dict = {"company_id": ObjectId(current_user["company_id"])}
    if employee_id:
        q["employee_id"] = ObjectId(employee_id)
    if leave_id:
        q["leave_id"] = ObjectId(leave_id)
    # Employees can only see their own docs
    if str(current_user.get("role")) in {"employee", "staff"}:
        me = await db["employees"].find_one({
            "company_id": ObjectId(current_user["company_id"]),
            "user_id": ObjectId(current_user["id"]),
        })
        if me:
            q["employee_id"] = me["_id"]
    total = await db["documents"].count_documents(q)
    cursor = db["documents"].find(q).skip((page - 1) * size).limit(size).sort("uploaded_at", -1)
    items = []
    async for doc in cursor:
        items.append(
            {
                "id": str(doc["_id"]),
                "filename": doc.get("filename", ""),
                "content_type": doc.get("mime_type"),
                "size": doc.get("size_bytes", 0),
                "uploaded_by": str(doc.get("uploaded_by")) if doc.get("uploaded_by") else None,
                "uploaded_at": doc.get("uploaded_at", datetime.utcnow()),
                "employee_id": str(doc.get("employee_id")) if doc.get("employee_id") else None,
                "leave_id": str(doc.get("leave_id")) if doc.get("leave_id") else None,
                "category": doc.get("category"),
            }
        )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    doc = await db["documents"].find_one({"_id": ObjectId(document_id), "company_id": ObjectId(current_user["company_id"])})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # Employee can only access own doc
    if str(current_user.get("role")) in {"employee", "staff"}:
        me = await db["employees"].find_one({
            "company_id": ObjectId(current_user["company_id"]),
            "user_id": ObjectId(current_user["id"]),
        })
        if not me or doc.get("employee_id") != me["_id"]:
            raise HTTPException(status_code=403, detail="Forbidden")
    return {
        "id": str(doc["_id"]),
        "filename": doc.get("filename", ""),
        "content_type": doc.get("mime_type"),
        "size": doc.get("size_bytes", 0),
        "uploaded_by": str(doc.get("uploaded_by")) if doc.get("uploaded_by") else None,
        "uploaded_at": doc.get("uploaded_at", datetime.utcnow()),
        "employee_id": str(doc.get("employee_id")) if doc.get("employee_id") else None,
        "leave_id": str(doc.get("leave_id")) if doc.get("leave_id") else None,
        "category": doc.get("category"),
    }


@router.post("", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    category: Optional[str] = Form(None),
    employee_id: Optional[str] = Form(None),
    leave_id: Optional[str] = Form(None),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    content = await file.read()
    size = len(content)
    now = datetime.utcnow()
    # Derive/validate employee access
    target_employee_id = None
    if str(current_user.get("role")) in {"employee", "staff"}:
        me = await db["employees"].find_one({
            "company_id": ObjectId(current_user["company_id"]),
            "user_id": ObjectId(current_user["id"]),
        })
        if not me:
            raise HTTPException(status_code=400, detail="No employee profile linked to your account")
        target_employee_id = me["_id"]
        # if a leave_id is provided, ensure it belongs to employee
        if leave_id:
            leave = await db["leaves"].find_one({"_id": ObjectId(leave_id), "employee_id": me["_id"], "company_id": ObjectId(current_user["company_id"])})
            if not leave:
                raise HTTPException(status_code=403, detail="Forbidden")
    else:
        if not employee_id:
            raise HTTPException(status_code=400, detail="employee_id is required")
        target_employee_id = ObjectId(employee_id)

    doc = {
        "company_id": ObjectId(current_user["company_id"]),
        "employee_id": target_employee_id,
        "leave_id": ObjectId(leave_id) if leave_id else None,
        "category": category or "general",
        "filename": file.filename,
        "file_url": "",  # stored elsewhere
        "mime_type": file.content_type,
        "size_bytes": size,
        "uploaded_by": ObjectId(current_user["id"]) if current_user.get("id") else None,
        "uploaded_at": now,
        "updated_at": now,
    }
    res = await db["documents"].insert_one(doc)
    return {
        "id": str(res.inserted_id),
        "filename": file.filename,
        "content_type": file.content_type,
        "size": size,
        "uploaded_by": current_user.get("id"),
        "uploaded_at": now,
        "employee_id": str(doc.get("employee_id")) if doc.get("employee_id") else None,
        "leave_id": str(doc.get("leave_id")) if doc.get("leave_id") else None,
        "category": doc.get("category"),
    }


@router.delete("/{document_id}")
async def delete_document(
    document_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    # Employees can only delete own docs
    q = {"_id": ObjectId(document_id), "company_id": ObjectId(current_user["company_id"]) }
    if str(current_user.get("role")) in {"employee", "staff"}:
        me = await db["employees"].find_one({
            "company_id": ObjectId(current_user["company_id"]),
            "user_id": ObjectId(current_user["id"]),
        })
        if not me:
            raise HTTPException(status_code=403, detail="Forbidden")
        q["employee_id"] = me["_id"]
    await db["documents"].delete_one(q)
    return {"status": "deleted", "id": document_id}
