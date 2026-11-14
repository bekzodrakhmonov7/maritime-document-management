"""Refused access reaches the Audit Log (T7, ADR 0002).

One exception-handling point writes *access refused*, in its own
transaction, for every 403, every out-of-Scope 404 on a record that exists,
and every refused request from a pending or deactivated account. A 404 for
an id that doesn't exist writes nothing.
"""

from uuid import UUID, uuid4

import asyncpg
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user, get_db
from app.models.auth import UserPayload
from app.refused_access import OutOfScope
from tests.conftest import auth_header


async def _refusals_by(owner_db, actor_id: UUID) -> list[dict]:
    rows = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE action = 'access_refused' AND actor_id = $1"
        " ORDER BY id",
        actor_id,
    )
    return [dict(r) for r in rows]


async def test_a_403_for_the_wrong_role_writes_a_refused_record(client, owner_db, make_account):
    officer = await make_account(role="crewing_officer", email="refused-officer@example.com")

    res = await client.get("/api/accounts", headers=auth_header(officer))

    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "wrong_role"
    [rec] = await _refusals_by(owner_db, officer)
    assert rec["outcome"] == "refused"
    assert rec["actor_email"] == "refused-officer@example.com"
    assert rec["actor_role"] == "crewing_officer"
    assert rec["reason"] == "wrong_role"
    assert rec["target_type"] == "request"
    assert rec["target_id"] == "GET /api/accounts"
    assert str(rec["ip"]) == "127.0.0.1"
    assert rec["request_id"] == res.headers["x-request-id"]


async def test_a_pending_account_is_recorded_when_refused(client, owner_db, make_account):
    pending = await make_account(status="pending")

    assert (await client.get("/api/accounts", headers=auth_header(pending))).status_code == 403

    [rec] = await _refusals_by(owner_db, pending)
    assert rec["reason"] == "account_pending"
    assert rec["actor_role"] is None


async def test_a_deactivated_account_is_recorded_on_every_request(
    client, owner_db, make_account
):
    off = await make_account(status="deactivated", role="crewing_officer")

    for path in ("/api/me", "/api/accounts"):
        assert (await client.get(path, headers=auth_header(off))).status_code == 403

    recs = await _refusals_by(owner_db, off)
    assert [r["reason"] for r in recs] == ["account_deactivated", "account_deactivated"]
    assert [r["target_id"] for r in recs] == ["GET /api/me", "GET /api/accounts"]


async def test_a_token_with_no_account_is_recorded(client, owner_db):
    stranger = uuid4()

    assert (await client.get("/api/me", headers=auth_header(stranger))).status_code == 403

    [rec] = await _refusals_by(owner_db, stranger)
    assert rec["reason"] == "no_account"
    assert rec["actor_email"] is None


async def test_a_pending_account_reading_its_own_status_is_not_refused(
    client, owner_db, make_account
):
    pending = await make_account(status="pending")

    assert (await client.get("/api/me", headers=auth_header(pending))).status_code == 200

    assert await _refusals_by(owner_db, pending) == []


async def test_a_404_for_a_non_existent_id_writes_nothing(client, owner_db, make_account):
    admin = await make_account()
    missing = uuid4()

    res = await client.post(
        f"/api/accounts/{missing}/approve",
        json={"role": "manager", "reason": "r"},
        headers=auth_header(admin),
    )

    assert res.status_code == 404
    assert await _refusals_by(owner_db, admin) == []
    assert await owner_db.fetchval(
        "SELECT count(*) FROM public.audit_log WHERE target_id = $1", str(missing)
    ) == 0


async def test_an_out_of_scope_404_writes_a_refused_record(app, owner_db, make_account):
    # No scoped endpoint exists yet (seafarers come in S5), so this route
    # stands in for one: the record exists but is outside the caller's Scope.
    @app.get("/api/test-scoped/{seafarer_id}")
    async def scoped(
        seafarer_id: int,
        db: asyncpg.Connection = Depends(get_db),
        user: UserPayload = Depends(get_current_user),
    ):
        # The refused request's own transaction rolls back; the record stays.
        async with db.transaction():
            await db.execute("SELECT 1")
            raise OutOfScope("seafarer", seafarer_id, seafarer_id=seafarer_id)

    officer = await make_account(role="crewing_officer")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/api/test-scoped/4242", headers=auth_header(officer))

    assert res.status_code == 404
    assert res.json() == {"detail": "Not found"}
    [rec] = await _refusals_by(owner_db, officer)
    assert rec["reason"] == "out_of_scope"
    assert rec["target_type"] == "seafarer"
    assert rec["target_id"] == "4242"
    assert rec["seafarer_id"] == 4242
    assert rec["outcome"] == "refused"


async def test_a_refused_change_leaves_only_the_refused_record(client, owner_db, make_account):
    officer = await make_account(role="crewing_officer")
    target = await make_account(status="pending")

    res = await client.post(
        f"/api/accounts/{target}/approve",
        json={"role": "manager", "reason": "r"},
        headers=auth_header(officer),
    )

    assert res.status_code == 403
    assert await owner_db.fetchval(
        "SELECT status FROM public.users WHERE id = $1", target
    ) == "pending"
    [rec] = await _refusals_by(owner_db, officer)
    assert rec["target_id"] == f"POST /api/accounts/{target}/approve"
