import pytest
import pytest_asyncio
from datetime import date, timedelta
from uuid import uuid4

from app.services.expiry_service import scan_and_transition


@pytest.mark.asyncio
async def test_verified_to_expiring_soon_at_90_days(db_conn):
    # Seed a verified document expiring in exactly 90 days
    today = date(2025, 6, 1)
    expiry = today + timedelta(days=90)

    seafarer_id = await db_conn.fetchval(
        """
        INSERT INTO public.seafarer (vessel_id, first_name, last_name, rank)
        VALUES (NULL, 'John', 'Doe', 'Captain')
        RETURNING seafarer_id
        """
    )
    doc_type_id = await db_conn.fetchval(
        "INSERT INTO public.document_type (type_name, is_mandatory) VALUES ($1, true) RETURNING doc_type_id",
        f"Passport-{uuid4().hex[:8]}",
    )
    doc_id = await db_conn.fetchval(
        """
        INSERT INTO public.document (seafarer_id, doc_type_id, document_number, issue_date, expiry_date, file_path, status)
        VALUES ($1, $2, 'DOC001', $3, $4, '/fake/path.pdf', 'verified')
        RETURNING document_id
        """,
        seafarer_id,
        doc_type_id,
        today - timedelta(days=365),
        expiry,
    )

    count = await scan_and_transition(db_conn, today)
    assert count == 1

    status = await db_conn.fetchval(
        "SELECT status FROM public.document WHERE document_id = $1", doc_id
    )
    assert status == "expiring_soon"


@pytest.mark.asyncio
async def test_expiring_soon_to_expired_at_0_days(db_conn):
    today = date(2025, 6, 1)
    expiry = today

    seafarer_id = await db_conn.fetchval(
        """
        INSERT INTO public.seafarer (vessel_id, first_name, last_name, rank)
        VALUES (NULL, 'John', 'Doe', 'Captain')
        RETURNING seafarer_id
        """
    )
    doc_type_id = await db_conn.fetchval(
        "INSERT INTO public.document_type (type_name, is_mandatory) VALUES ($1, true) RETURNING doc_type_id",
        f"Passport-{uuid4().hex[:8]}",
    )
    doc_id = await db_conn.fetchval(
        """
        INSERT INTO public.document (seafarer_id, doc_type_id, document_number, issue_date, expiry_date, file_path, status)
        VALUES ($1, $2, 'DOC002', $3, $4, '/fake/path.pdf', 'expiring_soon')
        RETURNING document_id
        """,
        seafarer_id,
        doc_type_id,
        today - timedelta(days=365),
        expiry,
    )

    count = await scan_and_transition(db_conn, today)
    assert count == 1

    status = await db_conn.fetchval(
        "SELECT status FROM public.document WHERE document_id = $1", doc_id
    )
    assert status == "expired"


@pytest.mark.asyncio
async def test_rejected_no_transition(db_conn):
    today = date(2025, 6, 1)
    expiry = today - timedelta(days=10)

    seafarer_id = await db_conn.fetchval(
        """
        INSERT INTO public.seafarer (vessel_id, first_name, last_name, rank)
        VALUES (NULL, 'John', 'Doe', 'Captain')
        RETURNING seafarer_id
        """
    )
    doc_type_id = await db_conn.fetchval(
        "INSERT INTO public.document_type (type_name, is_mandatory) VALUES ($1, true) RETURNING doc_type_id",
        f"Passport-{uuid4().hex[:8]}",
    )
    doc_id = await db_conn.fetchval(
        """
        INSERT INTO public.document (seafarer_id, doc_type_id, document_number, issue_date, expiry_date, file_path, status)
        VALUES ($1, $2, 'DOC003', $3, $4, '/fake/path.pdf', 'rejected')
        RETURNING document_id
        """,
        seafarer_id,
        doc_type_id,
        today - timedelta(days=365),
        expiry,
    )

    count = await scan_and_transition(db_conn, today)
    assert count == 0

    status = await db_conn.fetchval(
        "SELECT status FROM public.document WHERE document_id = $1", doc_id
    )
    assert status == "rejected"
