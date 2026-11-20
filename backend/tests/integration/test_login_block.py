"""Block after failed logins (SR-18).

Criterion (Table 18): after 10 failed logins for one account or address
within 15 minutes, further attempts return 429 for 15 minutes and are logged.
Counted: *login failed* with reason `invalid_credentials` (wrong password,
unknown e-mail) or `totp_invalid` (wrong authenticator code), per lower-case
e-mail and per address. A blocked attempt does not reach Supabase Auth, is
recorded as `login_blocked`, and does not extend the block.
"""

from contextlib import asynccontextmanager
from datetime import timedelta

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from tests.integration.test_sign_in_api import (  # noqa: F401  (fixtures)
    PASSWORD,
    TOTP,
    _records,
    _unique_email,
    _unique_ip,
    client,
    fake_auth,
    newcomer,
    officer,
)

WRONG = "not-the-password-1"
LIMIT = 10


@asynccontextmanager
async def _from(app, ip: str | None = None):
    """A client from its own (or the given) address."""
    ip = ip or _unique_ip()
    transport = ASGITransport(app=app, client=(ip, 123))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c.ip = ip
        yield c


async def _login(c, email: str, password: str):
    return await c.post("/api/auth/login", json={"email": email, "password": password})


async def _block(owner_db, kind: str, key: str):
    return await owner_db.fetchrow(
        "SELECT * FROM public.login_block WHERE kind = $1 AND key = $2", kind, key
    )


def _assert_blocked(res) -> None:
    assert res.status_code == 429, res.text
    assert res.json()["detail"]["code"] == "login_blocked"
    assert 0 < int(res.headers["retry-after"]) <= 15 * 60


async def test_ten_wrong_passwords_for_one_email_block_it_even_with_the_right_password(
    app, owner_db, fake_auth, officer
):
    email, user_id = officer
    # From ten different addresses: the e-mail alone is counted.
    for _ in range(LIMIT):
        async with _from(app) as c:
            assert (await _login(c, email.upper(), WRONG)).status_code == 400
    grants = len(fake_auth.called("password_grant"))

    async with _from(app) as c:
        res = await _login(c, email, PASSWORD)

    _assert_blocked(res)
    assert len(fake_auth.called("password_grant")) == grants  # Supabase not asked
    [rec] = await _records(owner_db, "login_failed", email)
    assert rec["reason"] == "login_blocked"
    assert rec["outcome"] == "refused"
    assert rec["actor_id"] == user_id
    assert str(rec["ip"]) == c.ip
    block = await _block(owner_db, "email", email.lower())
    assert block is not None


async def test_a_known_and_an_unknown_email_get_the_same_answer_when_blocked(
    app, fake_auth, officer
):
    known, _ = officer
    unknown = _unique_email()
    answers = []
    for email in (known, unknown):
        for _ in range(LIMIT):
            async with _from(app) as c:
                await _login(c, email, WRONG)
        async with _from(app) as c:
            answers.append(await _login(c, email, PASSWORD))

    for res in answers:
        _assert_blocked(res)
    assert answers[0].json() == answers[1].json()


async def test_ten_failures_from_one_address_block_it_for_every_email(
    app, owner_db, fake_auth, officer
):
    email, _ = officer
    async with _from(app) as c:
        for _ in range(LIMIT):
            assert (await _login(c, _unique_email(), WRONG)).status_code == 400

        res = await _login(c, email, PASSWORD)

        _assert_blocked(res)
        assert await _block(owner_db, "ip", c.ip) is not None
        assert fake_auth.called("password_grant")[-1][1] != email
    # The e-mail itself is not blocked: from another address it gets in.
    async with _from(app) as other:
        assert (await _login(other, email, PASSWORD)).status_code == 200


async def test_wrong_authenticator_codes_count(app, owner_db, fake_auth, officer):
    email, _ = officer
    async with _from(app) as c:
        # Five wrong codes end a challenge, so two challenges.
        for _ in range(2):
            challenge = (await _login(c, email, PASSWORD)).json()["challenge"]
            for _ in range(5):
                res = await c.post(
                    "/api/auth/verify",
                    json={"email": email, "challenge": challenge, "code": "000000"},
                )
                assert res.json()["detail"]["code"] == "totp_invalid"

    async with _from(app) as c:
        _assert_blocked(await _login(c, email, PASSWORD))


async def test_a_blocked_email_cannot_finish_the_totp_step(app, owner_db, fake_auth, officer):
    email, _ = officer
    async with _from(app) as c:
        challenge = (await _login(c, email, PASSWORD)).json()["challenge"]
    for _ in range(LIMIT):
        async with _from(app) as c:
            await _login(c, email, WRONG)
    verifies = len(fake_auth.called("verify_totp"))

    async with _from(app) as c:
        res = await c.post(
            "/api/auth/verify", json={"email": email, "challenge": challenge, "code": TOTP}
        )

    _assert_blocked(res)
    assert len(fake_auth.called("verify_totp")) == verifies
    assert fake_auth.called("challenge") == []


async def test_a_blocked_attempt_is_recorded_and_does_not_extend_the_block(
    app, owner_db, fake_auth, officer
):
    email, _ = officer
    for _ in range(LIMIT):
        async with _from(app) as c:
            await _login(c, email, WRONG)
    # Pretend the block began a while ago.
    await owner_db.execute(
        "UPDATE public.login_block SET blocked_until = blocked_until - interval '10 minutes'"
        " WHERE kind = 'email' AND key = $1",
        email.lower(),
    )
    before = (await _block(owner_db, "email", email.lower()))["blocked_until"]

    async with _from(app) as c:
        for _ in range(3):
            res = await _login(c, email, WRONG)
            _assert_blocked(res)
            assert int(res.headers["retry-after"]) <= 5 * 60

    assert (await _block(owner_db, "email", email.lower()))["blocked_until"] == before
    blocked = [r for r in await _records(owner_db, "login_failed", email)
               if r["reason"] == "login_blocked"]
    assert len(blocked) == 3


async def test_once_the_block_has_passed_sign_in_works(app, owner_db, fake_auth, officer):
    email, _ = officer
    for _ in range(LIMIT):
        async with _from(app) as c:
            await _login(c, email, WRONG)
    async with _from(app) as c:
        _assert_blocked(await _login(c, email, PASSWORD))

    await owner_db.execute(
        "UPDATE public.login_block SET blocked_until = now() - interval '1 second'"
        " WHERE kind = 'email' AND key = $1",
        email.lower(),
    )

    async with _from(app) as c:
        res = await _login(c, email, PASSWORD)
        assert res.status_code == 200
        session = await c.post(
            "/api/auth/verify",
            json={"email": email, "challenge": res.json()["challenge"], "code": TOTP},
        )
    assert session.status_code == 200


async def test_nine_failures_do_not_block(app, fake_auth, officer):
    email, _ = officer
    async with _from(app) as c:
        for _ in range(LIMIT - 1):
            await _login(c, email, WRONG)
        assert (await _login(c, email, PASSWORD)).status_code == 200


async def test_failures_older_than_15_minutes_do_not_count(app, owner_db, fake_auth, officer):
    email, _ = officer
    async with _from(app) as c:
        # Nine failures 16 minutes ago (the Audit Log cannot be back-dated,
        # so they are written as they would have been then).
        await owner_db.executemany(
            """
            INSERT INTO public.audit_log
                (occurred_at, actor_email, action, outcome, reason, ip)
            VALUES (now() - $1::interval, $2, 'login_failed', 'refused',
                    'invalid_credentials', $3::inet)
            """,
            [(timedelta(minutes=16), email, c.ip)] * (LIMIT - 1),
        )
        await _login(c, email, WRONG)
        assert (await _login(c, email, PASSWORD)).status_code == 200


async def test_sign_in_being_unavailable_is_not_counted(app, fake_auth, officer):
    email, _ = officer
    fake_auth.down = True
    async with _from(app) as c:
        for _ in range(LIMIT):
            assert (await _login(c, email, WRONG)).status_code == 503
        fake_auth.down = False
        assert (await _login(c, email, PASSWORD)).status_code == 200


async def test_login_block_is_closed_to_anon_and_authenticated(owner_db):
    rls = await owner_db.fetchrow(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class"
        " WHERE oid = 'public.login_block'::regclass"
    )
    assert (rls["relrowsecurity"], rls["relforcerowsecurity"]) == (True, True)
    for role in ("anon", "authenticated"):
        assert not await owner_db.fetchval(
            "SELECT has_table_privilege($1, 'public.login_block', 'SELECT')", role
        )
    for privilege in ("SELECT", "INSERT"):
        assert await owner_db.fetchval(
            "SELECT has_table_privilege('app_backend', 'public.login_block', $1)", privilege
        )
    assert await owner_db.fetchval(
        "SELECT has_column_privilege('app_backend', 'public.login_block', 'blocked_until',"
        " 'UPDATE')"
    )
    for privilege in ("UPDATE", "DELETE"):
        assert not await owner_db.fetchval(
            "SELECT has_table_privilege('app_backend', 'public.login_block', $1)", privilege
        )


async def test_failed_logins_are_counted_through_an_index(owner_db):
    defs = await owner_db.fetch(
        "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'audit_log'"
    )
    assert any("(action, occurred_at)" in d["indexdef"] for d in defs)


async def test_a_block_is_only_for_an_email_or_an_address(owner_db):
    with pytest.raises(asyncpg.CheckViolationError):
        await owner_db.execute(
            "INSERT INTO public.login_block (kind, key, blocked_until)"
            " VALUES ('account', 'x', now())"
        )


async def test_ended_blocks_are_removed_by_an_owner_job(owner_db):
    job = await owner_db.fetchrow(
        "SELECT command, active FROM cron.job WHERE jobname = 'login-block-cleanup'"
    )
    assert job is not None and job["active"]
    assert "DELETE FROM public.login_block" in job["command"]
