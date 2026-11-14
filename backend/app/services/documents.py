"""Documents and Versions (FR-09, FR-10, FR-13, FR-15; T1, T2, T5, T8).

A Document is read through its seafarer's Scope: outside it, it is answered
like a missing one (OutOfScope). In Scope means the whole record, so every
Version of it and every Version's file.

Versions are only ever added. An upload creates the Document if needed plus a
Version; a details-only Version reuses the Current Version's stored file. The
Document Type's rules are checked when a Version is created, and only then.
Current Version and Expiry Status are computed on read (app/domain.py), with
today and the largest Alert Step taken from the Settings row per request.
"""

import mimetypes
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import asyncpg

from app import audit, domain
from app.audit import AuditAction, AuditContext
from app.scope import Scope
from app.services import reference_data, seafarers
from app.services.errors import Conflict, Invalid, NotFound, OutOfScope
from app.storage import FileStorage
from app.upload_safety import Limits, Rejection

DOCUMENT = "document"
VERSION = "version"
DETAILS = ("document_number", "issuing_authority", "issue_date", "expiry_date")
# Signed URLs are short-lived: long enough to open, not to pass around.
FILE_URL_TTL_SECONDS = 120

_DOCUMENT_FIELDS = """
       d.id, d.seafarer_id, d.document_type_id, d.created_at,
       t.name AS document_type_name, t.retired AS document_type_retired,
       t.expires, t.max_validity_months
  FROM public.document d
  JOIN public.document_type t ON t.id = d.document_type_id
"""

_VERSION_FIELDS = """
       v.id, v.document_id, v.file_path, v.original_filename, v.content_type,
       v.document_number, v.issuing_authority, v.issue_date, v.expiry_date,
       v.uploaded_by, u.full_name AS uploaded_by_name, v.uploaded_at
  FROM public.version v
  JOIN public.users u ON u.id = v.uploaded_by
"""


@dataclass(frozen=True)
class StoredFile:
    """A cleaned file already written to Storage, ready for its Version."""

    path: str
    original_filename: str
    content_type: str


# --- Reads -------------------------------------------------------------------------------


async def _largest_alert_step(conn: asyncpg.Connection) -> int:
    """The largest Alert Step, read per request so a change applies at once."""
    return max(await conn.fetchval("SELECT alert_steps FROM public.settings"))


async def _versions_of(conn: asyncpg.Connection, document_ids: list[int]) -> dict[int, list[dict]]:
    rows = await conn.fetch(
        f"SELECT {_VERSION_FIELDS} WHERE v.document_id = ANY($1::bigint[]) "
        "ORDER BY v.uploaded_at, v.id",
        document_ids,
    )
    by_document: dict[int, list[dict]] = {}
    for row in rows:
        by_document.setdefault(row["document_id"], []).append(dict(row))
    return by_document


def _reviews_of(_versions: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    # Reviews arrive in S8; until then every Version awaits review.
    return []


def _summary(
    document: Mapping[str, Any], versions: list[dict], today: date, largest_step: int
) -> dict:
    current = domain.current_version(versions, _reviews_of(versions))
    return {
        **document,
        "version_count": len(versions),
        "current_version": current,
        "expiry_status": (
            None if current is None
            else domain.expiry_status(current["expiry_date"], today, largest_step)
        ),
    }


async def list_for_seafarer(conn: asyncpg.Connection, scope: Scope, seafarer_id: int) -> list[dict]:
    """A seafarer's documents, by type name, each with its Current Version
    and Expiry Status."""
    await seafarers.fetch_in_scope(conn, scope, seafarer_id)
    documents = await conn.fetch(
        f"SELECT {_DOCUMENT_FIELDS} WHERE d.seafarer_id = $1 ORDER BY lower(t.name), d.id",
        seafarer_id,
    )
    versions = await _versions_of(conn, [d["id"] for d in documents])
    largest_step = await _largest_alert_step(conn)
    return [
        _summary(dict(d), versions.get(d["id"], []), scope.today, largest_step) for d in documents
    ]


async def get(conn: asyncpg.Connection, scope: Scope, document_id: int) -> dict:
    """A Document with its full history, newest Version first."""
    row = await conn.fetchrow(
        f"""
        SELECT {scope.where("s")} AS in_scope, s.first_name AS seafarer_first_name,
               s.last_name AS seafarer_last_name,
               s.inactive_since IS NOT NULL AS seafarer_inactive, {_DOCUMENT_FIELDS}
          JOIN public.seafarer s ON s.id = d.seafarer_id
         WHERE d.id = $1
        """,
        document_id,
    )
    if row is None:
        raise NotFound()
    if not row["in_scope"]:
        raise OutOfScope(DOCUMENT, document_id, row["seafarer_id"])
    document = dict(row)
    del document["in_scope"]
    versions = (await _versions_of(conn, [document_id])).get(document_id, [])
    found = _summary(document, versions, scope.today, await _largest_alert_step(conn))
    found["versions"] = _history(versions, found["current_version"])
    return found


def _history(versions: list[dict], current: Mapping[str, Any] | None) -> list[dict]:
    """Every Version, numbered in upload order, newest first. A Version whose
    file an earlier one already had is marked with that earlier number."""
    first_with_file: dict[str, int] = {}
    history = []
    for number, v in enumerate(versions, start=1):
        reused_from = first_with_file.setdefault(v["file_path"], number)
        history.append(
            {
                **v,
                "number": number,
                "is_current": current is not None and v["id"] == current["id"],
                "file_from_version_number": reused_from if reused_from != number else None,
            }
        )
    return history[::-1]


# --- Writes ------------------------------------------------------------------------------


async def check_can_add(
    conn: asyncpg.Connection, scope: Scope, seafarer_id: int, document_type_id: int
) -> None:
    """Refuse early, before a file is read: seafarer missing or out of Scope,
    Inactive, or a Document Type that can't be picked. `add_version` checks
    all of it again under locks."""
    seafarer = await seafarers.fetch_in_scope(conn, scope, seafarer_id)
    _require_active(seafarer)
    await reference_data.check_pickable(conn, reference_data.DOCUMENT_TYPE, document_type_id)


async def upload_limits(conn: asyncpg.Connection) -> Limits:
    row = await conn.fetchrow("SELECT max_file_size_mb, max_pdf_pages FROM public.settings")
    return Limits.from_settings(row["max_file_size_mb"], row["max_pdf_pages"])


async def check_details(conn: asyncpg.Connection, document_type_id: int, details: dict) -> None:
    """The Document Type's rules for a new Version's dates (T2)."""
    rules = await conn.fetchrow(
        "SELECT expires, max_validity_months FROM public.document_type WHERE id = $1",
        document_type_id,
    )
    problem = domain.version_dates_problem(
        details["issue_date"],
        details["expiry_date"],
        expires=rules["expires"],
        max_validity_months=rules["max_validity_months"],
    )
    if problem:
        raise Invalid(problem)


async def add_version(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    scope: Scope,
    account_id: UUID,
    seafarer_id: int,
    document_type_id: int,
    details: dict,
    stored: StoredFile,
) -> dict:
    """Record an uploaded file as a new Version, creating the Document on its
    first upload. One transaction for the Version and its Audit Record; if it
    fails, the caller removes the stored file."""
    async with conn.transaction():
        seafarer = await seafarers.lock_in_scope(conn, scope, seafarer_id)
        _require_active(seafarer)
        await reference_data.check_pickable(conn, reference_data.DOCUMENT_TYPE, document_type_id)
        await check_details(conn, document_type_id, details)
        document_id = await _document_id(conn, seafarer_id, document_type_id)
        version_id = await _insert_version(conn, document_id, details, stored, account_id)
        await audit.record(
            conn, ctx, AuditAction.VERSION_UPLOADED,
            target_type=VERSION, target_id=version_id, seafarer_id=seafarer_id,
            after={
                "document_id": document_id,
                "document_type_id": document_type_id,
                **{c: details[c] for c in DETAILS},
                "original_filename": stored.original_filename,
                "content_type": stored.content_type,
            },
        )
        return await get(conn, scope, document_id)


async def add_details_version(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    scope: Scope,
    account_id: UUID,
    document_id: int,
    details: dict,
) -> dict:
    """A new Version with corrected details that reuses the Current Version's
    stored file. Refused when nothing changed or there is no Current Version."""
    async with conn.transaction():
        document = await conn.fetchrow(
            "SELECT seafarer_id, document_type_id FROM public.document WHERE id = $1", document_id
        )
        if document is None:
            raise NotFound()
        try:
            seafarer = await seafarers.lock_in_scope(conn, scope, document["seafarer_id"])
        except OutOfScope:
            raise OutOfScope(DOCUMENT, document_id, document["seafarer_id"])
        _require_active(seafarer)
        await reference_data.check_pickable(
            conn, reference_data.DOCUMENT_TYPE, document["document_type_id"]
        )
        versions = (await _versions_of(conn, [document_id])).get(document_id, [])
        current = domain.current_version(versions, _reviews_of(versions))
        if current is None:
            raise Conflict("The document has no Current Version: upload a file instead.")
        before, after = audit.changed_fields(
            {c: current[c] for c in DETAILS}, {c: details[c] for c in DETAILS}
        )
        if not after:
            raise Conflict("Nothing changed: the details are the same as the Current Version's.")
        await check_details(conn, document["document_type_id"], details)
        stored = StoredFile(current["file_path"], current["original_filename"], current["content_type"])
        version_id = await _insert_version(conn, document_id, details, stored, account_id)
        await audit.record(
            conn, ctx, AuditAction.VERSION_UPLOADED,
            target_type=VERSION, target_id=version_id, seafarer_id=document["seafarer_id"],
            before=before,
            after={"document_id": document_id, **after, "file_from_version_id": current["id"]},
        )
        return await get(conn, scope, document_id)


async def issue_file_url(
    conn: asyncpg.Connection, ctx: AuditContext, scope: Scope, storage: FileStorage, version_id: int
) -> dict:
    """A short-lived signed URL for one Version's file, recorded as a download.
    The record and the URL go together: no record, no URL."""
    row = await conn.fetchrow(
        f"""
        SELECT {scope.where("s")} AS in_scope, d.seafarer_id,
               v.file_path, v.original_filename, v.content_type
          FROM public.version v
          JOIN public.document d ON d.id = v.document_id
          JOIN public.seafarer s ON s.id = d.seafarer_id
         WHERE v.id = $1
        """,
        version_id,
    )
    if row is None:
        raise NotFound()
    if not row["in_scope"]:
        raise OutOfScope(VERSION, version_id, row["seafarer_id"])
    filename = download_name(row["original_filename"], row["content_type"])
    async with conn.transaction():
        await audit.record(
            conn, ctx, AuditAction.FILE_URL_ISSUED,
            target_type=VERSION, target_id=version_id, seafarer_id=row["seafarer_id"],
            after={"filename": filename},
        )
        url = await storage.signed_url(row["file_path"], FILE_URL_TTL_SECONDS, filename)
    return {
        "url": url,
        "expires_in": FILE_URL_TTL_SECONDS,
        "filename": filename,
        "content_type": row["content_type"],
    }


async def record_upload_rejected(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    seafarer_id: int,
    document_type_id: int,
    rejection: Rejection,
    size_bytes: int | None,
    filename: str | None,
) -> None:
    """An *upload rejected* record: who, which seafarer and type, why, the
    size and the cleaned name. Never the file's contents."""
    async with conn.transaction():
        await audit.record(
            conn, ctx, AuditAction.UPLOAD_REJECTED,
            target_type="document_type", target_id=document_type_id, seafarer_id=seafarer_id,
            after={
                "document_type_id": document_type_id,
                "size_bytes": size_bytes,
                "filename": filename,
            },
            reason=rejection.code,
            outcome="refused",
        )


def download_name(filename: str, content_type: str) -> str:
    """The cleaned name, given the detected type's extension if it has none."""
    if "." in filename.strip("."):
        return filename
    extension = {"image/jpeg": ".jpg"}.get(content_type) or mimetypes.guess_extension(content_type)
    return f"{filename}{extension or ''}"


def _require_active(seafarer: Mapping[str, Any]) -> None:
    if seafarer["inactive_since"] is not None:
        raise Conflict("The seafarer is Inactive: reactivate them before adding documents.")


async def _document_id(conn: asyncpg.Connection, seafarer_id: int, document_type_id: int) -> int:
    """The seafarer's Document of this type, created on its first upload.
    The seafarer row is locked, so two first uploads can't race."""
    existing = await conn.fetchval(
        "SELECT id FROM public.document WHERE seafarer_id = $1 AND document_type_id = $2",
        seafarer_id,
        document_type_id,
    )
    if existing is not None:
        return existing
    return await conn.fetchval(
        "INSERT INTO public.document (seafarer_id, document_type_id) VALUES ($1, $2) RETURNING id",
        seafarer_id,
        document_type_id,
    )


async def _insert_version(
    conn: asyncpg.Connection, document_id: int, details: dict, stored: StoredFile, account_id: UUID
) -> int:
    return await conn.fetchval(
        """
        INSERT INTO public.version
            (document_id, file_path, original_filename, content_type,
             document_number, issuing_authority, issue_date, expiry_date, uploaded_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id
        """,
        document_id,
        stored.path,
        stored.original_filename,
        stored.content_type,
        *(details[c] for c in DETAILS),
        account_id,
    )
