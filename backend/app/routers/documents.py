"""Documents, Versions and their files (FR-09, FR-10, FR-13, FR-15; T1, T5, T8).

Administrators and crewing officers, within their Scope; managers get 403.
Versions are only ever added: by uploading a file, or by correcting the
details of the Current Version (which reuses its stored file). Files are
opened only through short-lived signed URLs, each one recorded.

An upload runs in T8's order: size (the declared length, then a capped read)
-> magic bytes -> parse, clean or reject -> write the cleaned file to Storage
-> one transaction for the Version and its Audit Record. If that transaction
fails, the stored file is deleted again. A file that fails a Safety Check gets
413/415/422 with a reason code and a plain sentence, and an *upload rejected*
record; nothing of it is kept.
"""

import logging
from collections.abc import AsyncIterator
from typing import NoReturn
from uuid import uuid4

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.audit import audit_context_for
from app.deps import get_db
from app.models.document import (
    DocumentRead,
    DocumentSummary,
    FileUrl,
    UploadRefusal,
    VersionDetails,
)
from app.routers.crew_access import CrewAccess, errors_as_http, get_crew_access
from app.services import documents as svc
from app.storage import FileStorage, StorageUnavailable, get_storage
from app.upload_safety import Rejection, read_capped, sanitise_filename, too_large, validate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])

# Room for the details fields and multipart framing around the file itself.
FORM_OVERHEAD_BYTES = 64 * 1024
CHUNK_BYTES = 256 * 1024

_REFUSALS = {
    code: {"model": UploadRefusal, "description": "A Safety Check failed."}
    for code in (413, 415)
}


@router.get("/seafarers/{seafarer_id}/documents", response_model=list[DocumentSummary])
async def list_seafarer_documents(
    seafarer_id: int,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.list_for_seafarer(db, access.scope, seafarer_id)


@router.post(
    "/seafarers/{seafarer_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    responses=_REFUSALS,
)
async def upload_version(
    seafarer_id: int,
    request: Request,
    document_type_id: int = Query(...),
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
    storage: FileStorage = Depends(get_storage),
):
    """Upload a file with its details (multipart: `file`, `document_number`,
    `issuing_authority`, `issue_date`, `expiry_date`). Creates the seafarer's
    Document of this type on its first upload; otherwise adds a Version."""
    ctx = audit_context_for(request, access.user)
    with errors_as_http():
        await svc.check_can_add(db, access.scope, seafarer_id, document_type_id)
    limits = await svc.upload_limits(db)

    async def refuse(rejection: Rejection, size: int | None, filename: str | None) -> NoReturn:
        await svc.record_upload_rejected(
            db, ctx, seafarer_id, document_type_id, rejection, size, filename
        )
        raise HTTPException(
            rejection.status, {"code": rejection.code, "message": rejection.message}
        )

    # 1. Size: a fast reject on the declared length, then a capped read.
    body_limit = limits.max_bytes + FORM_OVERHEAD_BYTES
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > body_limit:
        await refuse(too_large(limits.max_bytes), int(declared), None)
    try:
        form = await _parse_form(request, body_limit)
    except _BodyTooLarge as exc:
        await refuse(too_large(limits.max_bytes), exc.size, None)

    try:
        upload, details = _file_and_details(form)
        with errors_as_http():
            await svc.check_details(db, document_type_id, details)
        filename = sanitise_filename(upload.filename)
        data = await read_capped(_chunks(upload), limits.max_bytes)
        if isinstance(data, Rejection):
            await refuse(data, upload.size, filename)
    finally:
        await form.close()

    # 2-3. Magic bytes, then parse and clean (Pillow and pikepdf off the event loop).
    safe = await run_in_threadpool(validate, data, limits, filename=filename)
    if isinstance(safe, Rejection):
        await refuse(safe, len(data), filename)

    # 4. The cleaned file goes to Storage under a random path.
    stored = svc.StoredFile(
        path=f"versions/{uuid4().hex}.{safe.extension}",
        original_filename=filename or f"document.{safe.extension}",
        content_type=safe.content_type,
    )
    try:
        await storage.upload(stored.path, safe.content, safe.content_type)
    except StorageUnavailable:
        raise _storage_unavailable()

    # 5. One transaction for the Version and its record; on failure the file goes.
    try:
        with errors_as_http():
            return await svc.add_version(
                db, ctx, access.scope, access.user.sub, seafarer_id, document_type_id, details, stored
            )
    except BaseException:
        await _delete_quietly(storage, stored.path)
        raise


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: int,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    """The Document with its full history, newest Version first."""
    with errors_as_http():
        return await svc.get(db, access.scope, document_id)


@router.post(
    "/documents/{document_id}/versions",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_details_version(
    document_id: int,
    body: VersionDetails,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    """A details-only Version: corrected details, the Current Version's file."""
    with errors_as_http():
        return await svc.add_details_version(
            db, audit_context_for(request, access.user), access.scope, access.user.sub,
            document_id, body.model_dump(),
        )


@router.post("/versions/{version_id}/file-url", response_model=FileUrl)
async def issue_file_url(
    version_id: int,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
    storage: FileStorage = Depends(get_storage),
):
    """A short-lived signed URL for one Version's file; recorded as a download."""
    try:
        with errors_as_http():
            return await svc.issue_file_url(
                db, audit_context_for(request, access.user), access.scope, storage, version_id
            )
    except StorageUnavailable:
        raise _storage_unavailable()


def _storage_unavailable() -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "File storage is unavailable; try again.")


# --- Multipart parsing ---------------------------------------------------------------------


class _BodyTooLarge(Exception):
    def __init__(self, size: int) -> None:
        self.size = size


async def _capped(stream: AsyncIterator[bytes], limit: int) -> AsyncIterator[bytes]:
    """The request body, stopping as soon as it passes `limit` bytes."""
    size = 0
    async for chunk in stream:
        size += len(chunk)
        if size > limit:
            raise _BodyTooLarge(size)
        yield chunk


async def _parse_form(request: Request, body_limit: int) -> FormData:
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Send the file and its details as multipart/form-data."
        )
    parser = MultiPartParser(
        request.headers, _capped(request.stream(), body_limit), max_files=1, max_fields=10
    )
    try:
        return await parser.parse()
    except MultiPartException as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.message)


def _file_and_details(form: FormData) -> tuple[UploadFile, dict]:
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a file to upload.")
    fields = {k: v for k, v in form.items() if k != "file" and isinstance(v, str)}
    try:
        details = VersionDetails.model_validate(fields)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False, include_context=False))
    return upload, details.model_dump()


async def _chunks(upload: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await upload.read(CHUNK_BYTES):
        yield chunk


async def _delete_quietly(storage: FileStorage, path: str) -> None:
    try:
        await storage.delete(path)
    except Exception:
        # The Version wasn't created, so nothing points at the file.
        logger.exception("Could not delete the stored file %s after a failed upload", path)

