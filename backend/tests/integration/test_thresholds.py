import pytest
from httpx import AsyncClient
from uuid import uuid4

from tests.conftest import make_token


@pytest.mark.asyncio
async def test_get_thresholds(client: AsyncClient, db_conn) -> None:
    user_id = uuid4()
    await db_conn.execute(
        "INSERT INTO auth.users (id, email, encrypted_password, email_confirmed_at, created_at, updated_at) VALUES ($1, $2, 'fake', now(), now(), now()) ON CONFLICT DO NOTHING",
        user_id, f"{user_id}@test.com",
    )
    await db_conn.execute(
        "INSERT INTO public.users (id, full_name, role) VALUES ($1, $2, $3) ON CONFLICT (id) DO UPDATE SET role = EXCLUDED.role, full_name = EXCLUDED.full_name",
        user_id, "Test User", "administrator",
    )
    token = make_token(user_id)
    resp = await client.get(
        "/alerts/thresholds",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["days_90"] == 90
    assert data["days_60"] == 60
    assert data["days_30"] == 30


@pytest.mark.asyncio
async def test_patch_thresholds_admin(client: AsyncClient, db_conn) -> None:
    user_id = uuid4()
    await db_conn.execute(
        "INSERT INTO auth.users (id, email, encrypted_password, email_confirmed_at, created_at, updated_at) VALUES ($1, $2, 'fake', now(), now(), now()) ON CONFLICT DO NOTHING",
        user_id, f"{user_id}@test.com",
    )
    await db_conn.execute(
        "INSERT INTO public.users (id, full_name, role) VALUES ($1, $2, $3) ON CONFLICT (id) DO UPDATE SET role = EXCLUDED.role, full_name = EXCLUDED.full_name",
        user_id, "Test User", "administrator",
    )
    token = make_token(user_id)
    resp = await client.patch(
        "/alerts/thresholds",
        json={"days_90": 85, "days_60": 55, "days_30": 25},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["days_90"] == 85
    assert data["days_60"] == 55
    assert data["days_30"] == 25

    # Verify GET reflects the change
    get_resp = await client.get(
        "/alerts/thresholds",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json() == data


@pytest.mark.asyncio
async def test_patch_thresholds_crewing_officer_forbidden(
    client: AsyncClient, crewing_officer_token: str
) -> None:
    resp = await client.patch(
        "/alerts/thresholds",
        json={"days_90": 80},
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_thresholds_invalid_ordering(client: AsyncClient, db_conn) -> None:
    user_id = uuid4()
    await db_conn.execute(
        "INSERT INTO auth.users (id, email, encrypted_password, email_confirmed_at, created_at, updated_at) VALUES ($1, $2, 'fake', now(), now(), now()) ON CONFLICT DO NOTHING",
        user_id, f"{user_id}@test.com",
    )
    await db_conn.execute(
        "INSERT INTO public.users (id, full_name, role) VALUES ($1, $2, $3) ON CONFLICT (id) DO UPDATE SET role = EXCLUDED.role, full_name = EXCLUDED.full_name",
        user_id, "Test User", "administrator",
    )
    token = make_token(user_id)
    resp = await client.patch(
        "/alerts/thresholds",
        json={"days_90": 30, "days_60": 60, "days_30": 90},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_thresholds_negative_values(client: AsyncClient, db_conn) -> None:
    user_id = uuid4()
    await db_conn.execute(
        "INSERT INTO auth.users (id, email, encrypted_password, email_confirmed_at, created_at, updated_at) VALUES ($1, $2, 'fake', now(), now(), now()) ON CONFLICT DO NOTHING",
        user_id, f"{user_id}@test.com",
    )
    await db_conn.execute(
        "INSERT INTO public.users (id, full_name, role) VALUES ($1, $2, $3) ON CONFLICT (id) DO UPDATE SET role = EXCLUDED.role, full_name = EXCLUDED.full_name",
        user_id, "Test User", "administrator",
    )
    token = make_token(user_id)
    resp = await client.patch(
        "/alerts/thresholds",
        json={"days_90": -10},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_thresholds_no_changes(client: AsyncClient, db_conn) -> None:
    user_id = uuid4()
    await db_conn.execute(
        "INSERT INTO auth.users (id, email, encrypted_password, email_confirmed_at, created_at, updated_at) VALUES ($1, $2, 'fake', now(), now(), now()) ON CONFLICT DO NOTHING",
        user_id, f"{user_id}@test.com",
    )
    await db_conn.execute(
        "INSERT INTO public.users (id, full_name, role) VALUES ($1, $2, $3) ON CONFLICT (id) DO UPDATE SET role = EXCLUDED.role, full_name = EXCLUDED.full_name",
        user_id, "Test User", "administrator",
    )
    token = make_token(user_id)
    # Send empty payload (no fields changed)
    resp = await client.patch(
        "/alerts/thresholds",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
