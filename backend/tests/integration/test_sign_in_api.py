"""The sign-in proxy: a password, then an e-mailed Sign-in Code (R1, T7,
ADR 0002, ADR 0005).

`POST /api/auth/login` and `/register` do the first step and answer with a
Sign-in Challenge, `/code` sends a new code, `/verify` checks the code against
the challenge and returns the session, and only sessions that passed both
steps get into the API. `/password/forgot` and `/password/reset` replace a
forgotten password. Most tests stand in for Supabase Auth (an outside
service); the last ones run against a real local Auth and Mailpit and skip
when they are unreachable.
"""

import os
import re
from uuid import UUID, uuid4

import httpx
import pytest
from app.config import settings as app_settings
from app.supabase_auth import AuthUnavailable, SignInRefused, get_supabase_auth

from tests.conftest import auth_header, make_token

CODE = "123456"
PASSWORD = "correct-horse-1"


class FakeAuth:
    """Supabase Auth with e-mail confirmation on: Accounts with passwords,
    e-mailed codes and the sessions they open."""

    def __init__(self, create_account) -> None:
        # Makes the auth.users row (and so the Account) that GoTrue would.
        self.create_account = create_account
        # e-mail -> {"id", "password", "confirmed"}
        self.accounts: dict[str, dict] = {}
        self.codes: dict[str, str] = {}
        self.reset_codes: dict[str, str] = {}
        self.expired: set[str] = set()
        self.autoconfirm = False
        self.send_rate_limited = False
        self.down = False
        self.calls: list[tuple] = []
        self.signed_out: list[tuple[str, str]] = []
        self.passwords_set: list[tuple[UUID, str]] = []

    def add(self, email: str, user_id: UUID, password: str = PASSWORD, confirmed: bool = True):
        self.accounts[email.lower()] = {"id": user_id, "password": password, "confirmed": confirmed}

    def _session(self, email: str) -> dict:
        user_id = self.accounts[email.lower()]["id"]
        return {
            "access_token": make_token(user_id, email, session_id=uuid4()),
            "refresh_token": "refresh",
            "token_type": "bearer",
            "expires_in": 3600,
            "user": {"id": str(user_id), "email": email.lower()},
        }

    def _check(self) -> None:
        if self.down:
            raise AuthUnavailable()

    def _mail(self, email: str) -> None:
        if self.send_rate_limited:
            raise SignInRefused(429, "over_email_send_rate_limit", "Wait 60 seconds.")
        self.codes[email.lower()] = CODE

    async def sign_up(self, email, password, full_name, client_ip):
        self.calls.append(("sign_up", email, password, full_name, client_ip))
        self._check()
        if email.lower() in self.accounts:
            # With confirmations on, an existing e-mail gets a made-up user.
            return {"id": str(uuid4()), "email": email, "identities": []}
        user_id = await self.create_account(email, full_name)
        self.add(email, user_id, password, confirmed=self.autoconfirm)
        if self.autoconfirm:
            return self._session(email)
        self._mail(email)
        return {"id": str(user_id), "email": email, "identities": [{"provider": "email"}]}

    async def password_grant(self, email, password, client_ip):
        self.calls.append(("password_grant", email, client_ip))
        self._check()
        account = self.accounts.get(email.lower())
        if account is None or account["password"] != password:
            raise SignInRefused(400, "invalid_credentials", "Invalid login credentials")
        if not account["confirmed"]:
            raise SignInRefused(400, "email_not_confirmed", "Email not confirmed")
        return self._session(email)

    async def send_code(self, email, client_ip):
        self.calls.append(("send_code", email))
        self._check()
        self._mail(email)

    async def resend_confirmation(self, email, client_ip):
        self.calls.append(("resend_confirmation", email))
        self._check()
        self._mail(email)

    async def verify_code(self, email, code, client_ip, type="email"):
        self.calls.append(("verify_code", email, code, type))
        self._check()
        codes = self.reset_codes if type == "recovery" else self.codes
        if email.lower() in self.expired:
            raise SignInRefused(403, "otp_expired", "Token has expired or is invalid")
        if codes.get(email.lower()) != code:
            raise SignInRefused(403, "otp_invalid", "Token is invalid")
        del codes[email.lower()]
        self.accounts[email.lower()]["confirmed"] = True
        return self._session(email)

    async def send_password_reset(self, email, client_ip):
        self.calls.append(("send_password_reset", email))
        self._check()
        if email.lower() in self.accounts:
            self.reset_codes[email.lower()] = CODE

    async def set_password(self, access_token, password, client_ip):
        import jwt

        sub = UUID(jwt.decode(access_token, options={"verify_signature": False})["sub"])
        self.passwords_set.append((sub, password))
        for account in self.accounts.values():
            if account["id"] == sub:
                account["password"] = password

    async def sign_out(self, access_token, scope, client_ip):
        self.signed_out.append((access_token, scope))

    def called(self, name: str) -> list[tuple]:
        return [c for c in self.calls if c[0] == name]


@pytest.fixture
async def fake_auth(app, owner_db):
    created: list[UUID] = []

    async def create_account(email: str, full_name: str) -> UUID:
        user_id = uuid4()
        await owner_db.execute(
            """
            INSERT INTO auth.users (id, email, raw_user_meta_data, created_at, updated_at)
            VALUES ($1, $2, jsonb_build_object('full_name', $3::text), now(), now())
            """,
            user_id, email, full_name,
        )
        created.append(user_id)
        return user_id

    fake = FakeAuth(create_account)
    app.dependency_overrides[get_supabase_auth] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_supabase_auth, None)
    if created:
        await owner_db.execute("DELETE FROM public.users WHERE id = ANY($1::uuid[])", created)
        await owner_db.execute("DELETE FROM auth.users WHERE id = ANY($1::uuid[])", created)


async def _records(owner_db, action: str, email: str) -> list[dict]:
    rows = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE action = $1 AND actor_email = $2 ORDER BY id",
        action,
        email,
    )
    return [dict(r) for r in rows]


def _unique_email() -> str:
    return f"{uuid4().hex[:12]}@example.com"


@pytest.fixture
async def officer(make_account, fake_auth):
    """An active crewing officer with a password, known to Supabase Auth."""
    email = _unique_email()
    user_id = await make_account(role="crewing_officer", email=email)
    fake_auth.add(email, user_id)
    return email, user_id


async def _login(client, email: str, password: str = PASSWORD) -> str:
    res = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["challenge"]


# --- step 1: the password -------------------------------------------------------


async def test_the_right_password_sends_a_code_and_opens_no_session(client, fake_auth, officer):
    email, _ = officer

    res = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})

    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"challenge", "message"}
    assert "access_token" not in res.text
    assert fake_auth.called("send_code") == [("send_code", email)]
    # The session Supabase Auth opened for the password alone is ended.
    [(_, scope)] = fake_auth.signed_out
    assert scope == "local"


async def test_a_wrong_password_and_an_unknown_email_get_the_same_answer(
    client, owner_db, fake_auth, officer
):
    email, user_id = officer
    unknown = _unique_email()

    wrong = await client.post("/api/auth/login", json={"email": email, "password": "not-it-123"})
    nobody = await client.post("/api/auth/login", json={"email": unknown, "password": PASSWORD})

    assert wrong.status_code == nobody.status_code == 400
    assert wrong.json() == nobody.json()
    assert wrong.json()["detail"] == {
        "code": "invalid_credentials",
        "message": "Wrong e-mail or password.",
    }
    assert fake_auth.called("send_code") == []
    [rec] = await _records(owner_db, "login_failed", email)
    assert rec["actor_id"] == user_id
    assert rec["reason"] == "invalid_credentials"
    assert rec["outcome"] == "refused"
    assert str(rec["ip"]) == "127.0.0.1"
    [rec] = await _records(owner_db, "login_failed", unknown)
    assert rec["actor_id"] is None


async def test_a_code_asked_again_within_a_minute_still_gives_a_challenge(
    client, fake_auth, officer
):
    email, _ = officer
    fake_auth.send_rate_limited = True

    res = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})

    assert res.status_code == 200
    assert res.json()["challenge"]


async def test_an_unfinished_register_gets_its_confirmation_code_again(
    client, fake_auth, make_account
):
    email = _unique_email()
    user_id = await make_account(status="pending", email=email)
    fake_auth.add(email, user_id, confirmed=False)

    challenge = await _login(client, email)

    assert fake_auth.called("resend_confirmation") == [("resend_confirmation", email)]
    res = await client.post(
        "/api/auth/verify", json={"email": email, "challenge": challenge, "code": CODE}
    )
    assert res.status_code == 200


# --- registering ----------------------------------------------------------------


async def test_register_creates_the_account_with_its_full_name_and_password(
    client, owner_db, fake_auth
):
    email = _unique_email()

    res = await client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "  Ana Kovač ", "password": PASSWORD},
    )

    assert res.status_code == 200
    assert set(res.json()) == {"challenge", "message"}
    assert fake_auth.called("sign_up") == [
        ("sign_up", email, PASSWORD, "Ana Kovač", "127.0.0.1")
    ]
    assert fake_auth.codes[email] == CODE


async def test_register_answers_an_existing_account_the_same_but_no_code_lets_it_in(
    client, fake_auth, officer
):
    email, _ = officer
    new = await client.post(
        "/api/auth/register",
        json={"email": _unique_email(), "full_name": "New Person", "password": PASSWORD},
    )
    again = await client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "Someone Else", "password": "other-pass-1"},
    )

    assert new.status_code == again.status_code == 200
    assert set(new.json()) == set(again.json())
    assert new.json()["message"] == again.json()["message"]

    # Even the Account's real code can't complete the decoy.
    fake_auth.codes[email] = CODE
    res = await client.post(
        "/api/auth/verify",
        json={"email": email, "challenge": again.json()["challenge"], "code": CODE},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "otp_invalid"
    assert fake_auth.called("verify_code") == []


@pytest.mark.parametrize(
    "body",
    [
        {"full_name": " ", "password": PASSWORD},
        {"full_name": "Ana Kovač", "password": "short1"},
        {"full_name": "Ana Kovač", "password": "x" * 73},
        {"full_name": "Ana Kovač"},
    ],
)
async def test_register_needs_a_full_name_and_a_password_of_8_to_72(client, fake_auth, body):
    res = await client.post("/api/auth/register", json={"email": _unique_email(), **body})

    assert res.status_code == 422
    assert fake_auth.calls == []


async def test_a_weak_password_refused_by_supabase_is_shown(client, fake_auth):
    async def weak(*_):
        raise SignInRefused(422, "weak_password", "Password should contain letters and digits.")

    fake_auth.sign_up = weak

    res = await client.post(
        "/api/auth/register",
        json={"email": _unique_email(), "full_name": "Ana", "password": "aaaaaaaa"},
    )

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "weak_password"


async def test_without_email_confirmation_register_still_needs_the_code(client, fake_auth):
    # Local Supabase confirms addresses on its own and answers with a session.
    fake_auth.autoconfirm = True
    email = _unique_email()

    res = await client.post(
        "/api/auth/register", json={"email": email, "full_name": "Ana", "password": PASSWORD}
    )

    assert res.status_code == 200
    assert "access_token" not in res.text
    assert len(fake_auth.signed_out) == 1
    assert fake_auth.called("send_code") == [("send_code", email)]


# --- step 2: the code -----------------------------------------------------------


async def test_the_right_code_returns_a_session_the_api_accepts(
    client, owner_db, fake_auth, officer
):
    email, user_id = officer
    challenge = await _login(client, email)

    res = await client.post(
        "/api/auth/verify", json={"email": email, "challenge": challenge, "code": f" {CODE} "}
    )

    assert res.status_code == 200
    session = res.json()
    me = await client.get(
        "/api/me", headers={"Authorization": f"Bearer {session['access_token']}"}
    )
    assert me.status_code == 200
    [rec] = await _records(owner_db, "login_succeeded", email)
    assert rec["actor_id"] == user_id
    assert rec["actor_role"] == "crewing_officer"
    assert rec["target_type"] == "account"
    assert rec["target_id"] == str(user_id)
    assert rec["outcome"] == "succeeded"
    assert await _records(owner_db, "login_failed", email) == []


async def test_a_challenge_works_once(client, fake_auth, officer):
    email, _ = officer
    challenge = await _login(client, email)
    body = {"email": email, "challenge": challenge, "code": CODE}
    assert (await client.post("/api/auth/verify", json=body)).status_code == 200
    fake_auth.codes[email] = CODE

    again = await client.post("/api/auth/verify", json=body)

    assert again.status_code == 400
    assert again.json()["detail"]["code"] == "challenge_expired"


@pytest.mark.parametrize(
    ("code", "expired", "expected"),
    [("000000", False, "otp_invalid"), (CODE, True, "otp_expired")],
)
async def test_a_wrong_or_expired_code_is_recorded_against_the_account(
    client, owner_db, fake_auth, officer, code, expired, expected
):
    email, user_id = officer
    challenge = await _login(client, email)
    if expired:
        fake_auth.expired.add(email)

    # The e-mail is matched the way it was typed, whatever its case.
    typed = email.upper()
    res = await client.post(
        "/api/auth/verify", json={"email": typed, "challenge": challenge, "code": code}
    )

    assert res.status_code == 403
    assert res.json()["detail"]["code"] == expected
    [rec] = await _records(owner_db, "login_failed", typed)
    assert rec["actor_id"] == user_id
    assert rec["actor_role"] == "crewing_officer"
    assert rec["target_type"] == "account"
    assert rec["reason"] == expected


async def test_five_wrong_codes_end_the_challenge(client, fake_auth, officer):
    email, _ = officer
    challenge = await _login(client, email)
    for _ in range(5):
        res = await client.post(
            "/api/auth/verify", json={"email": email, "challenge": challenge, "code": "000000"}
        )
        assert res.status_code == 403

    right = await client.post(
        "/api/auth/verify", json={"email": email, "challenge": challenge, "code": CODE}
    )

    assert right.status_code == 400
    assert right.json()["detail"]["code"] == "challenge_expired"


@pytest.mark.parametrize("challenge", ["made-up", "x" * 43])
async def test_a_code_without_a_real_challenge_is_refused(
    client, owner_db, fake_auth, officer, challenge
):
    email, _ = officer
    fake_auth.codes[email] = CODE

    res = await client.post(
        "/api/auth/verify", json={"email": email, "challenge": challenge, "code": CODE}
    )

    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "challenge_expired"
    assert fake_auth.called("verify_code") == []
    [rec] = await _records(owner_db, "login_failed", email)
    assert rec["reason"] == "challenge_expired"


async def test_a_challenge_is_only_for_its_own_email(client, fake_auth, officer, make_account):
    email, _ = officer
    other = _unique_email()
    fake_auth.add(other, await make_account(email=other))
    challenge = await _login(client, email)
    fake_auth.codes[other] = CODE

    res = await client.post(
        "/api/auth/verify", json={"email": other, "challenge": challenge, "code": CODE}
    )

    assert res.status_code == 400
    assert fake_auth.called("verify_code") == []


@pytest.mark.parametrize("code", ["", "12345", "1234567", "12a456"])
async def test_a_code_is_six_digits(client, fake_auth, code):
    res = await client.post(
        "/api/auth/verify", json={"email": _unique_email(), "challenge": "c", "code": code}
    )

    assert res.status_code == 422
    assert fake_auth.calls == []


async def test_a_new_code_can_be_sent_for_an_open_challenge(client, fake_auth, officer):
    email, _ = officer
    challenge = await _login(client, email)

    res = await client.post("/api/auth/code", json={"challenge": challenge})
    expired = await client.post("/api/auth/code", json={"challenge": "made-up"})

    assert res.status_code == 200
    assert fake_auth.called("send_code") == [("send_code", email), ("send_code", email)]
    assert expired.status_code == 400
    assert expired.json()["detail"]["code"] == "challenge_expired"


async def test_a_new_code_for_a_register_is_the_confirmation_again(client, fake_auth):
    email = _unique_email()
    res = await client.post(
        "/api/auth/register", json={"email": email, "full_name": "Ana", "password": PASSWORD}
    )

    again = await client.post("/api/auth/code", json={"challenge": res.json()["challenge"]})

    assert again.status_code == 200
    assert fake_auth.called("resend_confirmation") == [("resend_confirmation", email)]


# --- only sessions that passed both steps get in --------------------------------


async def test_a_session_from_a_password_or_a_code_alone_is_refused(client, make_account):
    # What a direct call to Supabase Auth with the public key would give.
    user_id = await make_account(role="crewing_officer")
    token = make_token(user_id, session_id=uuid4())

    res = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "session_not_verified"


async def test_a_verified_session_is_only_for_its_own_account(client, make_account):
    first = await make_account(role="crewing_officer")
    second = await make_account(role="crewing_officer")
    # The first Account's verified session id, in a token for the second.
    token = make_token(second, session_id=first)

    res = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 401


async def test_passwords_are_kept(owner_db, make_account):
    # ADR-0004's trigger that blanked every password is gone.
    account = await make_account()
    await owner_db.execute(
        "UPDATE auth.users SET encrypted_password = '$2a$10$hash' WHERE id = $1", account
    )

    assert await owner_db.fetchval(
        "SELECT encrypted_password FROM auth.users WHERE id = $1", account
    ) == "$2a$10$hash"


# --- a forgotten password -------------------------------------------------------


async def test_forgot_password_answers_every_email_the_same(client, fake_auth, officer):
    email, _ = officer

    known = await client.post("/api/auth/password/forgot", json={"email": email})
    unknown = await client.post("/api/auth/password/forgot", json={"email": _unique_email()})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


async def test_a_reset_sets_the_password_and_signs_out_everywhere(
    client, owner_db, fake_auth, officer
):
    email, user_id = officer
    await client.post("/api/auth/password/forgot", json={"email": email})

    res = await client.post(
        "/api/auth/password/reset",
        json={"email": email, "code": CODE, "password": "a-new-password-2"},
    )

    assert res.status_code == 200
    assert fake_auth.passwords_set == [(user_id, "a-new-password-2")]
    assert [scope for _, scope in fake_auth.signed_out] == ["global"]
    # The session signed in before the reset no longer gets in.
    assert (await client.get("/api/me", headers=auth_header(user_id))).status_code == 401
    [rec] = await _records(owner_db, "password_reset", email)
    assert rec["actor_id"] == user_id
    assert rec["outcome"] == "succeeded"
    # The new password then works for step 1.
    assert await _login(client, email, "a-new-password-2")


async def test_a_wrong_reset_code_changes_nothing(client, owner_db, fake_auth, officer):
    email, user_id = officer
    await client.post("/api/auth/password/forgot", json={"email": email})

    res = await client.post(
        "/api/auth/password/reset",
        json={"email": email, "code": "000000", "password": "a-new-password-2"},
    )

    assert res.status_code == 403
    assert fake_auth.passwords_set == []
    assert (await client.get("/api/me", headers=auth_header(user_id))).status_code == 200
    [rec] = await _records(owner_db, "password_reset", email)
    assert rec["outcome"] == "refused"
    assert rec["reason"] == "otp_invalid"


# --- Auth down ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "extra"),
    [
        ("/api/auth/login", {"password": PASSWORD}),
        ("/api/auth/register", {"full_name": "Ana Kovač", "password": PASSWORD}),
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


async def test_auth_down_while_checking_the_code(client, owner_db, fake_auth, officer):
    email, _ = officer
    challenge = await _login(client, email)
    fake_auth.down = True

    res = await client.post(
        "/api/auth/verify", json={"email": email, "challenge": challenge, "code": CODE}
    )

    assert res.status_code == 503
    [rec] = await _records(owner_db, "login_failed", email)
    assert rec["reason"] == "auth_unavailable"


# --- logout ---------------------------------------------------------------------


async def test_logout_is_recorded_and_ends_the_session(client, owner_db, make_account):
    email = _unique_email()
    officer_id = await make_account(role="crewing_officer", email=email)

    res = await client.post("/api/auth/logout", headers=auth_header(officer_id))

    assert res.status_code == 204
    [rec] = await _records(owner_db, "logout", email)
    assert rec["actor_id"] == officer_id
    assert rec["actor_role"] == "crewing_officer"
    assert rec["outcome"] == "succeeded"
    assert (await client.get("/api/me", headers=auth_header(officer_id))).status_code == 401


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


async def _remove(owner_db, user_id) -> None:
    base = app_settings.supabase_url.rstrip("/")
    key = app_settings.supabase_service_role_key
    # The Account row blocks deleting its auth user, so it goes first.
    await owner_db.execute("DELETE FROM public.users WHERE id = $1", user_id)
    async with httpx.AsyncClient() as http:
        await http.delete(
            f"{base}/auth/v1/admin/users/{user_id}",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
        )


@needs_auth
@needs_mailpit
async def test_real_auth_register_then_sign_in_with_password_and_code(client, owner_db):
    email = _unique_email()
    registered = await client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "Real Auth Test", "password": PASSWORD},
    )
    assert registered.status_code == 200, registered.text
    user_id = await owner_db.fetchval(
        "SELECT id FROM public.users WHERE lower(email) = lower($1)", email
    )
    try:
        assert await owner_db.fetchval(
            "SELECT coalesce(encrypted_password, '') <> '' FROM auth.users WHERE id = $1",
            user_id,
        )
        code = await _code_from_mailpit(email)
        challenge = registered.json()["challenge"]
        wrong_code = "000000" if code != "000000" else "111111"

        wrong = await client.post(
            "/api/auth/verify", json={"email": email, "challenge": challenge, "code": wrong_code}
        )
        right = await client.post(
            "/api/auth/verify", json={"email": email, "challenge": challenge, "code": code}
        )

        assert wrong.status_code >= 400
        assert right.status_code == 200, right.text
        token = right.json()["access_token"]
        me = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        assert me.json()["status"] == "pending"
        assert len(await _records(owner_db, "login_failed", email)) == 1
        assert await owner_db.fetchval(
            "SELECT count(*) FROM public.audit_log"
            " WHERE action = 'login_succeeded' AND actor_id = $1",
            user_id,
        ) == 1
    finally:
        if user_id:
            await _remove(owner_db, user_id)


@needs_auth
async def test_real_auth_a_password_grant_alone_does_not_get_in(client, owner_db, make_account):
    base = app_settings.supabase_url.rstrip("/")
    key = app_settings.supabase_service_role_key
    email = _unique_email()
    async with httpx.AsyncClient() as http:
        created = await http.post(
            f"{base}/auth/v1/admin/users",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            json={"email": email, "password": PASSWORD, "email_confirm": True},
        )
        created.raise_for_status()
        user_id = UUID(created.json()["id"])
        try:
            # Straight to Supabase Auth with the public key, skipping the proxy.
            grant = await http.post(
                f"{base}/auth/v1/token",
                params={"grant_type": "password"},
                headers={"apikey": app_settings.supabase_anon_key or key},
                json={"email": email, "password": PASSWORD},
            )
            assert grant.status_code == 200, grant.text
            token = grant.json()["access_token"]

            me = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

            assert me.status_code == 401
            assert me.json()["detail"]["code"] == "session_not_verified"
        finally:
            await _remove(owner_db, user_id)
