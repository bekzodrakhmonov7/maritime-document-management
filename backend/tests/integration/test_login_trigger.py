"""Login succeeded is copied from Supabase's own auth audit table (R1, T7).

GoTrue writes one `auth.audit_log_entries` row per sign-in; a trigger copies
it into the Audit Log, so sign-ins that skip our UI are recorded too. These
tests insert the row GoTrue would write. The end-to-end version against a
running Supabase Auth lives in test_sign_in_api.py.
"""

import json
from uuid import UUID, uuid4

import pytest


async def _gotrue_writes(owner_db, action: str, actor_id: object, email: str,
                         ip: str = "203.0.113.7") -> None:
    payload = {
        "action": action,
        "actor_id": str(actor_id),
        "actor_username": email,
        "actor_via_sso": False,
        "log_type": "account",
        "traits": {"provider": "email"},
    }
    await owner_db.execute(
        """
        INSERT INTO auth.audit_log_entries (instance_id, id, payload, created_at, ip_address)
        VALUES ('00000000-0000-0000-0000-000000000000', $1, $2::json, now(), $3)
        """,
        uuid4(),
        json.dumps(payload),
        ip,
    )


async def _logins_of(owner_db, account_id: UUID) -> list[dict]:
    rows = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE action = 'login_succeeded' AND actor_id = $1",
        account_id,
    )
    return [dict(r) for r in rows]


async def test_a_supabase_login_writes_login_succeeded(owner_db, make_account):
    officer = await make_account(role="crewing_officer", email="trigger-officer@example.com")

    await _gotrue_writes(owner_db, "login", officer, "trigger-officer@example.com")

    [rec] = await _logins_of(owner_db, officer)
    assert rec["outcome"] == "succeeded"
    assert rec["actor_email"] == "trigger-officer@example.com"
    assert rec["actor_role"] == "crewing_officer"
    assert str(rec["ip"]) == "203.0.113.7"
    assert rec["target_type"] == "account"
    assert rec["target_id"] == str(officer)


async def test_the_first_sign_in_that_completes_registration_writes_login_succeeded(
    owner_db, make_account
):
    # GoTrue writes user_signedup, not login, when the first code completes registration.
    newcomer = await make_account(status="pending", email="trigger-newcomer@example.com")

    await _gotrue_writes(owner_db, "user_signedup", newcomer, "trigger-newcomer@example.com")

    [rec] = await _logins_of(owner_db, newcomer)
    assert rec["outcome"] == "succeeded"
    assert rec["actor_id"] == newcomer
    assert rec["actor_email"] == "trigger-newcomer@example.com"
    assert rec["target_type"] == "account"
    assert rec["target_id"] == str(newcomer)


async def test_other_auth_events_are_not_copied(owner_db, make_account):
    officer = await make_account(role="crewing_officer")

    await _gotrue_writes(owner_db, "token_refreshed", officer, "x@example.com")
    await _gotrue_writes(owner_db, "logout", officer, "x@example.com")
    await _gotrue_writes(owner_db, "user_recovery_requested", officer, "x@example.com")
    await _gotrue_writes(owner_db, "user_confirmation_requested", officer, "x@example.com")

    assert await _logins_of(owner_db, officer) == []


@pytest.mark.parametrize("action", ["login", "user_signedup"])
async def test_a_broken_entry_never_breaks_sign_in(owner_db, action):
    # A malformed actor id makes the copy fail; GoTrue's own insert must still succeed.
    actor = f"not-a-uuid-{action}"
    await _gotrue_writes(owner_db, action, actor, "odd@example.com", ip="not-an-ip")

    assert await owner_db.fetchval(
        "SELECT count(*) FROM auth.audit_log_entries WHERE payload->>'actor_id' = $1", actor
    ) >= 1
