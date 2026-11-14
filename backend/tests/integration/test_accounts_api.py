"""Account approval flow through the HTTP API (FR-01, FR-02, T5, T7)."""

import json
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.audit import AuditContext
from app.config import settings as app_settings
from app.services import accounts
from tests.conftest import auth_header

ENDPOINTS = [
    ("approve", {"role": "manager", "reason": "r"}),
    ("role", {"role": "manager", "reason": "r"}),
    ("deactivate", {"reason": "r"}),
    ("reactivate", {"reason": "r"}),
]


async def _audit_for(owner_db, account_id: UUID) -> list[dict]:
    rows = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE target_type = 'account' AND target_id = $1 ORDER BY id",
        str(account_id),
    )
    return [dict(r) for r in rows]


# --- /api/me and the request dependency -----------------------------------


async def test_me_returns_status_and_role(client, make_account):
    officer = await make_account(role="crewing_officer", email="officer@example.com")
    res = await client.get("/api/me", headers=auth_header(officer))
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "active"
    assert body["role"] == "crewing_officer"
    assert body["email"] == "officer@example.com"


async def test_me_tells_a_pending_account_it_is_pending(client, make_account):
    pending = await make_account(status="pending")
    res = await client.get("/api/me", headers=auth_header(pending))
    assert res.status_code == 200
    assert res.json()["status"] == "pending"
    assert res.json()["role"] is None


async def test_me_refuses_a_deactivated_account(client, make_account):
    off = await make_account(status="deactivated", role="crewing_officer")
    res = await client.get("/api/me", headers=auth_header(off))
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "account_deactivated"


async def test_token_with_no_users_row_gets_403(client):
    res = await client.get("/api/me", headers=auth_header(uuid4()))
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "no_account"


async def test_missing_token_gets_401(client):
    assert (await client.get("/api/me")).status_code == 401


@pytest.mark.parametrize(
    "status, role, code",
    [("pending", None, "account_pending"), ("deactivated", "administrator", "account_deactivated")],
)
async def test_pending_and_deactivated_accounts_get_403(client, make_account, status, role, code):
    account = await make_account(status=status, role=role)
    res = await client.get("/api/accounts", headers=auth_header(account))
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == code


async def test_a_deactivated_account_is_refused_on_its_next_request(client, make_account):
    await make_account()  # a second administrator, so the guard doesn't apply
    admin = await make_account()
    victim = await make_account()
    assert (await client.get("/api/accounts", headers=auth_header(victim))).status_code == 200

    res = await client.post(
        f"/api/accounts/{victim}/deactivate", json={"reason": "left"}, headers=auth_header(admin)
    )
    assert res.status_code == 200

    res = await client.get("/api/accounts", headers=auth_header(victim))
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "account_deactivated"


# --- wrong role -> 403 for every endpoint --------------------------------------


@pytest.mark.parametrize("role", ["crewing_officer", "manager"])
async def test_list_is_administrator_only(client, make_account, role):
    account = await make_account(role=role)
    res = await client.get("/api/accounts", headers=auth_header(account))
    assert res.status_code == 403
    res = await client.get("/api/accounts/pending-count", headers=auth_header(account))
    assert res.status_code == 403


@pytest.mark.parametrize("path, body", ENDPOINTS)
async def test_changes_are_administrator_only(client, owner_db, make_account, path, body):
    officer = await make_account(role="crewing_officer")
    target = await make_account(status="pending")
    res = await client.post(f"/api/accounts/{target}/{path}", json=body, headers=auth_header(officer))
    assert res.status_code == 403
    row = await owner_db.fetchrow("SELECT status, role FROM public.users WHERE id = $1", target)
    assert (row["status"], row["role"]) == ("pending", None)
    assert await _audit_for(owner_db, target) == []


@pytest.mark.parametrize("path, body", ENDPOINTS)
async def test_unknown_account_gets_404(client, make_account, path, body):
    admin = await make_account()
    res = await client.post(f"/api/accounts/{uuid4()}/{path}", json=body, headers=auth_header(admin))
    assert res.status_code == 404


@pytest.mark.parametrize("path, body", ENDPOINTS)
async def test_a_reason_is_required(client, owner_db, make_account, path, body):
    admin = await make_account()
    target = await make_account(status="pending")
    res = await client.post(
        f"/api/accounts/{target}/{path}", json={**body, "reason": "   "}, headers=auth_header(admin)
    )
    assert res.status_code == 422
    assert await _audit_for(owner_db, target) == []


# --- list ----------------------------------------------------------------------


async def test_list_filters_by_status_and_counts_pending(client, make_account):
    admin = await make_account()
    pending = await make_account(status="pending")
    off = await make_account(status="deactivated", role="manager")

    res = await client.get("/api/accounts", params={"status": "pending"}, headers=auth_header(admin))
    assert res.status_code == 200
    ids = {a["id"] for a in res.json()}
    assert str(pending) in ids
    assert ids.isdisjoint({str(admin), str(off)})
    assert {a["status"] for a in res.json()} == {"pending"}

    res = await client.get("/api/accounts", headers=auth_header(admin))
    assert {str(admin), str(pending), str(off)} <= {a["id"] for a in res.json()}

    res = await client.get("/api/accounts/pending-count", headers=auth_header(admin))
    assert res.json() == {"pending": len(ids)}


# --- approve -------------------------------------------------------------------


async def test_approve_activates_with_a_role_and_is_audited(client, owner_db, make_account):
    admin = await make_account(email="boss@example.com")
    target = await make_account(status="pending")
    res = await client.post(
        f"/api/accounts/{target}/approve",
        json={"role": "crewing_officer", "reason": "New crewing officer"},
        headers={**auth_header(admin), "X-Request-ID": "req-123"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "active"
    assert res.json()["role"] == "crewing_officer"
    assert res.json()["status_reason"] == "New crewing officer"

    [rec] = await _audit_for(owner_db, target)
    assert rec["action"] == "account_approved"
    assert rec["outcome"] == "succeeded"
    assert rec["actor_id"] == admin
    assert rec["actor_email"] == "boss@example.com"
    assert rec["actor_role"] == "administrator"
    assert rec["reason"] == "New crewing officer"
    assert rec["request_id"] == "req-123"
    assert rec["ip"] is not None
    assert json.loads(rec["before"]) == {"status": "pending", "role": None}
    assert json.loads(rec["after"]) == {"status": "active", "role": "crewing_officer"}


async def test_only_a_pending_account_can_be_approved(client, owner_db, make_account):
    admin = await make_account()
    target = await make_account(role="manager")
    res = await client.post(
        f"/api/accounts/{target}/approve",
        json={"role": "administrator", "reason": "x"},
        headers=auth_header(admin),
    )
    assert res.status_code == 409
    assert await _audit_for(owner_db, target) == []


async def test_approve_needs_a_valid_role(client, make_account):
    admin = await make_account()
    target = await make_account(status="pending")
    res = await client.post(
        f"/api/accounts/{target}/approve", json={"role": "captain", "reason": "x"}, headers=auth_header(admin)
    )
    assert res.status_code == 422


# --- change role ---------------------------------------------------------------


async def test_change_role_is_audited(client, owner_db, make_account):
    admin = await make_account()
    target = await make_account(role="crewing_officer")
    res = await client.post(
        f"/api/accounts/{target}/role",
        json={"role": "manager", "reason": "Moved to management"},
        headers=auth_header(admin),
    )
    assert res.status_code == 200
    assert res.json()["role"] == "manager"
    [rec] = await _audit_for(owner_db, target)
    assert rec["action"] == "account_role_changed"
    assert rec["reason"] == "Moved to management"
    assert json.loads(rec["before"]) == {"role": "crewing_officer"}
    assert json.loads(rec["after"]) == {"role": "manager"}


async def test_the_last_active_administrator_cannot_be_demoted_or_deactivated(owner_db, make_account):
    # Over HTTP the acting administrator is always a second active one, so the
    # guard is checked where it lives, as a system action (as make_admin acts).
    last = await make_account()
    await make_account(status="deactivated", role="administrator")  # doesn't count
    conn = await asyncpg.connect(app_settings.database_url)
    outer = conn.transaction()
    await outer.start()
    try:
        # Any other active administrators in this database step aside until
        # the rollback below.
        await conn.execute(
            "UPDATE public.users SET status = 'deactivated'"
            " WHERE status = 'active' AND role = 'administrator' AND id <> $1",
            last,
        )
        with pytest.raises(accounts.AccountConflict, match="last active administrator"):
            await accounts.change_role(conn, AuditContext.system(), last, "manager", "x")
        with pytest.raises(accounts.AccountConflict, match="last active administrator"):
            await accounts.deactivate(conn, AuditContext.system(), last, "x")
    finally:
        await outer.rollback()
        await conn.close()
    row = await owner_db.fetchrow("SELECT status, role FROM public.users WHERE id = $1", last)
    assert (row["status"], row["role"]) == ("active", "administrator")
    assert await _audit_for(owner_db, last) == []


async def test_an_administrator_can_be_demoted_while_another_is_active(client, make_account):
    admin = await make_account()
    other = await make_account()
    res = await client.post(
        f"/api/accounts/{other}/role", json={"role": "manager", "reason": "x"}, headers=auth_header(admin)
    )
    assert res.status_code == 200


async def test_an_administrator_cannot_change_their_own_role_or_status(client, owner_db, make_account):
    await make_account()  # another administrator, so only the self-guard applies
    admin = await make_account()
    for path, body in [
        ("role", {"role": "manager", "reason": "x"}),
        ("deactivate", {"reason": "x"}),
    ]:
        res = await client.post(f"/api/accounts/{admin}/{path}", json=body, headers=auth_header(admin))
        assert res.status_code == 409
        assert "own" in res.json()["detail"]
    row = await owner_db.fetchrow("SELECT status, role FROM public.users WHERE id = $1", admin)
    assert (row["status"], row["role"]) == ("active", "administrator")
    assert await _audit_for(owner_db, admin) == []


async def test_change_role_needs_an_active_account(client, make_account):
    admin = await make_account()
    target = await make_account(status="pending")
    res = await client.post(
        f"/api/accounts/{target}/role", json={"role": "manager", "reason": "x"}, headers=auth_header(admin)
    )
    assert res.status_code == 409


# --- deactivate / reactivate ---------------------------------------------------


async def test_deactivate_is_audited(client, owner_db, make_account):
    admin = await make_account()
    target = await make_account(role="crewing_officer")
    res = await client.post(
        f"/api/accounts/{target}/deactivate", json={"reason": "Left the company"}, headers=auth_header(admin)
    )
    assert res.status_code == 200
    assert res.json()["status"] == "deactivated"
    assert res.json()["role"] == "crewing_officer"  # kept for reactivation
    [rec] = await _audit_for(owner_db, target)
    assert rec["action"] == "account_deactivated"
    assert rec["reason"] == "Left the company"


async def test_rejecting_a_sign_up_is_deactivating_it(client, owner_db, make_account):
    admin = await make_account()
    target = await make_account(status="pending")
    res = await client.post(
        f"/api/accounts/{target}/deactivate", json={"reason": "Unknown person"}, headers=auth_header(admin)
    )
    assert res.status_code == 200
    assert res.json()["status"] == "deactivated"
    assert res.json()["role"] is None


async def test_reactivate_keeps_the_role_and_is_audited(client, owner_db, make_account):
    admin = await make_account()
    target = await make_account(status="deactivated", role="manager")
    res = await client.post(
        f"/api/accounts/{target}/reactivate", json={"reason": "Returned"}, headers=auth_header(admin)
    )
    assert res.status_code == 200
    assert (res.json()["status"], res.json()["role"]) == ("active", "manager")
    [rec] = await _audit_for(owner_db, target)
    assert rec["action"] == "account_reactivated"
    assert rec["reason"] == "Returned"


async def test_reactivating_a_rejected_sign_up_needs_a_role(client, make_account):
    admin = await make_account()
    target = await make_account(status="deactivated", role=None)
    res = await client.post(
        f"/api/accounts/{target}/reactivate", json={"reason": "Mistake"}, headers=auth_header(admin)
    )
    assert res.status_code == 409
    res = await client.post(
        f"/api/accounts/{target}/reactivate",
        json={"reason": "Mistake", "role": "crewing_officer"},
        headers=auth_header(admin),
    )
    assert res.status_code == 200
    assert res.json()["role"] == "crewing_officer"


async def test_only_a_deactivated_account_can_be_reactivated(client, make_account):
    admin = await make_account()
    target = await make_account(role="manager")
    res = await client.post(
        f"/api/accounts/{target}/reactivate", json={"reason": "x"}, headers=auth_header(admin)
    )
    assert res.status_code == 409
