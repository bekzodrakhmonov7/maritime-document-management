import email
import pytest
from datetime import date, timedelta
from uuid import uuid4

from aiosmtpd.controller import Controller
from fastapi_mail import ConnectionConfig, FastMail

from app.services import notification_service
from app.worker.run_expiry_scan import _run_scan


class _TestSmtpHandler:
    def __init__(self):
        self.messages = []

    async def handle_DATA(self, server, session, envelope):
        self.messages.append({
            "from": envelope.mail_from,
            "to": envelope.rcpt_tos,
            "content": envelope.content.decode("utf-8", errors="replace"),
        })
        return "250 OK"


@pytest.mark.asyncio
async def test_smtp_dispatch(db_conn):
    handler = _TestSmtpHandler()
    controller = Controller(handler, hostname="127.0.0.1", port=2525)
    controller.start()

    # Override fast_mail to point at test SMTP sink
    test_conf = ConnectionConfig(
        MAIL_USERNAME="",
        MAIL_PASSWORD="",
        MAIL_FROM="alerts@maritime.example.com",
        MAIL_PORT=2525,
        MAIL_SERVER="127.0.0.1",
        MAIL_STARTTLS=False,
        MAIL_SSL_TLS=False,
        USE_CREDENTIALS=False,
    )
    original_fast_mail = notification_service.fast_mail
    notification_service.fast_mail = FastMail(test_conf)

    # Insert an administrator so get_admin_recipients returns a real address.
    # The handle_new_user trigger creates a public.users row on auth.users insert;
    # we then promote it to administrator.
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

        # Give aiosmtpd a moment to process
        import asyncio
        await asyncio.sleep(0.3)

        assert len(handler.messages) >= 1
        msg = handler.messages[0]
        parsed = email.message_from_string(msg["content"])
        subject = parsed["Subject"]
        assert "Document Expiry Alert" in subject
        assert "expires in 90 days" in subject
        assert admin_email in msg["to"]

        # Extract HTML body from multipart message
        body = ""
        if parsed.is_multipart():
            for part in parsed.walk():
                if part.get_content_type() == "text/html":
                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                    break
        else:
            body = parsed.get_payload(decode=True).decode("utf-8", errors="replace")

        assert "Jack Sparrow" in body
        assert "SMTP001" in body
        assert "90" in body
        assert "severity-early" in body
    finally:
        notification_service.fast_mail = original_fast_mail
        controller.stop()
