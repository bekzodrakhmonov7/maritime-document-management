import json
from datetime import date
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.deps import get_current_user, get_db
from app.models.auth import UserPayload
from app.models.document import DocumentCreate, DocumentRead, DocumentVerify
from app.services import document_service
from app.storage import StorageClient

router = APIRouter(prefix="/documents", tags=["documents"])


async def parse_document_create(
    doc_type_id: Annotated[int, Form()],
    seafarer_id: Annotated[int, Form()],
    document_number: Annotated[str, Form()],
    issue_date: Annotated[date, Form()],
    expiry_date: Annotated[date, Form()],
) -> DocumentCreate:
    from pydantic import ValidationError
    try:
        return DocumentCreate(
            doc_type_id=doc_type_id,
            seafarer_id=seafarer_id,
            document_number=document_number,
            issue_date=issue_date,
            expiry_date=expiry_date,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=json.loads(exc.json()),
        )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=DocumentRead)
async def create_document(
    metadata: Annotated[DocumentCreate, Depends(parse_document_create)],
    file: Annotated[UploadFile, File()],
    current_user: UserPayload = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> DocumentRead:
    file_bytes = await file.read()
    return await document_service.create_document(
        db, metadata, file_bytes, file.content_type or "application/octet-stream", current_user.sub
    )


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    current_user: UserPayload = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[DocumentRead]:
    return await document_service.list_documents(db)


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: int,
    current_user: UserPayload = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> DocumentRead:
    doc = await document_service.get_document(db, document_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    storage = StorageClient()
    doc.signed_url = await storage.create_signed_url(doc.file_path, ttl=300)
    return doc


@router.patch("/{document_id}/verify", response_model=DocumentRead)
async def verify_document(
    document_id: int,
    verify: DocumentVerify,
    current_user: UserPayload = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> DocumentRead:
    return await document_service.verify_document(db, document_id, verify.status)
