"""Database guards on Reviews and Verifications (FR-11, FR-12; T1).

Reviews and Verifications are append-only for everyone, the owner included,
and the database itself refuses a Review by the Version's uploader.
"""

import os
from datetime import date

import asyncpg
import pytest


@pytest.fixture
async def version(crew, make_account, documents_cleanup, owner_db):
    """A Version uploaded by `uploader`, inserted as the owner."""
    uploader = await make_account(role="crewing_officer")
    reviewer = await make_account(role="crewing_officer")
    seafarer = await crew.seafarer(await crew.position())
    type_id = await owner_db.fetchval(
        "INSERT INTO public.document_type (name, expires) VALUES ('Passport', true) RETURNING id"
    )
    document_id = await owner_db.fetchval(
        "INSERT INTO public.document (seafarer_id, document_type_id) VALUES ($1, $2) RETURNING id",
        seafarer, type_id,
    )
    version_id = await owner_db.fetchval(
        """
        INSERT INTO public.version
            (document_id, file_path, original_filename, content_type, document_number,
             issuing_authority, issue_date, expiry_date, uploaded_by)
        VALUES ($1, 'versions/x.pdf', 'p.pdf', 'application/pdf', 'P-1', 'Ministry',
                '2025-01-01', '2030-01-01', $2)
        RETURNING id
        """,
        document_id, uploader,
    )
    return {"id": version_id, "uploader": uploader, "reviewer": reviewer}


async def _review(conn, version_id, reviewer, decision="accept", comment="Looks right"):
    return await conn.fetchval(
        """
        INSERT INTO public.review (version_id, decision, comment, reviewed_by)
        VALUES ($1, $2, $3, $4) RETURNING id
        """,
        version_id, decision, comment, reviewer,
    )


async def _verification(conn, version_id, recorder, **fields):
    row = {
        "checked_on": date(2026, 1, 5),
        "source": "Phone call to the registry",
        "result": "confirmed",
        "reference": "REF-1",
        **fields,
    }
    return await conn.fetchval(
        """
        INSERT INTO public.verification
            (version_id, checked_on, source, result, reference, recorded_by,
             proof_file_path, proof_original_filename, proof_content_type)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id
        """,
        version_id, row["checked_on"], row["source"], row["result"], row["reference"], recorder,
        row.get("proof_file_path"), row.get("proof_original_filename"), row.get("proof_content_type"),
    )


async def test_the_uploader_cannot_review_their_own_version(version, owner_db):
    with pytest.raises(asyncpg.CheckViolationError, match="uploader"):
        await _review(owner_db, version["id"], version["uploader"])
    assert await _review(owner_db, version["id"], version["reviewer"]) is not None


async def test_the_uploader_is_refused_for_the_app_role_too(version):
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        with pytest.raises(asyncpg.CheckViolationError):
            await _review(conn, version["id"], version["uploader"])
        assert await _review(conn, version["id"], version["reviewer"]) is not None
    finally:
        await conn.close()


@pytest.mark.parametrize(
    "decision, comment", [("approve", "ok"), ("accept", "  "), ("reject", "")]
)
async def test_a_review_needs_a_known_decision_and_a_comment(version, owner_db, decision, comment):
    with pytest.raises(asyncpg.CheckViolationError):
        await _review(owner_db, version["id"], version["reviewer"], decision, comment)


async def test_reviews_and_verifications_are_append_only(version, owner_db):
    review_id = await _review(owner_db, version["id"], version["reviewer"])
    verification_id = await _verification(owner_db, version["id"], version["uploader"])
    for table, row_id in (("review", review_id), ("verification", verification_id)):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await owner_db.execute(f"UPDATE public.{table} SET version_id = version_id WHERE id = $1", row_id)
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await owner_db.execute(f"DELETE FROM public.{table} WHERE id = $1", row_id)

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        for statement in (
            "UPDATE public.review SET comment = 'x'",
            "DELETE FROM public.review",
            "UPDATE public.verification SET result = 'confirmed'",
            "DELETE FROM public.verification",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.execute(statement)
    finally:
        await conn.close()


async def test_there_is_no_four_eyes_rule_for_verifications(version, owner_db):
    assert await _verification(owner_db, version["id"], version["uploader"]) is not None


@pytest.mark.parametrize(
    "fields",
    [
        {"result": "maybe"},
        {"source": " "},
        {"reference": ""},
        # The proof file's path, name and type go together.
        {"proof_file_path": "proofs/x.pdf"},
        {"proof_file_path": "proofs/x.pdf", "proof_original_filename": "x.pdf",
         "proof_content_type": "text/html"},
    ],
)
async def test_a_verification_keeps_its_rules(version, owner_db, fields):
    with pytest.raises(asyncpg.CheckViolationError):
        await _verification(owner_db, version["id"], version["uploader"], **fields)


async def test_a_verification_with_a_proof_file(version, owner_db):
    assert await _verification(
        owner_db, version["id"], version["uploader"], result="not_confirmed",
        proof_file_path="proofs/x.pdf", proof_original_filename="letter.pdf",
        proof_content_type="application/pdf",
    ) is not None
