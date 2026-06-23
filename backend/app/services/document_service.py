from uuid import UUID, uuid4

import asyncpg
from fastapi import HTTPException, status

from app.models.document import DocumentCreate, DocumentRead
from app.storage import StorageClient

ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
BUCKET = "crew-documents"

_EXT_TO_MIME: dict[str, str] = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"verified", "rejected"},
    "verified": set(),
    "valid": set(),
    "rejected": set(),
    "expiring_soon": set(),
    "expired": set(),
}


async def create_document(
    conn: asyncpg.Connection,
    metadata: DocumentCreate,
    file_bytes: bytes,
    mime_type: str,
    uploaded_by: UUID | None = None,
) -> DocumentRead:
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported media type. Only PDF, JPEG, and PNG are allowed.",
        )

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds maximum size of 10MB.",
        )

    ext = {
        "application/pdf": "pdf",
        "image/jpeg": "jpg",
        "image/png": "png",
    }[mime_type]

    path = f"{uploaded_by or 'anonymous'}/{uuid4().hex}_{len(file_bytes)}.{ext}"

    storage = StorageClient(BUCKET)
    await storage.upload_file(BUCKET, path, file_bytes, mime_type)

    try:
        row = await conn.fetchrow(
            """
            INSERT INTO document (
                seafarer_id, doc_type_id, document_number,
                issue_date, expiry_date, file_path, uploaded_by, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending')
            RETURNING
                document_id, seafarer_id, doc_type_id, document_number,
                issue_date, expiry_date, status, file_path,
                uploaded_by, created_at
            """,
            metadata.seafarer_id,
            metadata.doc_type_id,
            metadata.document_number,
            metadata.issue_date,
            metadata.expiry_date,
            path,
            uploaded_by,
        )
    except Exception:
        await storage.delete_file(path)
        raise

    if row is None:
        await storage.delete_file(path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to insert document record.",
        )

    return DocumentRead(**dict(row))


async def verify_document(
    conn: asyncpg.Connection, document_id: int, new_status: str
) -> DocumentRead:
    row = await conn.fetchrow(
        "SELECT status FROM document WHERE document_id = $1", document_id
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    current_status: str = row["status"]
    if new_status not in _VALID_TRANSITIONS.get(current_status, set()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status transition from {current_status} to {new_status}",
        )

    updated = await conn.fetchrow(
        """
        UPDATE document SET status = $1
        WHERE document_id = $2
        RETURNING
            document_id, seafarer_id, doc_type_id, document_number,
            issue_date, expiry_date, status, file_path,
            uploaded_by, created_at
        """,
        new_status,
        document_id,
    )

    return DocumentRead(**dict(updated))


async def list_documents(conn: asyncpg.Connection) -> list[DocumentRead]:
    rows = await conn.fetch(
        """
        SELECT
            document_id, seafarer_id, doc_type_id, document_number,
            issue_date, expiry_date, status, file_path,
            uploaded_by, created_at
        FROM document
        ORDER BY created_at DESC
        """
    )
    return [DocumentRead(**dict(r)) for r in rows]


async def get_document(
    conn: asyncpg.Connection, document_id: int
) -> DocumentRead | None:
    row = await conn.fetchrow(
        """
        SELECT
            document_id, seafarer_id, doc_type_id, document_number,
            issue_date, expiry_date, status, file_path,
            uploaded_by, created_at
        FROM document
        WHERE document_id = $1
        """,
        document_id,
    )
    if row is None:
        return None
    return DocumentRead(**dict(row))


async def preview_document(
    conn: asyncpg.Connection, document_id: int
) -> tuple[bytes, str]:
    doc = await get_document(conn, document_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    ext = doc.file_path.rsplit(".", 1)[-1].lower() if "." in doc.file_path else ""
    content_type = _EXT_TO_MIME.get(ext)
    if content_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Document has an unsupported file type.",
        )

    storage = StorageClient(BUCKET)
    file_bytes = await storage.download_file(doc.file_path)
    return file_bytes, content_type
