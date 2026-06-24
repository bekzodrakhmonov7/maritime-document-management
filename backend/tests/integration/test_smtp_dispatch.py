import pytest
from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

from app.services import notification_service
from app.worker.run_expiry_scan import _run_scan


@pytest.mark.asyncio
async def test_smtp_dispatch(db_conn):
    captured_emails: list[dict] = []

    def fake_send(params):
        captured_emails.append(params)
        return {"id": "test-id"}

    with patch.object(notification_service.resend, "Emails") as mock_emails:
        mock_emails.send.side_effect = fake_send

        admin_email = "test-admin@example.com"
        admin_id = uuid4()
        await db_conn.execute(
            """
            INSERT INTO auth.users (id, email, encrypted_password, email_confirmed_at, created_at, updated_at)
            VALUES ($1, $2, 'fake', now(), now(), now())
            """,
            admin_id,
            admin_email,
        )
        await db_conn.execute(
            "UPDATE public.users SET role = 'administrator', full_name = 'Test Admin' WHERE id = $1",
            admin_id,
        )

        try:
            today = date(2025, 6, 1)

            seafarer_id = await db_conn.fetchval(
                """
                INSERT INTO public.seafarer (vessel_id, first_name, last_name, rank)
                VALUES (NULL, 'Jack', 'Sparrow', 'Captain')
                RETURNING seafarer_id
                """
            )
            doc_type_id = await db_conn.fetchval(
                "INSERT INTO public.document_type (type_name, is_mandatory) VALUES ($1, true) RETURNING doc_type_id",
                f"Passport-{uuid4().hex[:8]}",
            )
            await db_conn.execute(
                """
                INSERT INTO public.document (seafarer_id, doc_type_id, document_number, issue_date, expiry_date, file_path, status)
                VALUES ($1, $2, 'SMTP001', $3, $4, '/fake/smtp.pdf', 'verified')
                """,
                seafarer_id,
                doc_type_id,
                today - timedelta(days=365),
                today + timedelta(days=90),
            )

            summary = await _run_scan(today, db_conn)
            assert summary["emails_sent"] >= 1
            assert summary["emails_failed"] == 0

            assert len(captured_emails) >= 1
            msg = captured_emails[0]
            assert "Document Expiry Alert" in msg["subject"]
            assert "expires in 90 days" in msg["subject"]
            assert admin_email in msg["to"]
            assert "Jack Sparrow" in msg["html"]
            assert "SMTP001" in msg["html"]
            assert "90" in msg["html"]
            assert "severity-early" in msg["html"]
        finally:
            pass
