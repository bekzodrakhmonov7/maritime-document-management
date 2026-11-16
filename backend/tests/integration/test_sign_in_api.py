"""The sign-in proxy (e-mailed Sign-in Codes) and logout (R1, T7, ADR 0002, ADR 0004).

`POST /api/auth/register` and `POST /api/auth/code` ask Supabase Auth to
e-mail a code, `POST /api/auth/verify` checks it, and failed attempts are
recorded as *Login failed*; `POST /api/auth/logout` records *logout*. Most
tests stand in for Supabase Auth (it is an outside service); the last ones run
against a real local Auth and Mailpit and skip when they are unreachable.
"""

import os
import re
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
    """Supabase Auth's e-mail code flow, with known Accounts and sent codes."""

    def __init__(self) -> None:
        self.accounts: set[str] = set()
        self.codes: dict[str, str] = {}
        self.expired: set[str] = set()
        self.rate_limited = False
        self.down = False
        self.sent: list[dict] = []
        self.verified: list[tuple[str, str, str | None]] = []

    async def send_code(
        self, email: str, create: bool, full_name: str | None, client_ip: str | None
    ) -> None:
        self.sent.append(
            {"email": email, "create": create, "full_name": full_name, "client_ip": client_ip}
        )
        if self.down:
            raise AuthUnavailable()
        if self.rate_limited:
            raise SignInRefused(
                429, "over_email_send_rate_limit", "For security purposes, wait 60 seconds."
            )
        if not create and email not in self.accounts:
            raise SignInRefused(422, "otp_disabled", "Signups not allowed for otp")
        self.accounts.add(email)
        self.codes[email] = "123456"

    async def verify_code(self, email: str, code: str, client_ip: str | None):
        self.verified.append((email, code, client_ip))
        if self.down:
            raise AuthUnavailable()
        if email in self.expired:
            raise SignInRefused(403, "otp_expired", "Token has expired or is invalid")
        if self.codes.get(email) != code:
            raise SignInRefused(403, "otp_invalid", "Token is invalid")
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


# --- asking for a code ----------------------------------------------------------


async def test_code_answers_an_unknown_email_exactly_as_a_known_one(
    client, owner_db, make_account, fake_auth
):
    known = _unique_email()
    await make_account(role="crewing_officer", email=known)
    fake_auth.accounts.add(known)
    unknown = _unique_email()

    known_res = await client.post("/api/auth/code", json={"email": known})
    unknown_res = await client.post("/api/auth/code", json={"email": unknown})

    assert known_res.status_code == unknown_res.status_code == 200
    assert known_res.json() == unknown_res.json()
    assert await _records(owner_db, "login_failed", known) == []
    [rec] = await _records(owner_db, "login_failed", unknown)
    assert rec["actor_id"] is None
    assert rec["actor_role"] is None
    assert rec["target_id"] is None
    assert rec["outcome"] == "refused"
    assert rec["reason"] == "unknown_email"
    assert str(rec["ip"]) == "127.0.0.1"
    assert rec["request_id"] == unknown_res.headers["x-request-id"]


async def test_a_rate_limited_code_request_gets_the_same_answer(client, fake_auth):
    email = _unique_email()
    fake_auth.accounts.add(email)
    sent = await client.post("/api/auth/code", json={"email": email})
    fake_auth.rate_limited = True

    limited = await client.post("/api/auth/code", json={"email": email})

    assert limited.status_code == 200
    assert limited.json() == sent.json()


async def test_code_never_creates_an_account(client, fake_auth):
    email = _unique_email()

    await client.post("/api/auth/code", json={"email": f"  {email} "})

    assert fake_auth.sent == [
        {"email": email, "create": False, "full_name": None, "client_ip": "127.0.0.1"}
    ]


# --- registering ----------------------------------------------------------------


async def test_register_creates_the_account_with_its_full_name(client, fake_auth):
    email = _unique_email()

    res = await client.post(
        "/api/auth/register", json={"email": email, "full_name": "  Ana Kovač "}
    )

    assert res.status_code == 200
    assert fake_auth.sent == [
        {"email": email, "create": True, "full_name": "Ana Kovač", "client_ip": "127.0.0.1"}
    ]


async def test_register_answers_the_same_for_an_existing_account_and_a_rate_limit(
    client, fake_auth
):
    new = await client.post(
        "/api/auth/register", json={"email": _unique_email(), "full_name": "New Person"}
    )
    existing = _unique_email()
    fake_auth.accounts.add(existing)
    again = await client.post(
        "/api/auth/register", json={"email": existing, "full_name": "Old Person"}
    )
    fake_auth.rate_limited = True
    limited = await client.post(
        "/api/auth/register", json={"email": _unique_email(), "full_name": "Fast Person"}
    )

    assert new.status_code == again.status_code == limited.status_code == 200
    assert new.json() == again.json() == limited.json()


async def test_register_needs_a_full_name(client, fake_auth):
    res = await client.post("/api/auth/register", json={"email": _unique_email(), "full_name": " "})

    assert res.status_code == 422
    assert fake_auth.sent == []


# --- checking the code ----------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expired", "expected"),
    [("000000", False, "otp_invalid"), ("123456", True, "otp_expired")],
)
async def test_a_wrong_or_expired_code_is_recorded_against_the_account(
    client, owner_db, make_account, fake_auth, code, expired, expected
):
    email = _unique_email()
    officer = await make_account(role="crewing_officer", email=email)

    # The e-mail is matched the way it was typed, whatever its case.
    typed = email.upper()
    fake_auth.codes[typed] = "123456"
    if expired:
        fake_auth.expired.add(typed)
    res = await client.post("/api/auth/verify", json={"email": typed, "code": code})

    assert res.status_code == 403
    assert res.json()["detail"]["code"] == expected
    [rec] = await _records(owner_db, "login_failed", typed)
    assert rec["actor_id"] == officer
    assert rec["actor_role"] == "crewing_officer"
    assert rec["target_type"] == "account"
    assert rec["target_id"] == str(officer)
    assert rec["reason"] == expected
    assert rec["outcome"] == "refused"


async def test_a_code_for_an_unknown_email_is_recorded_with_no_actor(
    client, owner_db, fake_auth
):
    email = _unique_email()

    res = await client.post("/api/auth/verify", json={"email": email, "code": "123456"})

    assert res.status_code == 403
    [rec] = await _records(owner_db, "login_failed", email)
    assert rec["actor_id"] is None
    assert rec["reason"] == "otp_invalid"


async def test_a_right_code_returns_the_session(client, owner_db, make_account, fake_auth):
    email = _unique_email()
    await make_account(role="crewing_officer", email=email)
    fake_auth.codes[email] = "123456"

    res = await client.post("/api/auth/verify", json={"email": email, "code": " 123456 "})

    assert res.status_code == 200
    body = res.json()
    assert body["access_token"] == "access"
    assert body["refresh_token"] == "refresh"
    assert fake_auth.verified == [(email, "123456", "127.0.0.1")]
    # *Login succeeded* comes from Supabase's audit table, not from here.
    assert await _records(owner_db, "login_failed", email) == []


@pytest.mark.parametrize("code", ["", "12345", "1234567", "12a456"])
async def test_a_code_is_six_digits(client, fake_auth, code):
    res = await client.post("/api/auth/verify", json={"email": _unique_email(), "code": code})

    assert res.status_code == 422
    assert fake_auth.verified == []


# --- Auth down ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "extra"),
    [
        ("/api/auth/code", {}),
        ("/api/auth/register", {"full_name": "Ana Kovač"}),
        ("/api/auth/verify", {"code": "123456"}),
    ],
)
async def test_auth_being_down_is_a_recorded_failure(client, owner_db, fake_auth, path, extra):
    fake_auth.down = True
    email = _unique_email()

    res = await client.post(path, json={"email": email, **extra})

    assert res.status_code == 503
    assert res.json()["detail"]["code"] == "auth_unavailable"
    [rec] = await _records(owner_db, "login_failed", email)
    assert rec["reason"] == "auth_unavailable"


# --- no password sign-in --------------------------------------------------------


async def test_the_password_login_endpoint_is_gone(client, fake_auth):
    res = await client.post(
        "/api/auth/login", json={"email": _unique_email(), "password": "anything"}
    )

    assert res.status_code in (404, 405)


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


# --- against a real local Supabase Auth and Mailpit -----------------------------

MAILPIT_URL = os.environ.get("MAILPIT_URL", "http://127.0.0.1:54324").rstrip("/")


def _reachable(url: str) -> bool:
    try:
        httpx.get(url, timeout=2)
        return True
    except httpx.HTTPError:
        return False


_AUTH_HEALTH = f"{app_settings.supabase_url.rstrip('/')}/auth/v1/health"

needs_auth = pytest.mark.skipif(
    not _reachable(_AUTH_HEALTH),
    reason="Supabase Auth (GoTrue) is not reachable at SUPABASE_URL",
)
needs_mailpit = pytest.mark.skipif(
    not _reachable(f"{MAILPIT_URL}/api/v1/info"),
    reason=f"Mailpit is not reachable at {MAILPIT_URL}",
)


async def _code_from_mailpit(email: str) -> str:
    async with httpx.AsyncClient(base_url=MAILPIT_URL) as http:
        found = await http.get("/api/v1/search", params={"query": f'to:"{email}"'})
        found.raise_for_status()
        [newest, *_] = found.json()["messages"]
        message = await http.get(f"/api/v1/message/{newest['ID']}")
        message.raise_for_status()
    body = message.json()
    match = re.search(r"\b(\d{6})\b", body.get("Text") or body.get("HTML") or "")
    assert match, "no 6-digit code in the e-mail"
    return match.group(1)


@needs_auth
async def test_real_auth_refuses_a_password_grant(owner_db):
    base = app_settings.supabase_url.rstrip("/")
    key = app_settings.supabase_service_role_key
    admin_headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    email = _unique_email()
    async with httpx.AsyncClient() as http:
        created = await http.post(
            f"{base}/auth/v1/admin/users",
            headers=admin_headers,
            json={"email": email, "password": "a-password-1", "email_confirm": True},
        )
        created.raise_for_status()
        user_id = UUID(created.json()["id"])
        try:
            grant = await http.post(
                f"{base}/auth/v1/token",
                params={"grant_type": "password"},
                headers={"apikey": app_settings.supabase_anon_key or key},
                json={"email": email, "password": "a-password-1"},
            )
            assert grant.status_code == 400
            assert grant.json().get("error_code") in ("invalid_credentials", None)
        finally:
            # The Account row blocks deleting its auth user, so it goes first.
            await owner_db.execute("DELETE FROM public.users WHERE id = $1", user_id)
            await http.delete(f"{base}/auth/v1/admin/users/{user_id}", headers=admin_headers)


@needs_auth
@needs_mailpit
async def test_real_auth_a_code_from_mailpit_signs_in(client, owner_db):
    base = app_settings.supabase_url.rstrip("/")
    key = app_settings.supabase_service_role_key
    admin_headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    email = _unique_email()
    registered = await client.post(
        "/api/auth/register", json={"email": email, "full_name": "Real Auth Test"}
    )
    assert registered.status_code == 200
    user_id = await owner_db.fetchval(
        "SELECT id FROM public.users WHERE lower(email) = lower($1)", email
    )
    try:
        code = await _code_from_mailpit(email)
        wrong_code = "000000" if code != "000000" else "111111"

        wrong = await client.post("/api/auth/verify", json={"email": email, "code": wrong_code})
        right = await client.post("/api/auth/verify", json={"email": email, "code": code})

        assert wrong.status_code >= 400
        assert right.status_code == 200, right.text
        assert right.json()["access_token"]
        assert len(await _records(owner_db, "login_failed", email)) == 1
        assert await owner_db.fetchval(
            "SELECT count(*) FROM public.audit_log"
            " WHERE action = 'login_succeeded' AND actor_id = $1",
            user_id,
        ) == 1
    finally:
        if user_id:
            await owner_db.execute("DELETE FROM public.users WHERE id = $1", user_id)
            async with httpx.AsyncClient() as http:
                await http.delete(f"{base}/auth/v1/admin/users/{user_id}", headers=admin_headers)
