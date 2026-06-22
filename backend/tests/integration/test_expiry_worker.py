import pytest
from datetime import date, timedelta
from uuid import uuid4

from app.worker.run_expiry_scan import _run_scan


@pytest.mark.asyncio
async def test_expiry_worker_transitions_and_alerts(db_conn):
    today = date(2025, 6, 1)

    # Seed seafarer
    seafarer_id = await db_conn.fetchval(
        """
        INSERT INTO public.seafarer (vessel_id, first_name, last_name, rank)
        VALUES (NULL, 'Jane', 'Smith', 'Officer')
        RETURNING seafarer_id
        """
    )

    # Seed document types
    doc_type_1 = await db_conn.fetchval(
        "INSERT INTO public.document_type (type_name, is_mandatory) VALUES ($1, true) RETURNING doc_type_id",
        f"Passport-{uuid4().hex[:8]}",
    )
    doc_type_2 = await db_conn.fetchval(
        "INSERT INTO public.document_type (type_name, is_mandatory) VALUES ($1, true) RETURNING doc_type_id",
        f"Visa-{uuid4().hex[:8]}",
    )

    # Doc 1: verified, expires in 90 days -> should transition to expiring_soon
    doc1 = await db_conn.fetchval(
        """
        INSERT INTO public.document (seafarer_id, doc_type_id, document_number, issue_date, expiry_date, file_path, status)
        VALUES ($1, $2, 'DOC001', $3, $4, '/fake/1.pdf', 'verified')
        RETURNING document_id
        """,
        seafarer_id,
        doc_type_1,
        today - timedelta(days=365),
        today + timedelta(days=90),
    )

    # Doc 2: expiring_soon, expires today -> should transition to expired
    doc2 = await db_conn.fetchval(
        """
        INSERT INTO public.document (seafarer_id, doc_type_id, document_number, issue_date, expiry_date, file_path, status)
        VALUES ($1, $2, 'DOC002', $3, $4, '/fake/2.pdf', 'expiring_soon')
        RETURNING document_id
        """,
        seafarer_id,
        doc_type_2,
        today - timedelta(days=365),
        today,
    )

    summary = await _run_scan(today, db_conn)

    assert summary["transitioned"] == 2
    assert summary["alerts_generated"] >= 1

    status1 = await db_conn.fetchval(
        "SELECT status FROM public.document WHERE document_id = $1", doc1
    )
    status2 = await db_conn.fetchval(
        "SELECT status FROM public.document WHERE document_id = $1", doc2
    )
    assert status1 == "expiring_soon"
    assert status2 == "expired"

    alerts = await db_conn.fetch(
        "SELECT * FROM public.alert WHERE document_id = $1", doc1
    )
    assert len(alerts) >= 1
