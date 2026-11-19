"""Attempts with an invalid Session reach the Audit Log (ADR-0006, FR-22).

A refused Session writes one *access refused* record, through the same
handler as other refusals. The visitor sees the same 401 as before.
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest

from app import refused_access
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


def _forged_headers(real_account) -> dict[str, dict[str, str]]:
    def bearer(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    # A real Account's id inside a forged Session must not become the actor.
    sub = str(real_account)
    return {
        "wrong secret": bearer(jwt.encode(_claims(sub=sub), "not-the-secret-" * 3, "HS256")),
        "garbage": bearer("not-a-jwt"),
        "unsupported algorithm": bearer(jwt.encode(_claims(sub=sub), "x" * 64, "HS384")),
        "not bearer": {"Authorization": f"Token {make_token(real_account)}"},
        "bearer with two values": {"Authorization": "Bearer one two"},
        "wrong audience": bearer(
            jwt.encode(_claims(sub=sub, aud="elsewhere"), settings.supabase_jwt_secret, "HS256")
        ),
        "no subject": bearer(
            jwt.encode(_claims(sub=None), settings.supabase_jwt_secret, "HS256")
        ),
        "unusable subject": bearer(
            jwt.encode(_claims(sub="not-a-uuid"), settings.supabase_jwt_secret, "HS256")
        ),
    }


FORGED = [
    ("wrong secret", "Invalid token"),
    ("garbage", "Invalid token"),
    ("unsupported algorithm", "Invalid token"),
    ("not bearer", "Invalid authorization header format"),
    ("bearer with two values", "Invalid authorization header format"),
    ("wrong audience", "Invalid token"),
    ("no subject", "Invalid token"),
    ("unusable subject", "Invalid token"),
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
    assert rec["outcome"] == "refused"
    assert rec["actor_id"] is None
    assert rec["actor_email"] is None
    assert rec["actor_role"] is None
    assert rec["target_type"] == "request"
    assert rec["target_id"] == "GET /api/me"
    assert str(rec["ip"]) == "127.0.0.1"
    # No part of the Session is kept.
    token = headers["Authorization"].split()[-1]
    assert token not in " ".join(str(v) for v in rec.values())


async def test_no_authorization_header_writes_nothing(client, owner_db):
    res = await client.get("/api/me")

    assert res.status_code == 401
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
        res = await client.get("/api/me", headers={"Authorization": "Bearer not-a-jwt"})

    assert res.status_code == 401
    assert res.json() == {"detail": "Invalid token"}
    assert "Refused access could not be recorded" in caplog.text
