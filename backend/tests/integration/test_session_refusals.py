"""Attempts with an invalid Session reach the Audit Log (ADR-0006, FR-22).

A refused Session writes one *access refused* record, through the same
handler as other refusals. The visitor sees the same 401 as before.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient
from jwt import PyJWKClient, PyJWKClientConnectionError
from jwt.algorithms import ECAlgorithm

from app import deps, refused_access
from app.config import settings
from tests.conftest import auth_header, make_token


def _claims(**overrides) -> dict:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(uuid4()),
        "session_id": str(uuid4()),
        "aud": "authenticated",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


async def _refusals_for(owner_db, res) -> list[dict]:
    rows = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE action = 'access_refused' AND request_id = $1",
        res.headers["x-request-id"],
    )
    return [dict(r) for r in rows]


def _expired(**overrides) -> dict:
    now = datetime.now(timezone.utc)
    return _claims(**{"iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1), **overrides})


def _hs256(claims: dict, key: str | None = None) -> str:
    return jwt.encode(claims, key or settings.supabase_jwt_secret, "HS256")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_request_target(rec) -> None:
    assert rec["outcome"] == "refused"
    assert rec["target_type"] == "request"
    assert rec["target_id"] == "GET /api/me"
    assert str(rec["ip"]) == "127.0.0.1"


def _assert_token_not_kept(rec, headers: dict[str, str]) -> None:
    token = headers["Authorization"].split()[-1]
    assert token not in " ".join(str(v) for v in rec.values())


def _forged_headers(real_account) -> dict[str, dict[str, str]]:
    # A real Account's id inside a forged Session must not become the actor.
    sub = str(real_account)
    return {
        "wrong secret": _bearer(_hs256(_claims(sub=sub), "not-the-secret-" * 3)),
        "garbage": _bearer("not-a-jwt"),
        "unsupported algorithm": _bearer(jwt.encode(_claims(sub=sub), "x" * 64, "HS384")),
        "none algorithm": _bearer(jwt.encode(_claims(sub=sub), None, "none")),
        "not bearer": {"Authorization": f"Token {make_token(real_account)}"},
        "bearer with two values": {"Authorization": "Bearer one two"},
        "wrong audience": _bearer(_hs256(_claims(sub=sub, aud="elsewhere"))),
        "no subject": _bearer(_hs256(_claims(sub=None))),
        "unusable subject": _bearer(_hs256(_claims(sub="not-a-uuid"))),
        "no expiry": _bearer(_hs256(_claims(sub=sub, session_id=sub, exp=None))),
        "no audience": _bearer(_hs256(_claims(sub=sub, aud=None))),
    }


FORGED = [
    ("wrong secret", "Invalid token"),
    ("garbage", "Invalid token"),
    ("unsupported algorithm", "Invalid token"),
    ("none algorithm", "Invalid token"),
    ("not bearer", "Invalid authorization header format"),
    ("bearer with two values", "Invalid authorization header format"),
    ("wrong audience", "Invalid token"),
    ("no subject", "Invalid token"),
    ("unusable subject", "Invalid token"),
    ("no expiry", "Invalid token"),
    ("no audience", "Invalid token"),
]


@pytest.mark.parametrize("case, detail", FORGED)
async def test_a_forged_session_is_recorded_as_invalid_session(
    client, owner_db, make_account, case, detail
):
    account = await make_account()
    headers = _forged_headers(account)[case]

    res = await client.get("/api/me", headers=headers)

    assert res.status_code == 401
    assert res.json() == {"detail": detail}
    [rec] = await _refusals_for(owner_db, res)
    assert rec["reason"] == "invalid_session"
    assert rec["actor_id"] is None
    assert rec["actor_email"] is None
    assert rec["actor_role"] is None
    _assert_request_target(rec)
    _assert_token_not_kept(rec, headers)


@pytest.mark.parametrize("headers", [{}, {"Authorization": ""}, {"Authorization": "   "}])
async def test_a_missing_or_empty_authorization_header_writes_nothing(client, owner_db, headers):
    res = await client.get("/api/me", headers=headers)

    assert res.status_code == 401
    assert res.json() == {"detail": "Missing authorization header"}
    assert await _refusals_for(owner_db, res) == []


async def test_a_verified_session_writes_no_refusal(client, owner_db, make_account):
    account = await make_account()

    res = await client.get("/api/me", headers=auth_header(account))

    assert res.status_code == 200
    assert await _refusals_for(owner_db, res) == []


async def test_a_record_that_cannot_be_written_still_refuses_and_is_logged(
    client, owner_db, monkeypatch, caplog
):
    async def broken(*args, **kwargs):
        raise RuntimeError("audit log unavailable")

    monkeypatch.setattr(refused_access.audit, "record", broken)

    with caplog.at_level(logging.ERROR, logger="app.refused_access"):
        res = await client.get("/api/me", headers=_bearer("not-a-jwt"))

    assert res.status_code == 401
    assert res.json() == {"detail": "Invalid token"}
    assert "Refused access could not be recorded" in caplog.text


async def test_an_expired_session_is_recorded_with_its_account(
    client, owner_db, make_account
):
    account = await make_account(role="crewing_officer")
    headers = _bearer(_hs256(_expired(sub=str(account))))

    res = await client.get("/api/me", headers=headers)

    assert res.status_code == 401
    assert res.json() == {"detail": "Token has expired"}
    [rec] = await _refusals_for(owner_db, res)
    assert rec["reason"] == "session_expired"
    assert rec["actor_id"] == account
    email = await owner_db.fetchval("SELECT email FROM public.users WHERE id = $1", account)
    assert rec["actor_email"] == email
    assert rec["actor_role"] == "crewing_officer"
    _assert_request_target(rec)
    _assert_token_not_kept(rec, headers)


async def test_an_expired_session_without_an_account_names_only_its_subject(client, owner_db):
    sub = uuid4()

    res = await client.get("/api/me", headers=_bearer(_hs256(_expired(sub=str(sub)))))

    assert res.status_code == 401
    assert res.json() == {"detail": "Token has expired"}
    [rec] = await _refusals_for(owner_db, res)
    assert rec["reason"] == "session_expired"
    assert rec["actor_id"] == sub
    assert rec["actor_email"] is None
    assert rec["actor_role"] is None
    _assert_request_target(rec)


@pytest.mark.parametrize(
    "case", ["unusable subject", "no subject", "wrong key", "wrong audience"]
)
async def test_an_expired_but_otherwise_bad_session_is_an_invalid_session(
    client, owner_db, make_account, case
):
    account = await make_account()
    headers = {
        "unusable subject": _bearer(_hs256(_expired(sub="not-a-uuid"))),
        "no subject": _bearer(_hs256(_expired(sub=None))),
        "wrong key": _bearer(_hs256(_expired(sub=str(account)), "not-the-secret-" * 3)),
        "wrong audience": _bearer(_hs256(_expired(sub=str(account), aud="elsewhere"))),
    }[case]

    res = await client.get("/api/me", headers=headers)

    assert res.status_code == 401
    [rec] = await _refusals_for(owner_db, res)
    assert rec["reason"] == "invalid_session"
    assert rec["actor_id"] is None
    assert rec["actor_email"] is None
    assert rec["actor_role"] is None
    _assert_request_target(rec)


async def test_a_session_that_skipped_a_sign_in_step_is_recorded_with_its_account(
    client, owner_db, make_account
):
    account = await make_account(role="crewing_officer")
    email = await owner_db.fetchval("SELECT email FROM public.users WHERE id = $1", account)
    headers = _bearer(make_token(account, session_id=uuid4()))

    res = await client.get("/api/me", headers=headers)

    assert res.status_code == 401
    assert res.json() == {
        "detail": {
            "code": "session_not_verified",
            "message": "Sign in again with your password and e-mailed code.",
        }
    }
    [rec] = await _refusals_for(owner_db, res)
    assert rec["reason"] == "session_not_verified"
    assert rec["actor_id"] == account
    assert rec["actor_email"] == email
    assert rec["actor_role"] == "crewing_officer"
    _assert_request_target(rec)
    _assert_token_not_kept(rec, headers)


def _stub_signing_keys(monkeypatch, fetch=None):
    """The project's key endpoint, stubbed: it publishes one ES256 key, not the signer's."""
    public = ec.generate_private_key(ec.SECP256R1()).public_key()
    jwks = {"keys": [{**json.loads(ECAlgorithm.to_jwk(public)), "kid": "published-kid"}]}
    keys = PyJWKClient("http://keys.invalid/jwks.json", cache_jwk_set=False)
    monkeypatch.setattr(keys, "fetch_data", fetch or (lambda: jwks))
    monkeypatch.setattr(deps, "_jwks_client", lambda: keys)


def _es256_session(account) -> dict[str, str]:
    token = jwt.encode(
        _claims(sub=str(account)), ec.generate_private_key(ec.SECP256R1()), "ES256",
        headers={"kid": "unknown-kid"},
    )
    return _bearer(token)


async def test_a_session_under_an_unknown_es256_key_is_recorded_as_invalid_session(
    client, owner_db, make_account, monkeypatch
):
    account = await make_account()
    _stub_signing_keys(monkeypatch)

    res = await client.get("/api/me", headers=_es256_session(account))

    assert res.status_code == 401
    assert res.json() == {"detail": "Invalid token"}
    [rec] = await _refusals_for(owner_db, res)
    assert rec["reason"] == "invalid_session"
    assert rec["actor_id"] is None


def _unreachable():
    raise PyJWKClientConnectionError("Fail to fetch data from the url")


def _no_signing_keys():
    public = ec.generate_private_key(ec.SECP256R1()).public_key()
    return {"keys": [json.loads(ECAlgorithm.to_jwk(public))]}  # no kid: unusable


@pytest.mark.parametrize("fetch", [_unreachable, _no_signing_keys])
async def test_broken_signing_keys_are_not_the_visitors_fault(
    app, make_account, monkeypatch, fetch
):
    recorded = []

    async def record(*args, **kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(refused_access.audit, "record", record)
    account = await make_account()
    _stub_signing_keys(monkeypatch, fetch=fetch)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        res = await c.get("/api/me", headers=_es256_session(account))

    assert res.status_code == 500
    assert recorded == []
