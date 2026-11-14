"""`python -m app.scripts.make_admin <email>` bootstraps the first administrator."""

import json

import asyncpg
import pytest

from app.config import settings as app_settings
from app.scripts.make_admin import NoSuchAccount, make_admin


async def _run(email: str) -> str:
    conn = await asyncpg.connect(app_settings.database_url)
    try:
        return await make_admin(conn, email)
    finally:
        await conn.close()


async def test_make_admin_turns_a_pending_sign_up_into_an_active_administrator(owner_db, make_account):
    account = await make_account(status="pending", email="First.Admin@example.com")
    await _run("first.admin@example.com")  # e-mail match ignores case

    row = await owner_db.fetchrow("SELECT status, role FROM public.users WHERE id = $1", account)
    assert (row["status"], row["role"]) == ("active", "administrator")
    [rec] = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE target_type = 'account' AND target_id = $1", str(account)
    )
    assert rec["action"] == "account_approved"
    assert rec["actor_id"] is None
    assert rec["actor_role"] == "system"
    assert rec["reason"]
    assert json.loads(rec["after"]) == {"status": "active", "role": "administrator"}


async def test_make_admin_promotes_an_active_account(owner_db, make_account):
    account = await make_account(role="manager", email="m@example.com")
    await _run("m@example.com")
    row = await owner_db.fetchrow("SELECT status, role FROM public.users WHERE id = $1", account)
    assert (row["status"], row["role"]) == ("active", "administrator")


async def test_make_admin_reactivates_a_deactivated_account(owner_db, make_account):
    account = await make_account(status="deactivated", role="crewing_officer", email="d@example.com")
    await _run("d@example.com")
    row = await owner_db.fetchrow("SELECT status, role FROM public.users WHERE id = $1", account)
    assert (row["status"], row["role"]) == ("active", "administrator")


async def test_make_admin_on_an_administrator_changes_nothing(owner_db, make_account):
    account = await make_account(email="a@example.com")
    message = await _run("a@example.com")
    assert "already" in message
    assert await owner_db.fetchval(
        "SELECT count(*) FROM public.audit_log WHERE target_id = $1", str(account)
    ) == 0


async def test_make_admin_needs_a_signed_up_account(make_account):
    with pytest.raises(NoSuchAccount):
        await _run("nobody@example.com")
