"""Sign-in through the backend and logout (R1, T7, ADR 0002).

`POST /api/auth/login` proxies to Supabase Auth and records *login failed*;
`POST /api/auth/logout` records *logout*. Most tests stand in for Supabase
Auth (it is an outside service); the last one runs against a real local Auth
and skips when SUPABASE_URL is unreachable.
"""

from uuid import UUID, uuid4

import httpx
import pytest

from app.config import settings as app_settings
from app.supabase_auth import AuthUnavailable, SignInRefused, get_supabase_auth
from tests.conftest import auth_header

SESSION = {
    "access_token": "access",
    "refresh_token": "refresh",
    "token_type": "bearer",
    "expires_in": 3600,
    "expires_at": 1_900_000_000,
    "user": {"id": str(uuid4())},
}


class FakeAuth:
    """Supabase Auth with one known password per e-mail."""

    def __init__(self, passwords: dict[str, str] | None = None, down: bool = False):
        self.passwords = passwords or {}
        self.down = down
        self.calls: list[tuple[str, str | None]] = []

    async def sign_in_with_password(self, email: str, password: str, client_ip: str | None):
        self.calls.append((email, client_ip))
        if self.down:
            raise AuthUnavailable()
        if self.passwords.get(email) != password:
            raise SignInRefused(400, "invalid_credentials", "Invalid login credentials")
        return SESSION


@pytest.fixture
def fake_auth(app):
    fake = FakeAuth()
    app.dependency_overrides[get_supabase_auth] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_supabase_auth, None)


async def _records(owner_db, action: str, email: str) -> list[dict]:
    rows = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE action = $1 AND actor_email = $2 ORDER BY id",
        action,
        email,
    )
    return [dict(r) for r in rows]


def _unique_email() -> str:
    return f"{uuid4().hex[:12]}@example.com"


# --- login failed ---------------------------------------------------------------


async def test_a_failed_login_on_an_unknown_email_is_recorded_with_no_actor(
    client, owner_db, fake_auth
):
    email = _unique_email()

    res = await client.post("/api/auth/login", json={"email": email, "password": "guess"})

    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "invalid_credentials"
    [rec] = await _records(owner_db, "login_failed", email)
    assert rec["actor_id"] is None
    assert rec["actor_role"] is None
    assert rec["outcome"] == "refused"
    assert rec["reason"] == "invalid_credentials"
    assert str(rec["ip"]) == "127.0.0.1"
    assert rec["request_id"] == res.headers["x-request-id"]


async def test_a_wrong_password_is_recorded_against_the_account(
    client, owner_db, make_account, fake_auth
):
    email = _unique_email()
    officer = await make_account(role="crewing_officer", email=email)
    fake_auth.passwords[email] = "right"

    # The e-mail is matched the way it was typed, whatever its case.
    typed = email.upper()
    res = await client.post("/api/auth/login", json={"email": typed, "password": "wrong"})

    assert res.status_code == 400
    [rec] = await _records(owner_db, "login_failed", typed)
    assert rec["actor_id"] == officer
    assert rec["actor_role"] == "crewing_officer"
    assert rec["target_type"] == "account"
    assert rec["target_id"] == str(officer)


async def test_auth_being_down_is_a_recorded_failure(client, owner_db, fake_auth):
    fake_auth.down = True
    email = _unique_email()

    res = await client.post("/api/auth/login", json={"email": email, "password": "pw"})

    assert res.status_code == 503
    assert res.json()["detail"]["code"] == "auth_unavailable"
    [rec] = await _records(owner_db, "login_failed", email)
    assert rec["reason"] == "auth_unavailable"


# --- login succeeded ------------------------------------------------------------


async def test_a_right_password_returns_the_session(client, owner_db, make_account, fake_auth):
    email = _unique_email()
    await make_account(role="crewing_officer", email=email)
    fake_auth.passwords[email] = "right"

    res = await client.post("/api/auth/login", json={"email": email, "password": "right"})

    assert res.status_code == 200
    body = res.json()
    assert body["access_token"] == "access"
    assert body["refresh_token"] == "refresh"
    assert fake_auth.calls == [(email, "127.0.0.1")]
    # *Login succeeded* comes from Supabase's audit table, not from here.
    assert await _records(owner_db, "login_failed", email) == []


# --- logout ---------------------------------------------------------------------


async def test_logout_is_recorded(client, owner_db, make_account):
    email = _unique_email()
    officer = await make_account(role="crewing_officer", email=email)

    res = await client.post("/api/auth/logout", headers=auth_header(officer))

    assert res.status_code == 204
    [rec] = await _records(owner_db, "logout", email)
    assert rec["actor_id"] == officer
    assert rec["actor_role"] == "crewing_officer"
    assert rec["outcome"] == "succeeded"


async def test_a_pending_account_can_log_out(client, owner_db, make_account):
    email = _unique_email()
    pending = await make_account(status="pending", email=email)

    res = await client.post("/api/auth/logout", headers=auth_header(pending))

    assert res.status_code == 204
    assert len(await _records(owner_db, "logout", email)) == 1
    assert await _records(owner_db, "access_refused", email) == []


async def test_logout_needs_a_token(client):
    assert (await client.post("/api/auth/logout")).status_code == 401


# --- against a real local Supabase Auth -----------------------------------------


def _auth_reachable() -> bool:
    try:
        httpx.get(f"{app_settings.supabase_url.rstrip('/')}/auth/v1/health", timeout=2)
        return True
    except httpx.HTTPError:
        return False


needs_auth = pytest.mark.skipif(
    not _auth_reachable(), reason="Supabase Auth (GoTrue) is not reachable at SUPABASE_URL"
)


@needs_auth
async def test_real_auth_wrong_and_right_password_both_reach_the_audit_log(client, owner_db):
    base = app_settings.supabase_url.rstrip("/")
    key = app_settings.supabase_service_role_key
    email = _unique_email()
    admin_headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    async with httpx.AsyncClient() as http:
        created = await http.post(
            f"{base}/auth/v1/admin/users",
            headers=admin_headers,
            json={"email": email, "password": "right-password-1", "email_confirm": True},
        )
        created.raise_for_status()
        user_id = UUID(created.json()["id"])
    try:
        wrong = await client.post(
            "/api/auth/login", json={"email": email, "password": "wrong-password"}
        )
        right = await client.post(
            "/api/auth/login", json={"email": email, "password": "right-password-1"}
        )

        assert wrong.status_code == 400
        assert right.status_code == 200
        assert right.json()["access_token"]
        assert len(await _records(owner_db, "login_failed", email)) == 1
        assert await owner_db.fetchval(
            "SELECT count(*) FROM public.audit_log"
            " WHERE action = 'login_succeeded' AND actor_id = $1",
            user_id,
        ) == 1
    finally:
        # The Account row blocks deleting its auth user, so it goes first.
        await owner_db.execute("DELETE FROM public.users WHERE id = $1", user_id)
        async with httpx.AsyncClient() as http:
            await http.delete(f"{base}/auth/v1/admin/users/{user_id}", headers=admin_headers)
