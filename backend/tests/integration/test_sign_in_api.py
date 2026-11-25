"""The sign-in proxy: a password, then a TOTP code from an authenticator
app (R1, T7, ADR 0002, ADR 0005, ADR 0007, SR-03).

`POST /api/auth/login` checks the password and answers with a Sign-in
Challenge for the TOTP step (`totp`, or `enrol` at the first sign-in);
`/register` creates the Account and answers with a challenge for the
e-mailed confirmation code (`email`), which then leads on to `enrol`;
`/code` sends the confirmation code again; `/verify` checks a code against
the challenge and, after the TOTP step, returns the aal2 session. Only aal2
sessions that passed the proxy get into the API. `/password/forgot` and
`/password/reset` replace a forgotten password. Most tests stand in for
Supabase Auth (an outside service); the last ones run against a real local
Auth (and Mailpit) and skip when they are unreachable.
"""

import logging
import os
import re
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from app.config import settings as app_settings
from app.pwned_passwords import PwnedPasswords, get_pwned_passwords
from app.supabase_auth import AuthUnavailable, SignInRefused, get_supabase_auth

from tests.conftest import auth_header, make_token

CODE = "123456"  # the e-mailed code (Register, forgotten password)
TOTP = "654321"  # what the authenticator app shows
PASSWORD = "correct-horse-1"
QR_SVG = '<svg xmlns="http://www.w3.org/2000/svg"></svg>'


class FakeAuth:
    """Supabase Auth with e-mail confirmation and TOTP on: Accounts with
    passwords, e-mailed codes, TOTP factors and the sessions they open."""

    def __init__(self, create_account) -> None:
        # Makes the auth.users row (and so the Account) that GoTrue would.
        self.create_account = create_account
        # e-mail -> {"id", "password", "confirmed"}
        self.accounts: dict[str, dict] = {}
        # user id -> [{"id", "factor_type", "status"}]
        self.factors: dict[UUID, list[dict]] = {}
        self.codes: dict[str, str] = {}
        self.reset_codes: dict[str, str] = {}
        self.expired: set[str] = set()
        self.autoconfirm = False
        self.send_rate_limited = False
        self.down = False
        self.calls: list[tuple] = []
        self.signed_out: list[tuple[str, str]] = []
        self.passwords_set: list[tuple[UUID, str]] = []
        # The aal1 tokens handed to the proxy.
        self.aal1_tokens: list[str] = []
        # refresh token -> (e-mail, session id, aal) of a live session.
        self.refresh_tokens: dict[str, tuple[str, UUID, str]] = {}

    def add(
        self,
        email: str,
        user_id: UUID,
        password: str = PASSWORD,
        confirmed: bool = True,
        totp: bool = False,
    ):
        self.accounts[email.lower()] = {"id": user_id, "password": password, "confirmed": confirmed}
        if totp:
            self.factors[user_id] = [
                {"id": str(uuid4()), "factor_type": "totp", "status": "verified"}
            ]

    def _session(self, email: str, session_id: UUID | None = None, aal: str = "aal1") -> dict:
        user_id = self.accounts[email.lower()]["id"]
        session_id = session_id or uuid4()
        token = make_token(user_id, email, session_id=session_id, aal=aal)
        if aal == "aal1":
            self.aal1_tokens.append(token)
        refresh_token = f"refresh-{uuid4().hex}"
        self.refresh_tokens[refresh_token] = (email, session_id, aal)
        return {
            "access_token": token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 3600,
            "user": {"id": str(user_id), "email": email.lower()},
        }

    @staticmethod
    def _claims(access_token: str) -> dict:
        return jwt.decode(access_token, options={"verify_signature": False})

    def _user(self, access_token: str) -> UUID:
        return UUID(self._claims(access_token)["sub"])

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
        self.calls.append(("set_password",))
        self._check()
        sub = self._user(access_token)
        # As GoTrue: with a verified factor, only an aal2 session may change
        # the password (the bug of F-01 when the reset skipped the TOTP).
        verified = any(f["status"] == "verified" for f in self.factors.get(sub, []))
        if verified and self._claims(access_token).get("aal") != "aal2":
            raise SignInRefused(
                401, "insufficient_aal",
                "AAL2 session is required to update email or password when MFA is enabled.",
            )
        self.passwords_set.append((sub, password))
        for account in self.accounts.values():
            if account["id"] == sub:
                account["password"] = password

    async def sign_out(self, access_token, scope, client_ip):
        self.signed_out.append((access_token, scope))
        # Local: the session's refresh tokens stop working.
        session_id = UUID(self._claims(access_token)["session_id"])
        self.refresh_tokens = {
            t: s for t, s in self.refresh_tokens.items() if s[1] != session_id
        }

    async def refresh(self, refresh_token, client_ip):
        self.calls.append(("refresh", client_ip))
        self._check()
        # As GoTrue: a refresh token is used once; the session keeps its id and aal.
        found = self.refresh_tokens.pop(refresh_token, None)
        if found is None:
            raise SignInRefused(
                400, "refresh_token_not_found", "Invalid Refresh Token: Refresh Token Not Found"
            )
        email, session_id, aal = found
        return self._session(email, session_id=session_id, aal=aal)

    # --- MFA ---

    async def list_factors(self, access_token, client_ip):
        self.calls.append(("list_factors",))
        self._check()
        return [dict(f) for f in self.factors.get(self._user(access_token), [])]

    async def enroll_totp(self, access_token, client_ip):
        self.calls.append(("enroll_totp",))
        self._check()
        factor = {"id": str(uuid4()), "factor_type": "totp", "status": "unverified"}
        self.factors.setdefault(self._user(access_token), []).append(factor)
        return {
            "id": factor["id"],
            "type": "totp",
            "totp": {
                "qr_code": QR_SVG,
                "secret": "JBSWY3DPEHPK3PXP",
                "uri": "otpauth://totp/Maritime:someone?secret=JBSWY3DPEHPK3PXP",
            },
        }

    def _factor(self, access_token: str, factor_id: str) -> dict:
        for factor in self.factors.get(self._user(access_token), []):
            if factor["id"] == factor_id:
                return factor
        raise SignInRefused(404, "mfa_factor_not_found", "Factor not found")

    async def challenge(self, access_token, factor_id, client_ip):
        self.calls.append(("challenge", factor_id))
        self._check()
        self._factor(access_token, factor_id)
        return str(uuid4())

    async def verify_totp(self, access_token, factor_id, challenge_id, code, client_ip):
        self.calls.append(("verify_totp", factor_id, code))
        self._check()
        factor = self._factor(access_token, factor_id)
        if code != TOTP:
            raise SignInRefused(422, "mfa_verification_failed", "Invalid TOTP code entered")
        factor["status"] = "verified"
        user_id = self._user(access_token)
        # As GoTrue: a verified factor drops the unfinished enrolments.
        self.factors[user_id] = [
            f for f in self.factors[user_id] if f is factor or f["status"] == "verified"
        ]
        email = self._claims(access_token)["email"]
        session_id = UUID(self._claims(access_token)["session_id"])
        return self._session(email, session_id=session_id, aal="aal2")

    async def unenroll(self, access_token, factor_id, client_ip):
        self.calls.append(("unenroll", factor_id))
        user_id = self._user(access_token)
        self.factors[user_id] = [f for f in self.factors[user_id] if f["id"] != factor_id]

    async def delete_factors(self, user_id):
        self.calls.append(("delete_factors", user_id))
        self._check()
        self.factors.pop(UUID(user_id), None)

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


def _unique_ip() -> str:
    n = uuid4().int
    return f"198.{18 + n % 2}.{(n >> 8) % 256}.{(n >> 16) % 254 + 1}"


@pytest.fixture
async def client(app):
    """The app over HTTP from an address of its own: failed sign-ins are
    also counted per address (SR-18), so tests must not share one."""
    ip = _unique_ip()
    transport = ASGITransport(app=app, client=(ip, 123))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c.ip = ip
        yield c


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
    """An active crewing officer with a password and an enrolled authenticator."""
    email = _unique_email()
    user_id = await make_account(role="crewing_officer", email=email)
    fake_auth.add(email, user_id, totp=True)
    return email, user_id


@pytest.fixture
async def newcomer(make_account, fake_auth):
    """An active crewing officer who has not enrolled an authenticator yet."""
    email = _unique_email()
    user_id = await make_account(role="crewing_officer", email=email)
    fake_auth.add(email, user_id)
    return email, user_id


async def _login(client, email: str, password: str = PASSWORD) -> str:
    res = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["challenge"]


async def _verify(client, email: str, challenge: str, code: str = TOTP):
    return await client.post(
        "/api/auth/verify", json={"email": email, "challenge": challenge, "code": code}
    )


def _bearer(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['access_token']}"}


async def _challenge_row(owner_db, user_id: UUID):
    return await owner_db.fetchrow(
        "SELECT * FROM public.sign_in_challenge WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1",
        user_id,
    )


# --- step 1: the password -------------------------------------------------------


async def test_the_right_password_asks_for_the_authenticator_and_sends_no_mail(
    client, fake_auth, officer
):
    email, _ = officer

    res = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})

    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"challenge", "step", "message"}
    assert body["step"] == "totp"
    assert "authenticator" in body["message"]
    # No session, not even the aal1 one, leaves the proxy.
    assert "access_token" not in res.text
    assert not any(token in res.text for token in fake_auth.aal1_tokens)
    # Signing in no longer e-mails anything.
    assert fake_auth.codes == {}
    assert fake_auth.called("resend_confirmation") == []
    assert fake_auth.called("enroll_totp") == []


async def test_the_first_sign_in_enrols_an_authenticator(client, owner_db, fake_auth, newcomer):
    email, user_id = newcomer

    res = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})

    assert res.status_code == 200
    body = res.json()
    assert body["step"] == "enrol"
    assert body["qr_code"] == QR_SVG
    assert body["secret"] == "JBSWY3DPEHPK3PXP"
    assert body["uri"].startswith("otpauth://totp/")
    assert "access_token" not in res.text
    row = await _challenge_row(owner_db, user_id)
    assert str(row["factor_id"]) == fake_auth.factors[user_id][0]["id"]
    # The aal1 token stays in the challenge row, for the verify call.
    assert row["access_token"] == fake_auth.aal1_tokens[-1]


async def test_enrolling_then_a_right_code_gives_a_session_the_api_accepts(
    client, owner_db, fake_auth, newcomer
):
    email, user_id = newcomer
    challenge = await _login(client, email)

    res = await _verify(client, email, challenge, f" {TOTP} ")

    assert res.status_code == 200, res.text
    session = res.json()
    assert jwt.decode(session["access_token"], options={"verify_signature": False})["aal"] == "aal2"
    me = await client.get("/api/me", headers=_bearer(session))
    assert me.status_code == 200
    assert fake_auth.factors[user_id][0]["status"] == "verified"
    [rec] = await _records(owner_db, "login_succeeded", email)
    assert rec["actor_id"] == user_id
    # The aal1 token is gone from the database once used.
    assert (await _challenge_row(owner_db, user_id))["access_token"] is None

    # The next sign-in asks for the code of the enrolled authenticator.
    again = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert again.json()["step"] == "totp"
    assert len(fake_auth.called("enroll_totp")) == 1


async def test_an_unfinished_enrolment_is_replaced(client, fake_auth, newcomer):
    email, user_id = newcomer
    await _login(client, email)
    [first] = fake_auth.factors[user_id]

    await _login(client, email)

    assert fake_auth.called("unenroll") == [("unenroll", first["id"])]
    [second] = fake_auth.factors[user_id]
    assert second["id"] != first["id"] and second["status"] == "unverified"


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
    assert fake_auth.called("list_factors") == []
    [rec] = await _records(owner_db, "login_failed", email)
    assert rec["actor_id"] == user_id
    assert rec["reason"] == "invalid_credentials"
    assert rec["outcome"] == "refused"
    assert str(rec["ip"]) == client.ip
    [rec] = await _records(owner_db, "login_failed", unknown)
    assert rec["actor_id"] is None


async def test_an_unfinished_register_gets_its_confirmation_code_again(
    client, fake_auth, make_account
):
    email = _unique_email()
    user_id = await make_account(status="pending", email=email)
    fake_auth.add(email, user_id, confirmed=False)

    res = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})

    assert res.json()["step"] == "email"
    assert fake_auth.called("resend_confirmation") == [("resend_confirmation", email)]
    enrol = await _verify(client, email, res.json()["challenge"], CODE)
    assert enrol.status_code == 200
    assert enrol.json()["step"] == "enrol"
    session = await _verify(client, email, enrol.json()["challenge"], TOTP)
    assert session.status_code == 200
    assert "access_token" in session.json()


async def test_a_confirmation_code_asked_again_within_a_minute_still_gives_a_challenge(
    client, fake_auth, make_account
):
    email = _unique_email()
    fake_auth.add(email, await make_account(status="pending", email=email), confirmed=False)
    fake_auth.send_rate_limited = True

    res = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})

    assert res.status_code == 200
    assert res.json()["challenge"]


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
    assert set(res.json()) == {"challenge", "step", "message"}
    assert res.json()["step"] == "email"
    assert fake_auth.called("sign_up") == [
        ("sign_up", email, PASSWORD, "Ana Kovač", client.ip)
    ]
    assert fake_auth.codes[email] == CODE


async def test_register_ends_in_enrolling_an_authenticator(client, owner_db, fake_auth):
    email = _unique_email()
    registered = await client.post(
        "/api/auth/register", json={"email": email, "full_name": "Ana", "password": PASSWORD}
    )

    enrol = await _verify(client, email, registered.json()["challenge"], CODE)

    assert enrol.status_code == 200
    assert enrol.json()["step"] == "enrol"
    assert enrol.json()["qr_code"] == QR_SVG
    assert "access_token" not in enrol.text
    # The confirmation code alone lets no one in.
    assert await _records(owner_db, "login_succeeded", email) == []
    # The e-mailed code's challenge is used up.
    again = await _verify(client, email, registered.json()["challenge"], CODE)
    assert again.json()["detail"]["code"] == "challenge_expired"

    session = await _verify(client, email, enrol.json()["challenge"], TOTP)
    assert session.status_code == 200
    me = await client.get("/api/me", headers=_bearer(session.json()))
    assert me.status_code == 200
    assert me.json()["status"] == "pending"


async def test_register_answers_an_existing_account_the_same_but_no_code_lets_it_in(
    client, owner_db, fake_auth, officer
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
    assert new.json()["step"] == again.json()["step"] == "email"

    # Even the Account's real code can't complete the decoy.
    fake_auth.codes[email] = CODE
    res = await _verify(client, email, again.json()["challenge"], CODE)
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "otp_invalid"
    assert fake_auth.called("verify_code") == []
    # One record for the failed step, not also *Access refused* (FR-22).
    assert await _actions_of(owner_db, res) == ["login_failed"]


@pytest.mark.parametrize(
    "body",
    [
        {"full_name": " ", "password": PASSWORD},
        {"full_name": "Ana Kovač", "password": "short1"},
        {"full_name": "Ana Kovač", "password": "eleven-char"},
        {"full_name": "Ana Kovač", "password": "x" * 73},
        {"full_name": "Ana Kovač"},
    ],
)
async def test_register_needs_a_full_name_and_a_password_of_12_to_72(client, fake_auth, body):
    res = await client.post("/api/auth/register", json={"email": _unique_email(), **body})

    assert res.status_code == 422
    assert fake_auth.calls == []


async def test_a_weak_password_refused_by_supabase_is_shown(client, fake_auth):
    async def weak(*_):
        raise SignInRefused(422, "weak_password", "Password should contain letters and digits.")

    fake_auth.sign_up = weak

    res = await client.post(
        "/api/auth/register",
        json={"email": _unique_email(), "full_name": "Ana", "password": "harbour-pilot-ladder-7"},
    )

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "weak_password"


async def test_without_email_confirmation_register_goes_on_to_enrolling(client, fake_auth):
    # Where Supabase confirms addresses on its own, it answers with a session.
    fake_auth.autoconfirm = True
    email = _unique_email()

    res = await client.post(
        "/api/auth/register", json={"email": email, "full_name": "Ana", "password": PASSWORD}
    )

    assert res.status_code == 200
    assert res.json()["step"] == "enrol"
    assert "access_token" not in res.text
    assert fake_auth.codes == {}


# --- step 2: the authenticator code ---------------------------------------------


async def test_the_right_code_returns_a_session_the_api_accepts(
    client, owner_db, fake_auth, officer
):
    email, user_id = officer
    challenge = await _login(client, email)

    res = await _verify(client, email, challenge)

    assert res.status_code == 200
    session = res.json()
    me = await client.get("/api/me", headers=_bearer(session))
    assert me.status_code == 200
    [rec] = await _records(owner_db, "login_succeeded", email)
    assert rec["actor_id"] == user_id
    assert rec["actor_role"] == "crewing_officer"
    assert rec["target_type"] == "account"
    assert rec["target_id"] == str(user_id)
    assert rec["outcome"] == "succeeded"
    assert await _records(owner_db, "login_failed", email) == []
    [(_, factor_id)] = fake_auth.called("challenge")
    assert factor_id == fake_auth.factors[user_id][0]["id"]


async def test_a_challenge_works_once(client, fake_auth, officer):
    email, _ = officer
    challenge = await _login(client, email)
    assert (await _verify(client, email, challenge)).status_code == 200

    again = await _verify(client, email, challenge)

    assert again.status_code == 400
    assert again.json()["detail"]["code"] == "challenge_expired"


async def test_a_wrong_authenticator_code_is_recorded_against_the_account(
    client, owner_db, fake_auth, officer
):
    email, user_id = officer
    challenge = await _login(client, email)

    # The e-mail is matched the way it was typed, whatever its case.
    typed = email.upper()
    res = await _verify(client, typed, challenge, "000000")

    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "totp_invalid"
    [rec] = await _records(owner_db, "login_failed", typed)
    assert rec["actor_id"] == user_id
    assert rec["actor_role"] == "crewing_officer"
    assert rec["target_type"] == "account"
    assert rec["reason"] == "totp_invalid"
    # One record for the failed step, not also *Access refused* (FR-22).
    assert await _actions_of(owner_db, res) == ["login_failed"]
    # The challenge is still open for the right code.
    assert (await _verify(client, email, challenge)).status_code == 200


@pytest.mark.parametrize(
    ("code", "expired", "expected"),
    [("000000", False, "otp_invalid"), (CODE, True, "otp_expired")],
)
async def test_a_wrong_or_expired_confirmation_code_is_recorded(
    client, owner_db, fake_auth, code, expired, expected
):
    email = _unique_email()
    registered = await client.post(
        "/api/auth/register", json={"email": email, "full_name": "Ana", "password": PASSWORD}
    )
    if expired:
        fake_auth.expired.add(email)

    res = await _verify(client, email, registered.json()["challenge"], code)

    assert res.status_code == 403
    assert res.json()["detail"]["code"] == expected
    [rec] = await _records(owner_db, "login_failed", email)
    assert rec["reason"] == expected


async def test_five_wrong_codes_end_the_challenge(client, owner_db, fake_auth, officer):
    email, user_id = officer
    challenge = await _login(client, email)
    aal1 = fake_auth.aal1_tokens[-1]
    for _ in range(5):
        res = await _verify(client, email, challenge, "000000")
        assert res.status_code == 403

    right = await _verify(client, email, challenge)

    assert right.status_code == 400
    assert right.json()["detail"]["code"] == "challenge_expired"
    assert len(fake_auth.called("verify_totp")) == 5
    assert len(await _records(owner_db, "login_failed", email)) == 6
    # The aal1 token is removed and its session ended.
    assert (await _challenge_row(owner_db, user_id))["access_token"] is None
    assert (aal1, "local") in fake_auth.signed_out


async def test_a_challenge_whose_session_is_gone_must_be_started_again(
    client, owner_db, fake_auth, officer
):
    email, user_id = officer
    challenge = await _login(client, email)
    fake_auth.factors[user_id] = []  # e.g. reset by an administrator meanwhile

    res = await _verify(client, email, challenge)

    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "challenge_expired"
    assert (await _challenge_row(owner_db, user_id))["access_token"] is None


@pytest.mark.parametrize("challenge", ["made-up", "x" * 43])
async def test_a_code_without_a_real_challenge_is_refused(
    client, owner_db, fake_auth, officer, challenge
):
    email, _ = officer

    res = await _verify(client, email, challenge)

    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "challenge_expired"
    assert fake_auth.called("verify_totp") == []
    [rec] = await _records(owner_db, "login_failed", email)
    assert rec["reason"] == "challenge_expired"


async def test_a_challenge_is_only_for_its_own_email(client, fake_auth, officer, make_account):
    email, _ = officer
    other = _unique_email()
    fake_auth.add(other, await make_account(email=other), totp=True)
    challenge = await _login(client, email)

    res = await _verify(client, other, challenge)

    assert res.status_code == 400
    assert fake_auth.called("verify_totp") == []


@pytest.mark.parametrize("code", ["", "12345", "1234567", "12a456"])
async def test_a_code_is_six_digits(client, fake_auth, code):
    res = await client.post(
        "/api/auth/verify", json={"email": _unique_email(), "challenge": "c", "code": code}
    )

    assert res.status_code == 422
    assert fake_auth.calls == []


async def test_no_code_is_e_mailed_for_the_authenticator_step(client, fake_auth, officer):
    email, _ = officer
    challenge = await _login(client, email)

    res = await client.post("/api/auth/code", json={"challenge": challenge})
    expired = await client.post("/api/auth/code", json={"challenge": "made-up"})

    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "no_emailed_code"
    assert fake_auth.codes == {}
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


# --- only aal2 sessions that passed both steps get in ---------------------------


async def test_a_password_only_session_is_refused_and_recorded(client, owner_db, make_account):
    # SR-03: an aal1 token, even for a session the proxy recorded.
    user_id = await make_account(role="crewing_officer")
    email = await owner_db.fetchval("SELECT email FROM public.users WHERE id = $1", user_id)
    token = make_token(user_id, aal="aal1")

    res = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "second_factor_missing"
    [rec] = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE action = 'access_refused' AND request_id = $1",
        res.headers["x-request-id"],
    )
    assert rec["reason"] == "second_factor_missing"
    assert rec["actor_id"] == user_id
    assert rec["actor_email"] == email


async def test_a_session_completed_directly_at_supabase_is_refused(client, make_account):
    # What a direct call to Supabase Auth with the public key would give,
    # even with both factors: the proxy never saw it.
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


# --- a lost authenticator -------------------------------------------------------


async def test_an_administrator_resets_a_lost_authenticator(
    client, owner_db, fake_auth, officer, make_account
):
    email, user_id = officer
    admin = await make_account(role="administrator")
    open_challenge = await _login(client, email)

    res = await client.post(
        f"/api/accounts/{user_id}/second-factor/reset",
        json={"reason": "Phone lost"},
        headers=auth_header(admin),
    )

    assert res.status_code == 200, res.text
    assert res.json()["id"] == str(user_id)
    assert fake_auth.called("delete_factors") == [("delete_factors", str(user_id))]
    [rec] = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE action = 'second_factor_reset' AND target_id = $1",
        str(user_id),
    )
    assert rec["actor_id"] == admin
    assert rec["target_type"] == "account"
    assert rec["reason"] == "Phone lost"
    assert rec["outcome"] == "succeeded"
    # Signed out everywhere, and sign-ins already under way are ended.
    assert (await client.get("/api/me", headers=auth_header(user_id))).status_code == 401
    assert (await _verify(client, email, open_challenge)).status_code == 400
    # The next sign-in enrols a new authenticator.
    again = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert again.json()["step"] == "enrol"


async def test_only_an_administrator_resets_a_second_factor_and_not_their_own(
    client, fake_auth, officer, make_account
):
    _, user_id = officer
    admin = await make_account(role="administrator")
    manager = await make_account(role="manager")
    url = "/api/accounts/{}/second-factor/reset"
    body = {"reason": "r"}

    by_manager = await client.post(url.format(user_id), json=body, headers=auth_header(manager))
    own = await client.post(url.format(admin), json=body, headers=auth_header(admin))
    unknown = await client.post(url.format(uuid4()), json=body, headers=auth_header(admin))
    no_reason = await client.post(url.format(user_id), json={}, headers=auth_header(admin))

    assert by_manager.status_code == 403
    assert own.status_code == 409
    assert unknown.status_code == 404
    assert no_reason.status_code == 422
    assert fake_auth.called("delete_factors") == []


async def test_a_reset_with_auth_down_changes_nothing(
    client, owner_db, fake_auth, officer, make_account
):
    _, user_id = officer
    admin = await make_account(role="administrator")
    fake_auth.down = True

    res = await client.post(
        f"/api/accounts/{user_id}/second-factor/reset",
        json={"reason": "r"},
        headers=auth_header(admin),
    )

    assert res.status_code == 503
    assert (await client.get("/api/me", headers=auth_header(user_id))).status_code == 200
    assert await owner_db.fetchval(
        "SELECT count(*) FROM public.audit_log WHERE action = 'second_factor_reset'"
        " AND target_id = $1",
        str(user_id),
    ) == 0


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
        json={"email": email, "code": CODE, "password": "a-new-password-2", "totp": TOTP},
    )

    assert res.status_code == 200, res.text
    assert fake_auth.passwords_set == [(user_id, "a-new-password-2")]
    assert [scope for _, scope in fake_auth.signed_out] == ["global"]
    # The session signed in before the reset no longer gets in.
    assert (await client.get("/api/me", headers=auth_header(user_id))).status_code == 401
    [rec] = await _records(owner_db, "password_reset", email)
    assert rec["actor_id"] == user_id
    assert rec["outcome"] == "succeeded"
    # The new password then works for step 1, and the authenticator is
    # still needed (ASVS 6.4.3): the e-mail alone opens nothing.
    res = await client.post(
        "/api/auth/login", json={"email": email, "password": "a-new-password-2"}
    )
    assert res.json()["step"] == "totp"


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


async def _reset_with(client, email: str, **extra):
    await client.post("/api/auth/password/forgot", json={"email": email})
    return await client.post(
        "/api/auth/password/reset",
        json={"email": email, "code": CODE, "password": "a-new-password-2", **extra},
    )


async def test_a_recovery_session_alone_cannot_set_the_password_of_an_account_with_an_authenticator(
    fake_auth, officer
):
    """The fake keeps GoTrue's rule, so skipping the TOTP fails here as it
    did against the real Supabase Auth."""
    email, _ = officer
    await fake_auth.send_password_reset(email, None)
    recovery = await fake_auth.verify_code(email, CODE, None, type="recovery")

    with pytest.raises(SignInRefused) as refused:
        await fake_auth.set_password(recovery["access_token"], "a-new-password-2", None)

    assert refused.value.code == "insufficient_aal"


async def test_a_reset_without_the_authenticator_code_is_refused(
    client, owner_db, fake_auth, officer
):
    email, user_id = officer

    res = await _reset_with(client, email)

    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "totp_required"
    assert fake_auth.passwords_set == []
    # The recovery session is of no further use.
    assert [scope for _, scope in fake_auth.signed_out] == ["local"]
    [rec] = await _records(owner_db, "password_reset", email)
    assert rec["actor_id"] == user_id
    assert (rec["outcome"], rec["reason"]) == ("refused", "totp_required")


async def test_a_reset_with_a_wrong_authenticator_code_changes_nothing(
    client, owner_db, fake_auth, officer
):
    email, user_id = officer

    res = await _reset_with(client, email, totp="000000")

    assert res.status_code == 403
    detail = res.json()["detail"]
    assert detail["code"] == "totp_invalid"
    assert "new code" in detail["message"]
    assert fake_auth.passwords_set == []
    assert [scope for _, scope in fake_auth.signed_out] == ["local"]
    [rec] = await _records(owner_db, "password_reset", email)
    assert (rec["outcome"], rec["reason"]) == ("refused", "totp_invalid")
    # One record for the refused reset, not also *Access refused* (FR-22).
    assert await _actions_of(owner_db, res) == ["password_reset"]
    # The old password still works for step 1.
    assert (await client.post(
        "/api/auth/login", json={"email": email, "password": PASSWORD}
    )).status_code == 200


async def test_an_account_without_an_authenticator_resets_with_the_emailed_code_alone(
    client, owner_db, fake_auth, newcomer
):
    """E.g. right after an Administrator's "Reset authenticator"."""
    email, user_id = newcomer

    res = await _reset_with(client, email)

    assert res.status_code == 200, res.text
    assert fake_auth.passwords_set == [(user_id, "a-new-password-2")]
    assert fake_auth.called("verify_totp") == []
    [rec] = await _records(owner_db, "password_reset", email)
    assert rec["outcome"] == "succeeded"


@pytest.mark.parametrize("step", ["list_factors", "challenge", "verify_totp", "set_password"])
async def test_a_reset_with_auth_down_after_the_emailed_code_is_503(
    client, owner_db, fake_auth, officer, step
):
    email, _ = officer

    async def down(*args, **kwargs):
        raise AuthUnavailable()

    setattr(fake_auth, step, down)
    res = await _reset_with(client, email, totp=TOTP)

    assert res.status_code == 503
    assert res.json()["detail"]["code"] == "auth_unavailable"
    assert fake_auth.passwords_set == []
    [rec] = await _records(owner_db, "password_reset", email)
    assert (rec["outcome"], rec["reason"]) == ("refused", "auth_unavailable")


@pytest.mark.parametrize("totp", ["12345", "abcdef", "1234567"])
async def test_a_reset_authenticator_code_is_six_digits(client, fake_auth, officer, totp):
    email, _ = officer

    res = await _reset_with(client, email, totp=totp)

    assert res.status_code == 422
    assert fake_auth.called("verify_code") == []


# --- password rules (SR-02) ------------------------------------------------------

ELEVEN = "harbour-pil"  # 11 characters
TWELVE = "harbour-pilo"  # 12 characters, on no list
COMMON = "Qwerty123456"  # on the bundled list (compared case-insensitively)


class FakePwned:
    """Pwned Passwords with a set of breached passwords."""

    def __init__(self, breached: set[str] = frozenset()) -> None:
        self.breached = set(breached)
        self.asked: list[str] = []

    async def is_breached(self, password: str) -> bool:
        self.asked.append(password)
        return password in self.breached


@pytest.fixture
def pwned(app):
    fake = FakePwned()
    app.dependency_overrides[get_pwned_passwords] = lambda: fake
    return fake


async def _register(client, password: str):
    return await client.post(
        "/api/auth/register",
        json={"email": _unique_email(), "full_name": "Ana Kovač", "password": password},
    )


async def _reset(client, email: str, password: str):
    await client.post("/api/auth/password/forgot", json={"email": email})
    return await client.post(
        "/api/auth/password/reset",
        json={"email": email, "code": CODE, "password": password, "totp": TOTP},
    )


async def test_register_refuses_an_eleven_character_password(client, fake_auth, pwned):
    res = await _register(client, ELEVEN)

    assert res.status_code == 422
    assert fake_auth.called("sign_up") == []
    assert pwned.asked == []


async def test_register_refuses_a_common_password(client, fake_auth, pwned):
    res = await _register(client, COMMON)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "weak_password"
    assert res.json()["detail"]["message"]
    assert fake_auth.called("sign_up") == []
    # The common list is checked first: the password never leaves the host.
    assert pwned.asked == []


async def test_register_refuses_a_breached_password(client, fake_auth, pwned):
    pwned.breached.add(TWELVE)

    res = await _register(client, TWELVE)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "weak_password"
    assert fake_auth.called("sign_up") == []


async def test_register_accepts_a_twelve_character_uncommon_password(client, fake_auth, pwned):
    res = await _register(client, TWELVE)

    assert res.status_code == 200, res.text
    assert pwned.asked == [TWELVE]
    [call] = fake_auth.called("sign_up")
    assert call[2] == TWELVE


async def test_reset_refuses_an_eleven_character_password(client, fake_auth, pwned, officer):
    email, _ = officer

    res = await _reset(client, email, ELEVEN)

    assert res.status_code == 422
    assert fake_auth.called("verify_code") == []
    assert fake_auth.passwords_set == []


@pytest.mark.parametrize("kind", ["common", "breached"])
async def test_reset_refuses_a_weak_password_and_records_it(
    client, owner_db, fake_auth, pwned, officer, kind
):
    email, user_id = officer
    password = COMMON if kind == "common" else TWELVE
    pwned.breached.add(TWELVE)

    res = await _reset(client, email, password)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "weak_password"
    # Checked before the code: it stays usable for a better password.
    assert fake_auth.called("verify_code") == []
    assert fake_auth.passwords_set == []
    [rec] = await _records(owner_db, "password_reset", email)
    assert rec["actor_id"] == user_id
    assert rec["outcome"] == "refused"
    assert rec["reason"] == "weak_password"


async def test_reset_accepts_a_twelve_character_uncommon_password(
    client, fake_auth, pwned, officer
):
    email, user_id = officer

    res = await _reset(client, email, TWELVE)

    assert res.status_code == 200, res.text
    assert fake_auth.passwords_set == [(user_id, TWELVE)]


async def test_a_breached_password_found_through_the_range_api_is_refused(
    app, client, fake_auth
):
    """The real module, answered by httpx.MockTransport: 422, and the request
    carries only the first five hex characters of the SHA-1."""
    import hashlib

    sha1 = hashlib.sha1(TWELVE.encode()).hexdigest().upper()
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=f"{sha1[5:]}:12")

    app.dependency_overrides[get_pwned_passwords] = lambda: PwnedPasswords(
        transport=httpx.MockTransport(handle)
    )

    res = await _register(client, TWELVE)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "weak_password"
    [request] = seen
    assert request.url.path == f"/range/{sha1[:5]}"
    assert sha1[5:] not in str(request.url) and TWELVE not in str(request.url)


async def test_an_unreachable_breach_service_lets_the_password_through(
    app, client, fake_auth, caplog
):
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    app.dependency_overrides[get_pwned_passwords] = lambda: PwnedPasswords(
        transport=httpx.MockTransport(handle)
    )

    with caplog.at_level(logging.WARNING, logger="app.pwned_passwords"):
        res = await _register(client, TWELVE)

    assert res.status_code == 200, res.text
    assert "Pwned Passwords" in caplog.text


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


async def test_logout_is_recorded_and_ends_the_session(client, owner_db, fake_auth, make_account):
    email = _unique_email()
    officer_id = await make_account(role="crewing_officer", email=email)
    headers = auth_header(officer_id)

    res = await client.post("/api/auth/logout", headers=headers)

    assert res.status_code == 204
    # Ended at Supabase Auth too, by the backend (SR-01): this session only.
    assert fake_auth.signed_out == [(headers["Authorization"].split()[1], "local")]
    [rec] = await _records(owner_db, "logout", email)
    assert rec["actor_id"] == officer_id
    assert rec["actor_role"] == "crewing_officer"
    assert rec["outcome"] == "succeeded"
    assert (await client.get("/api/me", headers=auth_header(officer_id))).status_code == 401


async def test_a_pending_account_can_log_out(client, owner_db, fake_auth, make_account):
    email = _unique_email()
    pending = await make_account(status="pending", email=email)

    res = await client.post("/api/auth/logout", headers=auth_header(pending))

    assert res.status_code == 204
    assert len(await _records(owner_db, "logout", email)) == 1
    assert await _records(owner_db, "access_refused", email) == []


async def test_logout_needs_a_token(client, fake_auth):
    assert (await client.post("/api/auth/logout")).status_code == 401
    assert fake_auth.signed_out == []


async def test_logout_works_while_supabase_auth_is_down(client, owner_db, fake_auth, make_account):
    email = _unique_email()
    officer_id = await make_account(role="crewing_officer", email=email)

    async def down(*_):
        raise AuthUnavailable()

    fake_auth.sign_out = down

    res = await client.post("/api/auth/logout", headers=auth_header(officer_id))

    assert res.status_code == 204
    assert len(await _records(owner_db, "logout", email)) == 1
    assert (await client.get("/api/me", headers=auth_header(officer_id))).status_code == 401


# --- refresh: the web client renews its session through the API (SR-01) ---------


async def _signed_in(client, email: str) -> dict:
    """A session that passed the password and the authenticator code."""
    res = await _verify(client, email, await _login(client, email))
    assert res.status_code == 200, res.text
    return res.json()


async def _refresh(client, refresh_token: str):
    return await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})


async def _refusals_for(owner_db, res) -> list[dict]:
    rows = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE action = 'access_refused' AND request_id = $1",
        res.headers["x-request-id"],
    )
    return [dict(r) for r in rows]


async def _actions_of(owner_db, res) -> list[str]:
    """Every audit record one request wrote, oldest first."""
    rows = await owner_db.fetch(
        "SELECT action FROM public.audit_log WHERE request_id = $1 ORDER BY id",
        res.headers["x-request-id"],
    )
    return [r["action"] for r in rows]


def _session_id(session: dict) -> str:
    return jwt.decode(session["access_token"], options={"verify_signature": False})["session_id"]


async def test_a_verified_session_is_refreshed(client, owner_db, fake_auth, officer):
    email, _ = officer
    session = await _signed_in(client, email)

    res = await _refresh(client, session["refresh_token"])

    assert res.status_code == 200, res.text
    renewed = res.json()
    assert renewed["refresh_token"] != session["refresh_token"]
    assert _session_id(renewed) == _session_id(session)
    assert (await client.get("/api/me", headers=_bearer(renewed))).status_code == 200
    assert await _refusals_for(owner_db, res) == []
    # The old refresh token was used up.
    assert (await _refresh(client, session["refresh_token"])).status_code == 401


async def test_refreshing_a_password_only_session_is_refused_and_recorded(
    client, owner_db, fake_auth, officer
):
    email, user_id = officer
    aal1 = await fake_auth.password_grant(email, PASSWORD, None)

    res = await _refresh(client, aal1["refresh_token"])

    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "second_factor_missing"
    assert "access_token" not in res.text
    [rec] = await _refusals_for(owner_db, res)
    assert rec["reason"] == "second_factor_missing"
    assert rec["actor_id"] == user_id
    assert rec["actor_email"] == email
    # The session is no use to anyone: it is ended at Supabase Auth too.
    assert [scope for _, scope in fake_auth.signed_out] == ["local"]


async def test_refreshing_a_session_that_skipped_the_proxy_is_refused_and_recorded(
    client, owner_db, fake_auth, officer
):
    email, user_id = officer
    # aal2, but completed directly at Supabase Auth: never a verified session.
    direct = fake_auth._session(email, aal="aal2")

    res = await _refresh(client, direct["refresh_token"])

    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "session_not_verified"
    [rec] = await _refusals_for(owner_db, res)
    assert rec["reason"] == "session_not_verified"
    assert rec["actor_id"] == user_id


async def test_an_unknown_refresh_token_is_refused_and_recorded(client, owner_db, fake_auth):
    res = await _refresh(client, "made-up-refresh-token")

    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "invalid_session"
    [rec] = await _refusals_for(owner_db, res)
    assert rec["reason"] == "invalid_session"
    assert rec["actor_id"] is None
    assert "made-up-refresh-token" not in str(rec)


async def test_a_session_ended_by_logout_cannot_be_refreshed(
    client, owner_db, fake_auth, officer
):
    email, _ = officer
    session = await _signed_in(client, email)
    assert (await client.post("/api/auth/logout", headers=_bearer(session))).status_code == 204

    res = await _refresh(client, session["refresh_token"])

    assert res.status_code == 401
    assert len(await _refusals_for(owner_db, res)) == 1


async def test_a_session_no_longer_verified_cannot_be_refreshed(
    client, owner_db, fake_auth, officer
):
    """E.g. a password reset ended every session of the Account here."""
    email, user_id = officer
    session = await _signed_in(client, email)
    await owner_db.execute("DELETE FROM public.verified_session WHERE user_id = $1", user_id)

    res = await _refresh(client, session["refresh_token"])

    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "session_not_verified"
    assert len(await _refusals_for(owner_db, res)) == 1


async def test_a_switched_off_account_cannot_refresh(client, owner_db, fake_auth, officer):
    email, user_id = officer
    session = await _signed_in(client, email)
    await owner_db.execute("UPDATE public.users SET status = 'deactivated' WHERE id = $1", user_id)

    res = await _refresh(client, session["refresh_token"])

    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "account_deactivated"
    [rec] = await _refusals_for(owner_db, res)
    assert rec["reason"] == "account_deactivated"


async def test_refresh_with_supabase_auth_down_is_503(client, fake_auth, officer):
    email, _ = officer
    session = await _signed_in(client, email)
    fake_auth.down = True

    res = await _refresh(client, session["refresh_token"])

    assert res.status_code == 503
    assert res.json()["detail"]["code"] == "auth_unavailable"


async def test_a_refresh_token_is_never_echoed(client, fake_auth):
    res = await client.post("/api/auth/refresh", json={"refresh_token": "x" * 5000})

    assert res.status_code == 422
    assert "xxxx" not in res.text


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


def _admin_headers() -> dict[str, str]:
    key = app_settings.supabase_service_role_key
    return {"apikey": key, "Authorization": f"Bearer {key}"}


async def _remove(owner_db, user_id) -> None:
    base = app_settings.supabase_url.rstrip("/")
    # The Account row blocks deleting its auth user, so it goes first.
    await owner_db.execute("DELETE FROM public.users WHERE id = $1", user_id)
    async with httpx.AsyncClient() as http:
        await http.delete(f"{base}/auth/v1/admin/users/{user_id}", headers=_admin_headers())


async def _real_user(email: str) -> UUID:
    """A confirmed user at the real Supabase Auth, with PASSWORD."""
    base = app_settings.supabase_url.rstrip("/")
    async with httpx.AsyncClient() as http:
        created = await http.post(
            f"{base}/auth/v1/admin/users",
            headers=_admin_headers(),
            json={"email": email, "password": PASSWORD, "email_confirm": True},
        )
        created.raise_for_status()
    return UUID(created.json()["id"])


def _totp(secret: str) -> str:
    import pyotp

    return pyotp.TOTP(secret).now()


@needs_auth
@needs_mailpit
async def test_real_auth_register_then_enrol_an_authenticator(client, owner_db):
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

        wrong = await _verify(client, email, challenge, wrong_code)
        enrol = await _verify(client, email, challenge, code)

        assert wrong.status_code >= 400
        assert enrol.status_code == 200, enrol.text
        step = enrol.json()
        assert step["step"] == "enrol"
        assert step["qr_code"].lstrip().startswith(("<?xml", "<svg"))
        assert step["uri"].startswith("otpauth://totp/")
        right = await _verify(client, email, step["challenge"], _totp(step["secret"]))
        assert right.status_code == 200, right.text
        token = right.json()["access_token"]
        assert jwt.decode(token, options={"verify_signature": False})["aal"] == "aal2"
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
async def test_real_auth_sign_in_enrols_then_asks_for_the_code(client, owner_db, make_account):
    email = _unique_email()
    user_id = await _real_user(email)
    try:
        first = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert first.status_code == 200, first.text
        assert first.json()["step"] == "enrol"
        secret = first.json()["secret"]

        wrong = await _verify(client, email, first.json()["challenge"], "000000")
        assert wrong.status_code == 403
        assert wrong.json()["detail"]["code"] == "totp_invalid"
        enrolled = await _verify(client, email, first.json()["challenge"], _totp(secret))
        assert enrolled.status_code == 200, enrolled.text
        me = await client.get("/api/me", headers=_bearer(enrolled.json()))
        assert me.status_code == 200, me.text

        second = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert second.json()["step"] == "totp"
        totp = await _verify(client, email, second.json()["challenge"], _totp(secret))
        assert totp.status_code == 200, totp.text

        # A lost authenticator: an administrator resets it, and the next
        # sign-in enrols again.
        admin = await make_account(role="administrator")
        reset = await client.post(
            f"/api/accounts/{user_id}/second-factor/reset",
            json={"reason": "Phone lost"},
            headers=auth_header(admin),
        )
        assert reset.status_code == 200, reset.text
        assert (await client.get("/api/me", headers=_bearer(totp.json()))).status_code == 401
        third = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert third.json()["step"] == "enrol"
    finally:
        await _remove(owner_db, user_id)


@needs_auth
async def test_real_auth_refresh_keeps_the_second_factor_and_logout_ends_it(client, owner_db):
    """GoTrue keeps the session id and aal2 on a refresh; the backend's
    logout ends the session at GoTrue, so its refresh token stops working."""
    email = _unique_email()
    user_id = await _real_user(email)
    try:
        first = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert first.status_code == 200, first.text
        signed_in = await _verify(
            client, email, first.json()["challenge"], _totp(first.json()["secret"])
        )
        assert signed_in.status_code == 200, signed_in.text
        session = signed_in.json()

        res = await _refresh(client, session["refresh_token"])

        assert res.status_code == 200, res.text
        renewed = res.json()
        claims = jwt.decode(renewed["access_token"], options={"verify_signature": False})
        assert claims["aal"] == "aal2"
        assert claims["session_id"] == _session_id(session)
        assert (await client.get("/api/me", headers=_bearer(renewed))).status_code == 200

        out = await client.post("/api/auth/logout", headers=_bearer(renewed))
        assert out.status_code == 204
        again = await _refresh(client, renewed["refresh_token"])
        assert again.status_code == 401
        assert len(await _refusals_for(owner_db, again)) == 1
    finally:
        await _remove(owner_db, user_id)


@needs_auth
async def test_real_auth_a_session_made_without_the_proxy_does_not_get_in(client, owner_db):
    import pyotp

    base = app_settings.supabase_url.rstrip("/")
    public = {"apikey": app_settings.supabase_anon_key or app_settings.supabase_service_role_key}
    email = _unique_email()
    user_id = await _real_user(email)
    try:
        async with httpx.AsyncClient(base_url=f"{base}/auth/v1") as http:
            # Straight to Supabase Auth with the public key: a password alone.
            grant = await http.post(
                "/token", params={"grant_type": "password"}, headers=public,
                json={"email": email, "password": PASSWORD},
            )
            assert grant.status_code == 200, grant.text
            aal1 = grant.json()["access_token"]

            me = await client.get("/api/me", headers={"Authorization": f"Bearer {aal1}"})
            assert me.status_code == 401
            assert me.json()["detail"]["code"] == "second_factor_missing"

            # Even with a TOTP factor verified directly, the proxy never saw it.
            user = {**public, "Authorization": f"Bearer {aal1}"}
            factor = (await http.post("/factors", headers=user, json={"factor_type": "totp"})).json()
            challenge = (await http.post(f"/factors/{factor['id']}/challenge", headers=user)).json()
            verified = await http.post(
                f"/factors/{factor['id']}/verify", headers=user,
                json={"challenge_id": challenge["id"], "code": pyotp.TOTP(factor["totp"]["secret"]).now()},
            )
            assert verified.status_code == 200, verified.text
            aal2 = verified.json()["access_token"]

            me = await client.get("/api/me", headers={"Authorization": f"Bearer {aal2}"})
            assert me.status_code == 401
            assert me.json()["detail"]["code"] == "session_not_verified"
    finally:
        await _remove(owner_db, user_id)


async def _wait_for_code(email: str) -> str:
    """The code of the only e-mail to `email`, once Mailpit has it."""
    import asyncio

    for _ in range(50):
        async with httpx.AsyncClient(base_url=MAILPIT_URL) as http:
            found = await http.get("/api/v1/search", params={"query": f'to:"{email}"'})
        if found.json()["messages"]:
            return await _code_from_mailpit(email)
        await asyncio.sleep(0.2)
    raise AssertionError(f"no e-mail to {email}")


async def _real_user_with_authenticator(client, email: str) -> tuple[UUID, str]:
    """A real user who signed in once through the proxy and so enrolled an
    authenticator; returns its id and the TOTP secret."""
    user_id = await _real_user(email)
    first = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert first.json()["step"] == "enrol", first.text
    secret = first.json()["secret"]
    enrolled = await _verify(client, email, first.json()["challenge"], _totp(secret))
    assert enrolled.status_code == 200, enrolled.text
    return user_id, secret


async def _real_reset(client, email: str, **extra):
    forgot = await client.post("/api/auth/password/forgot", json={"email": email})
    assert forgot.status_code == 200, forgot.text
    code = await _wait_for_code(email)
    return await client.post(
        "/api/auth/password/reset",
        json={"email": email, "code": code, "password": NEW_PASSWORD, **extra},
    )


NEW_PASSWORD = "lighthouse-keeper-7"


@needs_auth
@needs_mailpit
async def test_real_auth_reset_with_the_authenticator_then_sign_in(client, owner_db, pwned):
    email = _unique_email()
    user_id, secret = await _real_user_with_authenticator(client, email)
    try:
        res = await _real_reset(client, email, totp=_totp(secret))

        assert res.status_code == 200, res.text
        [rec] = await _records(owner_db, "password_reset", email)
        assert rec["outcome"] == "succeeded"
        old = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert old.status_code == 400
        new = await client.post(
            "/api/auth/login", json={"email": email, "password": NEW_PASSWORD}
        )
        assert new.status_code == 200, new.text
        assert new.json()["step"] == "totp"
        signed_in = await _verify(client, email, new.json()["challenge"], _totp(secret))
        assert signed_in.status_code == 200, signed_in.text
        me = await client.get("/api/me", headers=_bearer(signed_in.json()))
        assert me.status_code == 200, me.text
    finally:
        await _remove(owner_db, user_id)


@needs_auth
@needs_mailpit
@pytest.mark.parametrize(
    ("totp", "status_code", "code"),
    [(None, 400, "totp_required"), ("000000", 403, "totp_invalid")],
)
async def test_real_auth_a_reset_needs_the_right_authenticator_code(
    client, owner_db, pwned, totp, status_code, code
):
    email = _unique_email()
    user_id, secret = await _real_user_with_authenticator(client, email)
    try:
        if totp == _totp(secret):
            totp = "111111"
        res = await _real_reset(client, email, **({"totp": totp} if totp else {}))

        assert res.status_code == status_code, res.text
        assert res.json()["detail"]["code"] == code
        [rec] = await _records(owner_db, "password_reset", email)
        assert (rec["outcome"], rec["reason"]) == ("refused", code)
        # The password is unchanged.
        old = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert old.status_code == 200, old.text
    finally:
        await _remove(owner_db, user_id)
