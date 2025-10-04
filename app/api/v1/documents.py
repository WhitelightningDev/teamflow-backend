from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path, UploadFile, File, Form
from app.db.session import get_db
from app.core.security import get_current_user
from app.schemas.document_schema import DocumentOut, DocumentListOut

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=DocumentListOut)
def list_documents(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    employee_id: Optional[int] = Query(None, ge=1),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    items = [
        {
            "id": 1,
            "filename": "policy.pdf",
            "content_type": "application/pdf",
            "size": 123456,
            "uploaded_by": 1,
            "uploaded_at": datetime.utcnow(),
        }
    ]
    return {"items": items, "total": len(items), "page": page, "size": size}


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int = Path(..., ge=1),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    return {
        "id": document_id,
        "filename": "resume.pdf",
        "content_type": "application/pdf",
        "size": 98765,
        "uploaded_by": 1,
        "uploaded_at": datetime.utcnow(),
    }


@router.post("", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    employee_id: Optional[int] = Form(None),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    content = await file.read()
    size = len(content)
    return {
        "id": 2,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": size,
        "uploaded_by": 1,
        "uploaded_at": datetime.utcnow(),
    }


@router.delete("/{document_id}")
def delete_document(
    document_id: int = Path(..., ge=1),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    return {"status": "deleted", "id": document_id}
