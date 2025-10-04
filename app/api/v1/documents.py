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
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    q: dict = {"company_id": ObjectId(current_user["company_id"])}
    if employee_id:
        q["employee_id"] = ObjectId(employee_id)
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
    return {
        "id": str(doc["_id"]),
        "filename": doc.get("filename", ""),
        "content_type": doc.get("mime_type"),
        "size": doc.get("size_bytes", 0),
        "uploaded_by": str(doc.get("uploaded_by")) if doc.get("uploaded_by") else None,
        "uploaded_at": doc.get("uploaded_at", datetime.utcnow()),
    }


@router.post("", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    employee_id: Optional[str] = Form(None),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    content = await file.read()
    size = len(content)
    now = datetime.utcnow()
    doc = {
        "company_id": ObjectId(current_user["company_id"]),
        "employee_id": ObjectId(employee_id) if employee_id else None,
        "category": "general",
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
    }


@router.delete("/{document_id}")
async def delete_document(
    document_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user=Depends(get_current_user),
):
    await db["documents"].delete_one({"_id": ObjectId(document_id), "company_id": ObjectId(current_user["company_id"])})
    return {"status": "deleted", "id": document_id}
