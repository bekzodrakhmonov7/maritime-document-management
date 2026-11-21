"""Documents, Versions, Reviews, Verifications and their files (FR-09 to FR-13,
FR-15; T1, T5, T8).

Administrators and crewing officers, within their Scope; managers get 403.
Versions are only ever added: by uploading a file, or by correcting the
details of the Current Version (which reuses its stored file). Reviews and
Verifications are added to a Version; a Verification's optional proof file
goes through the same Safety Checks. Files are opened only through
short-lived signed URLs, each one recorded.

An upload runs in T8's order: size (the declared length, then a capped read)
-> magic bytes -> parse, clean or reject -> write the cleaned file to Storage
-> one transaction for the Version and its Audit Record. If that transaction
fails, the stored file is deleted again. A file that fails a Safety Check gets
413/415/422 with a reason code and a plain sentence, and an *upload rejected*
record; nothing of it is kept.
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import NoReturn
from uuid import uuid4

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import FormParser, MultiPartException, MultiPartParser

from app.audit import audit_context_for
from app.deps import get_db
from app.models.document import (
    DocumentRead,
    DocumentSummary,
    FileUrl,
    ReviewWrite,
    UploadRefusal,
    VerificationDetails,
    VersionDetails,
)
from app.routers.crew_access import CrewAccess, errors_as_http, get_crew_access
from app.services import documents as svc
from app.services import reviews
from app.storage import FileMissing, FileStorage, StorageUnavailable, get_storage
from app.upload_safety import (
    Limits,
    Rejection,
    SafeFile,
    read_capped,
    sanitise_filename,
    too_large,
    validate,
)
from app.routers.params import MAX_ID, Id

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
    seafarer_id: Id,
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
    seafarer_id: Id,
    request: Request,
    document_type_id: int = Query(..., ge=1, le=MAX_ID),
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

    async def refuse(rejection: Rejection, size: int | None, filename: str | None) -> NoReturn:
        await svc.record_upload_rejected(
            db, ctx, seafarer_id, document_type_id, rejection, size, filename
        )
        _raise_refusal(rejection)

    async def check(details: dict) -> None:
        with errors_as_http():
            await svc.check_details(db, document_type_id, details)

    received = await _receive(request, await svc.upload_limits(db), refuse, VersionDetails, check)
    assert received.file is not None
    stored = await _store(storage, "versions", received.file, received.filename, "document")

    # One transaction for the Version and its record; on failure the file goes.
    async with _deleted_on_failure(storage, stored):
        with errors_as_http():
            return await svc.add_version(
                db, ctx, access.scope, access.user.sub, seafarer_id, document_type_id,
                received.fields, stored,
            )


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: Id,
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
    document_id: Id,
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
    version_id: Id,
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
    except FileMissing:
        raise _file_missing()
    except StorageUnavailable:
        raise _storage_unavailable()


@router.post(
    "/versions/{version_id}/reviews",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def review_version(
    version_id: Id,
    body: ReviewWrite,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    """Accept or reject a Version with a comment. Never by its uploader (403)."""
    with errors_as_http():
        return await reviews.review(
            db, audit_context_for(request, access.user), access.scope, access.user.sub,
            version_id, body.decision, body.comment,
        )


@router.post(
    "/versions/{version_id}/verifications",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    responses=_REFUSALS,
)
async def record_verification(
    version_id: Id,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
    storage: FileStorage = Depends(get_storage),
):
    """Record a Verification (form fields `checked_on`, `source`, `result`,
    `reference`) with an optional proof `file`, which passes the same Safety
    Checks as a document file."""
    ctx = audit_context_for(request, access.user)
    with errors_as_http():
        version = await reviews.check_can_verify(db, access.scope, version_id)

    async def refuse(rejection: Rejection, size: int | None, filename: str | None) -> NoReturn:
        await reviews.record_proof_rejected(db, ctx, version, rejection, size, filename)
        _raise_refusal(rejection)

    async def check(details: dict) -> None:
        with errors_as_http():
            reviews.check_details(details, access.scope.today)

    received = await _receive(
        request, await svc.upload_limits(db), refuse, VerificationDetails, check, file_required=False
    )
    stored = (
        None if received.file is None
        else await _store(storage, "proofs", received.file, received.filename, "proof")
    )
    async with _deleted_on_failure(storage, stored):
        with errors_as_http():
            return await reviews.add_verification(
                db, ctx, access.scope, access.user.sub, version_id, received.fields, stored
            )


@router.post("/verifications/{verification_id}/proof-url", response_model=FileUrl)
async def issue_proof_url(
    verification_id: Id,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
    storage: FileStorage = Depends(get_storage),
):
    """A short-lived signed URL for a Verification's proof file; recorded as a download."""
    try:
        with errors_as_http():
            return await reviews.issue_proof_url(
                db, audit_context_for(request, access.user), access.scope, storage, verification_id
            )
    except StorageUnavailable:
        raise _storage_unavailable()


def _storage_unavailable() -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "File storage is unavailable; try again.")


def _file_missing() -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        {"code": "file_missing", "message": "The file for this Version was not found in storage."},
    )


# --- Receiving a file ----------------------------------------------------------------------
#
# T8's order: size (the declared length, then a capped read) -> the form's
# fields -> magic bytes -> parse, clean or reject -> the cleaned file to
# Storage -> one transaction; if that fails, the stored file is deleted.


Refuse = Callable[[Rejection, int | None, str | None], Awaitable[NoReturn]]


@dataclass(frozen=True)
class _Received:
    fields: dict
    # None when no file was sent (only allowed where the file is optional).
    file: SafeFile | None
    filename: str | None


def _raise_refusal(rejection: Rejection) -> NoReturn:
    raise HTTPException(rejection.status, {"code": rejection.code, "message": rejection.message})


async def _receive(
    request: Request,
    limits: Limits,
    refuse: Refuse,
    model: type[BaseModel],
    check: Callable[[dict], Awaitable[None]],
    *,
    file_required: bool = True,
) -> _Received:
    """Read a form with a file through the size cap and the Safety Checks.
    A refused file goes to `refuse` (which records it and raises); the form's
    fields are validated with `model` and then `check`, before the file is read."""
    body_limit = limits.max_bytes + FORM_OVERHEAD_BYTES
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > body_limit:
        await refuse(too_large(limits.max_bytes), int(declared), None)
    try:
        form = await _parse_form(request, body_limit)
    except _BodyTooLarge as exc:
        await refuse(too_large(limits.max_bytes), exc.size, None)

    try:
        upload, fields = _file_and_fields(form, model, file_required)
        await check(fields)
        if upload is None:
            return _Received(fields, None, None)
        filename = sanitise_filename(upload.filename)
        data = await read_capped(_chunks(upload), limits.max_bytes)
        if isinstance(data, Rejection):
            await refuse(data, upload.size, filename)
    finally:
        await form.close()

    # Magic bytes, then parse and clean (Pillow and pikepdf off the event loop).
    safe = await run_in_threadpool(validate, data, limits, filename=filename)
    if isinstance(safe, Rejection):
        await refuse(safe, len(data), filename)
    return _Received(fields, safe, filename)


async def _store(
    storage: FileStorage, folder: str, safe: SafeFile, filename: str | None, fallback_stem: str
) -> svc.StoredFile:
    """Write a cleaned file to Storage under a random path."""
    stored = svc.StoredFile(
        path=f"{folder}/{uuid4().hex}.{safe.extension}",
        original_filename=filename or f"{fallback_stem}.{safe.extension}",
        content_type=safe.content_type,
    )
    try:
        await storage.upload(stored.path, safe.content, safe.content_type)
    except StorageUnavailable:
        raise _storage_unavailable()
    return stored


@asynccontextmanager
async def _deleted_on_failure(
    storage: FileStorage, stored: svc.StoredFile | None
) -> AsyncIterator[None]:
    """Delete the stored file again if the block fails: nothing points at it."""
    try:
        yield
    except BaseException:
        if stored is not None:
            await _delete_quietly(storage, stored.path)
        raise


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
    content_type = request.headers.get("content-type", "")
    stream = _capped(request.stream(), body_limit)
    if content_type.startswith("application/x-www-form-urlencoded"):
        return await FormParser(request.headers, stream).parse()
    if not content_type.startswith("multipart/form-data"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Send the file and its details as multipart/form-data."
        )
    parser = MultiPartParser(request.headers, stream, max_files=1, max_fields=10)
    try:
        return await parser.parse()
    except MultiPartException as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.message)


def _file_and_fields(
    form: FormData, model: type[BaseModel], file_required: bool
) -> tuple[UploadFile | None, dict]:
    upload = form.get("file")
    if not isinstance(upload, UploadFile) or (not upload.filename and not upload.size):
        upload = None
    if upload is None and file_required:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a file to upload.")
    fields = {k: v for k, v in form.items() if k != "file" and isinstance(v, str)}
    try:
        details = model.model_validate(fields)
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
        # The row wasn't created, so nothing points at the file.
        logger.exception("Could not delete the stored file %s after a failed write", path)
