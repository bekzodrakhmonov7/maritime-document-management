"""Reviews and Verifications (FR-11, FR-12; T1, T7, T8).

Both are recorded on one Version, through its seafarer's Scope, and are only
ever added. A Review is a second staff member's accept or reject with a
comment; the uploader never reviews their own Version (refused here, and by a
trigger as the backstop). The latest Review decides, so a rejected newest
Version hands the Current Version back to the previous non-rejected one.

A Verification is a check with the issuing authority, with an optional proof
file that has passed the Safety Checks. There is no four-eyes rule for it.
Verified (the Current Version's latest Verification is confirmed) is computed
on read in app/domain.py.
"""

from datetime import date
from uuid import UUID

import asyncpg

from app import audit, domain
from app.audit import AuditAction, AuditContext
from app.scope import Scope
from app.services import documents
from app.services.documents import VERSION, StoredFile
from app.services.errors import Invalid, NotFound, OutOfScope, OwnVersion
from app.storage import FileStorage
from app.upload_safety import Rejection

VERIFICATION = "verification"
PROOF = "verification_proof"


async def review(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    scope: Scope,
    account_id: UUID,
    version_id: int,
    decision: str,
    comment: str,
) -> dict:
    """Accept or reject a Version. Answers with the whole Document, whose
    Current Version may have moved."""
    async with conn.transaction():
        version = await documents.version_in_scope(conn, scope, version_id)
        if version["uploaded_by"] == account_id:
            raise OwnVersion("You uploaded this version, so someone else has to review it.")
        earlier = await conn.fetch(
            "SELECT id, version_id, decision FROM public.review WHERE version_id = $1", version_id
        )
        before = domain.review_state(version_id, earlier)
        review_id = await conn.fetchval(
            """
            INSERT INTO public.review (version_id, decision, comment, reviewed_by)
            VALUES ($1, $2, $3, $4) RETURNING id
            """,
            version_id, decision, comment, account_id,
        )
        await audit.record(
            conn, ctx, AuditAction.VERSION_REVIEWED,
            target_type=VERSION, target_id=version_id, seafarer_id=version["seafarer_id"],
            before={"review_state": before},
            after={
                "review_id": review_id,
                "document_id": version["document_id"],
                "decision": decision,
                "comment": comment,
            },
        )
        return await documents.get(conn, scope, version["document_id"])


async def check_can_verify(conn: asyncpg.Connection, scope: Scope, version_id: int) -> dict:
    """Refuse early, before a proof file is read: the Version missing or out
    of Scope. Returns the Version with its seafarer."""
    return await documents.version_in_scope(conn, scope, version_id)


def check_details(details: dict, today: date) -> None:
    """A Verification can't be dated after today in the company time zone."""
    if details["checked_on"] > today:
        raise Invalid("The verification date can't be in the future.")


async def add_verification(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    scope: Scope,
    account_id: UUID,
    version_id: int,
    details: dict,
    proof: StoredFile | None,
) -> dict:
    """Record a Verification, with its proof file already in Storage. One
    transaction for the row and its Audit Record; if it fails, the caller
    removes the stored proof file."""
    async with conn.transaction():
        version = await documents.version_in_scope(conn, scope, version_id)
        check_details(details, scope.today)
        verification_id = await conn.fetchval(
            """
            INSERT INTO public.verification
                (version_id, checked_on, source, result, reference, recorded_by,
                 proof_file_path, proof_original_filename, proof_content_type)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
            """,
            version_id,
            details["checked_on"], details["source"], details["result"], details["reference"],
            account_id,
            proof and proof.path, proof and proof.original_filename, proof and proof.content_type,
        )
        await audit.record(
            conn, ctx, AuditAction.VERIFICATION_RECORDED,
            target_type=VERSION, target_id=version_id, seafarer_id=version["seafarer_id"],
            after={
                "verification_id": verification_id,
                "document_id": version["document_id"],
                **details,
                "proof_filename": proof and proof.original_filename,
            },
        )
        return await documents.get(conn, scope, version["document_id"])


async def record_proof_rejected(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    version: dict,
    rejection: Rejection,
    size_bytes: int | None,
    filename: str | None,
) -> None:
    """An *upload rejected* record for a proof file that failed a Safety Check."""
    await documents.record_rejected_file(
        conn, ctx, rejection,
        target_type=VERSION, target_id=version["id"], seafarer_id=version["seafarer_id"],
        after={"purpose": PROOF, "size_bytes": size_bytes, "filename": filename},
    )


async def issue_proof_url(
    conn: asyncpg.Connection, ctx: AuditContext, scope: Scope, storage: FileStorage, verification_id: int
) -> dict:
    """A short-lived signed URL for a Verification's proof file, recorded as a
    download. A Verification without a proof file has none (404)."""
    row = await conn.fetchrow(
        f"""
        SELECT {scope.where("s")} AS in_scope, d.seafarer_id,
               c.proof_file_path, c.proof_original_filename, c.proof_content_type
          FROM public.verification c
          JOIN public.version v ON v.id = c.version_id
          JOIN public.document d ON d.id = v.document_id
          JOIN public.seafarer s ON s.id = d.seafarer_id
         WHERE c.id = $1
        """,
        verification_id,
    )
    if row is None:
        raise NotFound()
    if not row["in_scope"]:
        raise OutOfScope(VERIFICATION, verification_id, row["seafarer_id"])
    if row["proof_file_path"] is None:
        raise NotFound()
    return await documents.signed_file_url(
        conn, ctx, storage,
        target_type=VERIFICATION, target_id=verification_id, seafarer_id=row["seafarer_id"],
        file=StoredFile(row["proof_file_path"], row["proof_original_filename"], row["proof_content_type"]),
    )
