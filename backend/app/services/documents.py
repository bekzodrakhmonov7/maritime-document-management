"""Documents and Versions (FR-09, FR-10, FR-13, FR-15; T1, T2, T5, T8).

A Document is read through its seafarer's Scope: outside it, it is answered
like a missing one (OutOfScope). In Scope means the whole record, so every
Version of it and every Version's file.

Versions are only ever added. An upload creates the Document if needed plus a
Version; a details-only Version reuses the Current Version's stored file. The
Document Type's rules are checked when a Version is created, and only then.
Current Version and Expiry Status are computed on read (app/domain.py), with
today and the largest Alert Step taken from the Settings row per request.
Expiry Status follows the Effective Expiry: an Endorsement is capped by its
certificate's Current Version and counts as expired with none (FR-14). The
Current Version keeps its own expiry date, which Alerts follow.
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
       t.expires, t.max_validity_months, t.depends_on_id,
       ct.name AS certificate_type_name
  FROM public.document d
  JOIN public.document_type t ON t.id = d.document_type_id
  LEFT JOIN public.document_type ct ON ct.id = t.depends_on_id
"""

# A Document Type's fields as _DOCUMENT_FIELDS names them, plus the rank of
# its lower-cased name (equal names share one), to order Documents read
# without joining their types.
_DOCUMENT_TYPES = """
SELECT t.id, t.name AS document_type_name, t.retired AS document_type_retired,
       t.expires, t.max_validity_months, t.depends_on_id,
       ct.name AS certificate_type_name,
       dense_rank() OVER (ORDER BY lower(t.name)) AS name_rank
  FROM public.document_type t
  LEFT JOIN public.document_type ct ON ct.id = t.depends_on_id
"""

_VERSION_FIELDS = """
       v.id, v.document_id, v.file_path, v.original_filename, v.content_type,
       v.document_number, v.issuing_authority, v.issue_date, v.expiry_date,
       v.uploaded_by, u.full_name AS uploaded_by_name, v.uploaded_at
  FROM public.version v
  JOIN public.users u ON u.id = v.uploaded_by
"""

# What the dashboard reads of a Current Version (NFR-07): a brief summary
# carries only these.
_BRIEF_VERSION_FIELDS = """
       v.id, v.document_id, v.issue_date, v.expiry_date, v.uploaded_by, v.uploaded_at
  FROM public.version v
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


async def _versions_of(
    conn: asyncpg.Connection, document_ids: list[int], fields: str = _VERSION_FIELDS
) -> dict[int, list[asyncpg.Record]]:
    """Each Document's Versions in upload order, as read-only rows."""
    rows = await conn.fetch(
        f"SELECT {fields} WHERE v.document_id = ANY($1::bigint[]) "
        "ORDER BY v.uploaded_at, v.id",
        document_ids,
    )
    by_document: dict[int, list[asyncpg.Record]] = {}
    for row in rows:
        by_document.setdefault(row["document_id"], []).append(row)
    return by_document


async def _reviews_of(conn: asyncpg.Connection, versions: Iterable[Mapping[str, Any]]) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT r.id, r.version_id, r.decision, r.comment, r.reviewed_by,
               u.full_name AS reviewed_by_name, r.reviewed_at
          FROM public.review r
          JOIN public.users u ON u.id = r.reviewed_by
         WHERE r.version_id = ANY($1::bigint[])
         ORDER BY r.id
        """,
        [v["id"] for v in versions],
    )
    return [dict(r) for r in rows]


async def _verifications_of(
    conn: asyncpg.Connection, versions: Iterable[Mapping[str, Any]]
) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT c.id, c.version_id, c.checked_on, c.source, c.result, c.reference,
               c.proof_original_filename, c.proof_content_type, c.recorded_by,
               u.full_name AS recorded_by_name, c.recorded_at
          FROM public.verification c
          JOIN public.users u ON u.id = c.recorded_by
         WHERE c.version_id = ANY($1::bigint[])
         ORDER BY c.id
        """,
        [v["id"] for v in versions],
    )
    return [dict(r) for r in rows]


async def _latest_checks_of(
    conn: asyncpg.Connection, document_ids: list[int]
) -> tuple[dict[int, asyncpg.Record], dict[int, asyncpg.Record]]:
    """Each Version's latest Review (id, decision) and latest Verification (id,
    result), by Version, for these Documents' Versions. The latest one (the
    highest id) is all the domain functions read of a Version's checks, so a
    summary needs no other rows (NFR-07)."""
    reviews = await conn.fetch(
        """
        SELECT DISTINCT ON (r.version_id) r.id, r.version_id, r.decision
          FROM public.review r JOIN public.version v ON v.id = r.version_id
         WHERE v.document_id = ANY($1::bigint[])
         ORDER BY r.version_id, r.id DESC
        """,
        document_ids,
    )
    verifications = await conn.fetch(
        """
        SELECT DISTINCT ON (c.version_id) c.id, c.version_id, c.result
          FROM public.verification c JOIN public.version v ON v.id = c.version_id
         WHERE v.document_id = ANY($1::bigint[])
         ORDER BY c.version_id, c.id DESC
        """,
        document_ids,
    )
    return {r["version_id"]: r for r in reviews}, {c["version_id"]: c for c in verifications}


@dataclass(frozen=True)
class _Checks:
    """The Reviews and Verifications of a set of Versions, oldest first."""

    reviews: list[dict]
    verifications: list[dict]

    @classmethod
    async def of(cls, conn: asyncpg.Connection, versions: list[dict]) -> "_Checks":
        return cls(await _reviews_of(conn, versions), await _verifications_of(conn, versions))


def by_version(rows: Iterable[Mapping[str, Any]]) -> dict[int, list]:
    """Rows (Reviews or Verifications) grouped by their Version, order kept."""
    grouped: dict[int, list] = {}
    for row in rows:
        grouped.setdefault(row["version_id"], []).append(row)
    return grouped


def rows_of(grouped: Mapping[int, list], versions: Iterable[Mapping[str, Any]]) -> list:
    """The grouped rows of just these Versions, oldest (lowest id) first: the
    subset the domain functions need, so one Document's read does not scan the
    checks of every Version read with it."""
    return sorted((r for v in versions for r in grouped.get(v["id"], ())), key=lambda r: r["id"])


def _summary(
    document: Mapping[str, Any],
    type_fields: Mapping[str, Any],
    version_count: int,
    current: Mapping[str, Any] | None,
    checks: _Checks,
    today: date,
    largest_step: int,
    certificate_current: Mapping[str, Any] | None,
) -> dict:
    """A Document with its Current Version (`current`: domain.current_version
    over its Versions and `checks.reviews`) and Expiry Status. The status
    follows the Effective Expiry, so an Endorsement is capped by
    `certificate_current` (its certificate's Current Version, None when there
    is none). `type_fields` adds the Document Type's fields when `document`
    does not carry them."""
    summary = {
        **document,
        **type_fields,
        "version_count": version_count,
        "current_version": (
            None if current is None
            else {**current, "review_state": domain.review_state(current["id"], checks.reviews)}
        ),
    }
    effective = domain.effective_expiry(summary, certificate_current)
    summary["expiry_status"] = None if effective is None else effective.status(today, largest_step)
    # Kept for coverage and readiness; not part of the response.
    summary["effective"] = effective
    summary["effective_expiry"] = None if effective is None else effective.expiry
    summary["capped_by"] = None if effective is None else effective.capped_by
    summary["certificate_missing"] = effective is not None and effective.certificate_missing
    summary["verified"] = domain.is_verified(current, checks.verifications)
    return summary


async def _certificate_current(
    conn: asyncpg.Connection, document: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    """An Endorsement's certificate's Current Version: the seafarer's Document of
    the type it depends on. None for any other document, or with no certificate."""
    if document["depends_on_id"] is None:
        return None
    certificate_id = await conn.fetchval(
        "SELECT id FROM public.document WHERE seafarer_id = $1 AND document_type_id = $2",
        document["seafarer_id"],
        document["depends_on_id"],
    )
    if certificate_id is None:
        return None
    return (await current_versions(conn, [certificate_id]))[certificate_id]


async def current_versions(conn: asyncpg.Connection, document_ids: list[int]) -> dict[int, dict | None]:
    """Each Document's Current Version with its review state, or None when it
    has none (no Version, or every one rejected)."""
    versions = await _versions_of(conn, document_ids)
    grouped = by_version(await _reviews_of(conn, [v for vs in versions.values() for v in vs]))
    found: dict[int, dict | None] = {}
    for document_id in document_ids:
        own = versions.get(document_id, [])
        reviews = rows_of(grouped, own)
        current = domain.current_version(own, reviews)
        found[document_id] = (
            None if current is None
            else {**current, "review_state": domain.review_state(current["id"], reviews)}
        )
    return found


async def list_for_seafarer(conn: asyncpg.Connection, scope: Scope, seafarer_id: int) -> list[dict]:
    """A seafarer's documents, by type name, each with its Current Version
    and Expiry Status."""
    await seafarers.fetch_in_scope(conn, scope, seafarer_id)
    return await summaries_for(conn, seafarer_id, scope.today)


async def summaries_for(conn: asyncpg.Connection, seafarer_id: int, today: date) -> list[dict]:
    """The document summaries of a seafarer the caller already checked is in Scope."""
    return (await summaries_by_seafarer(conn, [seafarer_id], today)).get(seafarer_id, [])


async def summaries_by_seafarer(
    conn: asyncpg.Connection, seafarer_ids: list[int], today: date, *, brief: bool = False
) -> dict[int, list[dict]]:
    """Each seafarer's document summaries, by type name, for seafarers the
    caller already read through its Scope. Of each Version's Reviews and
    Verifications only the latest is read: it is what the domain rules decide by.
    `brief`: each Current Version carries only its id, issue and expiry dates,
    uploader and upload time, which is all the dashboard reads (NFR-07)."""
    types = {}
    for t in await conn.fetch(_DOCUMENT_TYPES):
        fields = dict(t)
        del fields["id"]
        types[t["id"]] = (fields.pop("name_rank"), fields)
    # As ORDER BY lower(t.name), d.id, without joining the types to every row.
    documents = sorted(
        await conn.fetch(
            "SELECT d.id, d.seafarer_id, d.document_type_id, d.created_at FROM public.document d "
            "WHERE d.seafarer_id = ANY($1::bigint[])",
            seafarer_ids,
        ),
        key=lambda d: (types[d["document_type_id"]][0], d["id"]),
    )
    document_ids = [d["id"] for d in documents]
    versions = await _versions_of(
        conn, document_ids, _BRIEF_VERSION_FIELDS if brief else _VERSION_FIELDS
    )
    latest_review, latest_verification = await _latest_checks_of(conn, document_ids)
    largest_step = await _largest_alert_step(conn)

    # Every Current Version first: an Endorsement is capped by its
    # certificate's. A seafarer has at most one Document per type, so the
    # certificate is the seafarer's Document of the type it depends on.
    read = []
    current_by_type: dict[tuple[int, int], Mapping[str, Any] | None] = {}
    for d in documents:
        depends_on_id = types[d["document_type_id"]][1]["depends_on_id"]
        own = versions.get(d["id"], ())
        checks = _Checks(
            [latest_review[v["id"]] for v in own if v["id"] in latest_review],
            [latest_verification[v["id"]] for v in own if v["id"] in latest_verification],
        )
        current = domain.current_version(own, checks.reviews)
        current_by_type[d["seafarer_id"], d["document_type_id"]] = current
        read.append((d, depends_on_id, len(own), current, checks))

    by_seafarer: dict[int, list[dict]] = {}
    for d, depends_on_id, version_count, current, checks in read:
        certificate = (
            None if depends_on_id is None
            else current_by_type.get((d["seafarer_id"], depends_on_id))
        )
        by_seafarer.setdefault(d["seafarer_id"], []).append(
            _summary(
                d, types[d["document_type_id"]][1], version_count, current, checks,
                today, largest_step, certificate,
            )
        )
    return by_seafarer


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
    checks = await _Checks.of(conn, versions)
    found = _summary(
        document,
        {},
        len(versions),
        domain.current_version(versions, checks.reviews),
        checks,
        scope.today,
        await _largest_alert_step(conn),
        await _certificate_current(conn, document),
    )
    found["versions"] = _history(versions, checks, found["current_version"])
    return found


def _history(
    versions: list[dict], checks: _Checks, current: Mapping[str, Any] | None
) -> list[dict]:
    """Every Version, numbered in upload order, newest first, each with its
    Reviews and Verifications, newest first. A Version whose file an earlier
    one already had is marked with that earlier number."""
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
                "review_state": domain.review_state(v["id"], checks.reviews),
                "reviews": [r for r in reversed(checks.reviews) if r["version_id"] == v["id"]],
                "verifications": [
                    c for c in reversed(checks.verifications) if c["version_id"] == v["id"]
                ],
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
        expiry_not_stated=details.get("expiry_not_stated", False),
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
        current = domain.current_version(versions, await _reviews_of(conn, versions))
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


async def version_in_scope(conn: asyncpg.Connection, scope: Scope, version_id: int) -> dict:
    """A Version with its Document's seafarer; missing -> NotFound, outside the
    Scope -> OutOfScope (recorded against the Version)."""
    row = await conn.fetchrow(
        f"""
        SELECT {scope.where("s")} AS in_scope, d.seafarer_id, {_VERSION_FIELDS}
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
    version = dict(row)
    del version["in_scope"]
    return version


async def issue_file_url(
    conn: asyncpg.Connection, ctx: AuditContext, scope: Scope, storage: FileStorage, version_id: int
) -> dict:
    """A short-lived signed URL for one Version's file, recorded as a download."""
    version = await version_in_scope(conn, scope, version_id)
    return await signed_file_url(
        conn, ctx, storage,
        target_type=VERSION, target_id=version_id, seafarer_id=version["seafarer_id"],
        file=StoredFile(version["file_path"], version["original_filename"], version["content_type"]),
    )


async def signed_file_url(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    storage: FileStorage,
    *,
    target_type: str,
    target_id: int,
    seafarer_id: int,
    file: StoredFile,
) -> dict:
    """A short-lived signed URL for a stored file, recorded as a download
    (*file URL issued*). The record and the URL go together: no record, no URL."""
    filename = download_name(file.original_filename, file.content_type)
    async with conn.transaction():
        await audit.record(
            conn, ctx, AuditAction.FILE_URL_ISSUED,
            target_type=target_type, target_id=target_id, seafarer_id=seafarer_id,
            after={"filename": filename},
        )
        url = await storage.signed_url(file.path, FILE_URL_TTL_SECONDS, filename)
    return {
        "url": url,
        "expires_in": FILE_URL_TTL_SECONDS,
        "filename": filename,
        "content_type": file.content_type,
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
    """An *upload rejected* record for a document file: who, which seafarer
    and type, why, the size and the cleaned name. Never the file's contents."""
    await record_rejected_file(
        conn, ctx, rejection,
        target_type="document_type", target_id=document_type_id, seafarer_id=seafarer_id,
        after={"document_type_id": document_type_id, "size_bytes": size_bytes, "filename": filename},
    )


async def record_rejected_file(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    rejection: Rejection,
    *,
    target_type: str,
    target_id: int,
    seafarer_id: int,
    after: dict,
) -> None:
    """An *upload rejected* record (outcome refused, the reason code), in its
    own transaction."""
    async with conn.transaction():
        await audit.record(
            conn, ctx, AuditAction.UPLOAD_REJECTED,
            target_type=target_type, target_id=target_id, seafarer_id=seafarer_id,
            after=after, reason=rejection.code, outcome="refused",
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
