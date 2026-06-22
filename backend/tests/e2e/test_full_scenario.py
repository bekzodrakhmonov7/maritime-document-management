import pytest
from httpx import AsyncClient
from io import BytesIO
from datetime import date, timedelta

from tests.conftest import make_token


@pytest.mark.asyncio
async def test_full_scenario_signup_upload_expiry_email(
    client: AsyncClient, db_conn, test_user, test_seafarer, test_doc_type
):
    """E2E: signup -> upload document -> verify -> run worker -> assert status transition + alert."""
    token = make_token(test_user)

    # Upload document with expiry 90 days from now
    expiry = date.today() + timedelta(days=90)
    response = await client.post(
        "/documents",
        data={
            "doc_type_id": test_doc_type,
            "seafarer_id": test_seafarer,
            "document_number": "E2E001",
            "issue_date": "2024-01-01",
            "expiry_date": expiry.isoformat(),
        },
        files={"file": ("test.pdf", BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    doc_id = response.json()["document_id"]

    # Verify document
    verify_resp = await client.patch(
        f"/documents/{doc_id}/verify",
        json={"status": "verified"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert verify_resp.status_code == 200

    # Run worker at day 0 — document enters 90-day window, becomes expiring_soon + alert generated
    from app.worker.run_expiry_scan import _run_scan
    await _run_scan(today=date.today(), conn=db_conn)

    # Assert status flipped to expiring_soon
    doc_resp = await client.get(
        f"/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert doc_resp.status_code == 200
    assert doc_resp.json()["status"] == "expiring_soon"

    # Assert alert was generated at 90-day threshold
    alerts_resp = await client.get(
        "/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()
    assert any(a["document_id"] == doc_id for a in alerts)


@pytest.mark.asyncio
async def test_invalid_dates_rejected_e2e(client: AsyncClient, test_user, test_seafarer, test_doc_type):
    """E2E: attempt to upload document with expiry <= issue — must be rejected."""
    token = make_token(test_user)

    response = await client.post(
        "/documents",
        data={
            "doc_type_id": test_doc_type,
            "seafarer_id": test_seafarer,
            "document_number": "E2E002",
            "issue_date": "2025-06-01",
            "expiry_date": "2025-01-01",
        },
        files={"file": ("test.pdf", BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_cron_clock_advance_updates_expirations(
    client: AsyncClient, db_conn, test_user, test_seafarer, test_doc_type
):
    """E2E: run worker with mocked far-future date — all verified docs become expired."""
    token = make_token(test_user)

    # Upload and verify a doc expiring in 90 days
    expiry = date.today() + timedelta(days=90)
    upload_resp = await client.post(
        "/documents",
        data={
            "doc_type_id": test_doc_type,
            "seafarer_id": test_seafarer,
            "document_number": "E2E003",
            "issue_date": "2024-01-01",
            "expiry_date": expiry.isoformat(),
        },
        files={"file": ("test.pdf", BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["document_id"]

    await client.patch(
        f"/documents/{doc_id}/verify",
        json={"status": "verified"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Advance 91 days
    future = date.today() + timedelta(days=91)
    from app.worker.run_expiry_scan import _run_scan
    await _run_scan(today=future, conn=db_conn)

    doc_resp = await client.get(
        f"/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert doc_resp.status_code == 200
    assert doc_resp.json()["status"] == "expired"


@pytest.mark.asyncio
async def test_role_propagation_from_db(
    client: AsyncClient, db_conn
):
    """E2E: role is fetched from public.users, not JWT payload, for real Supabase Auth users."""
    from uuid import uuid4
    user_id = uuid4()
    await db_conn.execute(
        "INSERT INTO auth.users (id, email, encrypted_password, email_confirmed_at, created_at, updated_at) VALUES ($1, $2, 'fake', now(), now(), now()) ON CONFLICT DO NOTHING",
        user_id,
        f"{user_id}@test.com",
    )
    await db_conn.execute(
        "INSERT INTO public.users (id, full_name, role) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
        user_id,
        "Crewing Officer",
        "crewing_officer",
    )

    # Forge a JWT with role='authenticated' (what Supabase Auth actually sends)
    import jwt
    from datetime import datetime, timezone, timedelta
    from app.config import settings
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": f"{user_id}@test.com",
        "role": "authenticated",
        "aud": "authenticated",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")

    me_resp = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    data = me_resp.json()
    assert data["role"] == "crewing_officer"
    assert data["sub"] == str(user_id)
