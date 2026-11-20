"""Database guards that hold no matter what the API does (T5, T7, T9, ADR 0002)."""

from uuid import uuid4

import asyncpg
import pytest

from app.config import settings as app_settings


async def _app_conn() -> asyncpg.Connection:
    return await asyncpg.connect(app_settings.database_url)


async def test_app_runs_as_app_backend():
    conn = await _app_conn()
    try:
        assert await conn.fetchval("SELECT current_user") == "app_backend"
    finally:
        await conn.close()


async def test_sign_up_creates_a_pending_account_with_no_role(owner_db, make_account):
    user_id = await make_account(status="pending", email="new@example.com", full_name="Anna")
    row = await owner_db.fetchrow("SELECT * FROM public.users WHERE id = $1", user_id)
    assert row["status"] == "pending"
    assert row["role"] is None
    assert row["email"] == "new@example.com"
    assert row["full_name"] == "Anna"


async def test_sign_up_ignores_a_role_in_the_metadata(owner_db, make_account):
    user_id = uuid4()
    await owner_db.execute(
        """
        INSERT INTO auth.users (id, email, raw_user_meta_data)
        VALUES ($1, 'sneaky@example.com', '{"role": "administrator"}'::jsonb)
        """,
        user_id,
    )
    try:
        row = await owner_db.fetchrow("SELECT status, role FROM public.users WHERE id = $1", user_id)
        assert (row["status"], row["role"]) == ("pending", None)
    finally:
        await owner_db.execute("DELETE FROM public.users WHERE id = $1", user_id)
        await owner_db.execute("DELETE FROM auth.users WHERE id = $1", user_id)


async def test_role_is_required_once_active(owner_db, make_account):
    user_id = await make_account(status="pending")
    with pytest.raises(asyncpg.CheckViolationError):
        await owner_db.execute("UPDATE public.users SET status = 'active' WHERE id = $1", user_id)


async def test_a_pending_account_has_no_role(owner_db, make_account):
    user_id = await make_account(status="pending")
    with pytest.raises(asyncpg.CheckViolationError):
        await owner_db.execute("UPDATE public.users SET role = 'manager' WHERE id = $1", user_id)


async def test_settings_is_one_row_with_the_defaults(owner_db):
    rows = await owner_db.fetch("SELECT * FROM public.settings")
    assert len(rows) == 1
    row = rows[0]
    assert row["alert_steps"] == [90, 60, 30, 0]
    assert row["planning_horizon_days"] == 90
    assert row["max_file_size_mb"] == 4
    assert row["max_pdf_pages"] == 50
    assert row["time_zone"] == "UTC"
    assert row["daily_check_time"].strftime("%H:%M") == "07:00"
    assert row["version"] == 1


async def test_settings_refuses_a_second_row(owner_db):
    with pytest.raises(asyncpg.PostgresError):
        await owner_db.execute("INSERT INTO public.settings DEFAULT VALUES")
    with pytest.raises(asyncpg.CheckViolationError):
        await owner_db.execute("INSERT INTO public.settings (id) VALUES (false)")


@pytest.mark.parametrize(
    "column, value",
    [
        ("planning_horizon_days", 6),
        ("planning_horizon_days", 366),
        ("max_file_size_mb", 0),
        ("max_file_size_mb", 5),
        ("max_pdf_pages", 0),
        ("max_pdf_pages", 501),
        ("alert_steps", [90, 60]),  # 0 must be present
        ("alert_steps", [0, 30, 30]),  # distinct
        ("alert_steps", [0, 1, 2, 3, 4, 5, 6]),  # at most 6
        ("alert_steps", [0, -1]),
        ("alert_steps", []),
    ],
)
async def test_settings_ranges_are_checked(owner_db, column, value):
    async with owner_db.transaction():
        with pytest.raises(asyncpg.CheckViolationError):
            await owner_db.execute(f"UPDATE public.settings SET {column} = $1", value)


async def test_the_file_size_ceiling_is_4_mb(owner_db):
    # Vercel refuses request bodies over 4.5 MB (ADR 0003).
    await owner_db.execute("UPDATE public.settings SET max_file_size_mb = 4")
    assert await owner_db.fetchval("SELECT max_file_size_mb FROM public.settings") == 4


async def test_settings_daily_check_time_is_in_15_minute_steps(owner_db):
    from datetime import time

    with pytest.raises(asyncpg.CheckViolationError):
        await owner_db.execute("UPDATE public.settings SET daily_check_time = $1", time(7, 10))


async def test_app_backend_can_insert_and_read_the_audit_log():
    conn = await _app_conn()
    try:
        marker = str(uuid4())
        await conn.execute(
            "INSERT INTO public.audit_log (action, target_id) VALUES ('test_marker', $1)", marker
        )
        assert await conn.fetchval(
            "SELECT count(*) FROM public.audit_log WHERE target_id = $1", marker
        ) == 1
    finally:
        await conn.close()


async def test_app_backend_cannot_update_or_delete_the_audit_log():
    conn = await _app_conn()
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("UPDATE public.audit_log SET reason = 'x'")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("DELETE FROM public.audit_log")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("TRUNCATE public.audit_log")
    finally:
        await conn.close()


async def test_the_append_only_trigger_also_blocks_the_owner(owner_db):
    marker = str(uuid4())
    await owner_db.execute(
        "INSERT INTO public.audit_log (action, target_id) VALUES ('test_marker', $1)", marker
    )
    for statement in (
        "UPDATE public.audit_log SET reason = 'tampered' WHERE target_id = $1",
        "DELETE FROM public.audit_log WHERE target_id = $1",
    ):
        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="append-only"):
            await owner_db.execute(statement, marker)
    with pytest.raises(asyncpg.InsufficientPrivilegeError, match="append-only"):
        await owner_db.execute("TRUNCATE public.audit_log")
    assert await owner_db.fetchval(
        "SELECT reason FROM public.audit_log WHERE target_id = $1", marker
    ) is None


async def test_app_backend_cannot_delete_accounts_or_settings(make_account):
    user_id = await make_account()
    conn = await _app_conn()
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("DELETE FROM public.users WHERE id = $1", user_id)
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("DELETE FROM public.settings")
    finally:
        await conn.close()


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize(
    "table",
    [
        "users",
        "settings",
        "audit_log",
        "vessel",
        "position",
        "document_type",
        "position_requirement",
        "requirement_exception",
        "seafarer",
        "assignment",
        "responsible_officer",
        "document",
        "version",
        "review",
        "verification",
        "alert",
        "alert_delivery",
        "daily_check_run",
        "sign_in_challenge",
        "verified_session",
        "login_block",
    ],
)
async def test_every_table_denies_anon_and_authenticated(owner_db, make_account, role, table):
    await make_account()
    async with owner_db.transaction():
        await owner_db.execute(f"SET LOCAL ROLE {role}")
        try:
            rows = await owner_db.fetch(f"SELECT * FROM public.{table}")
        except asyncpg.InsufficientPrivilegeError:
            rows = []
        assert rows == []


async def test_every_public_table_has_forced_rls(owner_db):
    rows = await owner_db.fetch(
        """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relkind = 'r'
        """
    )
    assert rows, "no tables found"
    assert [r["relname"] for r in rows if not (r["relrowsecurity"] and r["relforcerowsecurity"])] == []


async def test_app_backend_role_is_restricted(owner_db):
    role = await owner_db.fetchrow("SELECT * FROM pg_roles WHERE rolname = 'app_backend'")
    assert role["rolcanlogin"] is True
    assert role["rolinherit"] is False
    assert role["rolbypassrls"] is False
    assert role["rolsuper"] is False
    owned = await owner_db.fetchval(
        "SELECT count(*) FROM pg_class WHERE relowner = 'app_backend'::regrole"
    )
    assert owned == 0


async def test_the_database_calls_the_daily_check_every_5_minutes(owner_db):
    job = await owner_db.fetchrow(
        "SELECT schedule, active FROM cron.job WHERE jobname = 'daily-check'"
    )
    assert job is not None
    assert (job["schedule"], job["active"]) == ("*/5 * * * *", True)


async def test_expired_sign_in_challenges_and_their_tokens_are_deleted_every_5_minutes(owner_db):
    # SR-03, ADR 0007: the aal1 token a challenge keeps does not outlive it.
    job = await owner_db.fetchrow(
        "SELECT schedule, command, active FROM cron.job WHERE jobname = 'sign-in-challenge-cleanup'"
    )
    assert job is not None
    assert (job["schedule"], job["active"]) == ("*/5 * * * *", True)
    assert "DELETE FROM public.sign_in_challenge WHERE expires_at < now()" in job["command"]


# --- SR-14: the Audit Log is append-only for the application -----------------------


async def test_app_backend_holds_only_insert_and_select_on_the_audit_log(owner_db):
    privileges = await owner_db.fetch(
        """
        SELECT privilege_type FROM information_schema.role_table_grants
         WHERE grantee = 'app_backend' AND table_schema = 'public' AND table_name = 'audit_log'
        """
    )
    assert {r["privilege_type"] for r in privileges} == {"INSERT", "SELECT"}


async def test_the_audit_log_owner_is_a_separate_role(owner_db):
    owner = await owner_db.fetchval(
        "SELECT tableowner FROM pg_tables WHERE schemaname = 'public' AND tablename = 'audit_log'"
    )
    assert owner != "app_backend"
    assert await owner_db.fetchval("SELECT pg_has_role('app_backend', $1, 'MEMBER')", owner) is False


async def test_app_backend_cannot_run_the_audit_retention():
    conn = await _app_conn()
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("SELECT public.retention_remove_old_audit_records()")
    finally:
        await conn.close()


async def test_the_owner_removes_old_audit_records_nightly(owner_db):
    job = await owner_db.fetchrow(
        "SELECT schedule, command, username, active FROM cron.job WHERE jobname = 'audit-retention'"
    )
    assert job is not None
    assert (job["schedule"], job["active"]) == ("17 3 * * *", True)
    assert "public.retention_remove_old_audit_records()" in job["command"]
    owner = await owner_db.fetchval(
        "SELECT pg_get_userbyid(proowner) FROM pg_proc "
        "WHERE oid = 'public.retention_remove_old_audit_records()'::regprocedure"
    )
    assert job["username"] == owner != "app_backend"
