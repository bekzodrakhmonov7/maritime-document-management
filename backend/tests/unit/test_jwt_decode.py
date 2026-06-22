from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest

from app.config import settings
from app.deps import get_current_user
from app.models.auth import UserPayload


@pytest.fixture
def valid_token() -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid4()),
        "email": "test@example.com",
        "role": "admin",
        "aud": "authenticated",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")


@pytest.fixture
def expired_token() -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid4()),
        "email": "test@example.com",
        "role": "admin",
        "aud": "authenticated",
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
    }
    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")


@pytest.fixture
def wrong_audience_token() -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid4()),
        "email": "test@example.com",
        "role": "admin",
        "aud": "wrong-audience",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")


class DummyRequest:
    def __init__(self, token: str | None = None):
        self.headers = {}
        if token:
            self.headers["authorization"] = f"Bearer {token}"


class MockConn:
    async def fetchrow(self, query, *args):
        return None


@pytest.mark.asyncio
async def test_valid_token_decodes(valid_token: str) -> None:
    request = DummyRequest(valid_token)
    user = await get_current_user(request, MockConn())
    assert isinstance(user, UserPayload)
    assert user.email == "test@example.com"
    assert user.role == "admin"


@pytest.mark.asyncio
async def test_expired_token_rejected(expired_token: str) -> None:
    from fastapi import HTTPException

    request = DummyRequest(expired_token)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, MockConn())
    assert exc_info.value.status_code == 401
    assert "expired" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_wrong_audience_rejected(wrong_audience_token: str) -> None:
    from fastapi import HTTPException

    request = DummyRequest(wrong_audience_token)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, MockConn())
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_malformed_token_rejected() -> None:
    from fastapi import HTTPException

    request = DummyRequest("not-a-valid-jwt")
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, MockConn())
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_header_rejected() -> None:
    from fastapi import HTTPException

    request = DummyRequest(None)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, MockConn())
    assert exc_info.value.status_code == 401


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def __init__(self, public_key):
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._public_key)


def _generate_es256_keypair():
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, private_key.public_key()


@pytest.fixture
def es256_keypair():
    return _generate_es256_keypair()


def _build_es256_token(private_key, *, sub: str, aud: str = "authenticated", email: str = "es256@test.com", exp_delta: timedelta = timedelta(hours=1)):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "email": email,
        "role": "authenticated",
        "aud": aud,
        "iat": now,
        "exp": now + exp_delta,
    }
    return jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": "test-kid"})


@pytest.mark.asyncio
async def test_es256_token_decodes(es256_keypair, monkeypatch) -> None:
    import app.deps

    private_key, public_key = es256_keypair
    sub = str(uuid4())
    token = _build_es256_token(private_key, sub=sub, email="es256@test.com")

    monkeypatch.setattr(app.deps, "_jwks_client", lambda: _FakeJWKSClient(public_key))

    request = DummyRequest(token)
    user = await get_current_user(request, MockConn())
    assert isinstance(user, UserPayload)
    assert user.email == "es256@test.com"
    assert user.role == "authenticated"
    assert str(user.sub) == sub


@pytest.mark.asyncio
async def test_es256_expired_token_rejected(es256_keypair, monkeypatch) -> None:
    from fastapi import HTTPException

    import app.deps

    private_key, public_key = es256_keypair
    token = _build_es256_token(
        private_key,
        sub=str(uuid4()),
        exp_delta=timedelta(hours=-1),
    )

    monkeypatch.setattr(app.deps, "_jwks_client", lambda: _FakeJWKSClient(public_key))

    request = DummyRequest(token)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, MockConn())
    assert exc_info.value.status_code == 401
    assert "expired" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_es256_wrong_audience_rejected(es256_keypair, monkeypatch) -> None:
    from fastapi import HTTPException

    import app.deps

    private_key, public_key = es256_keypair
    token = _build_es256_token(private_key, sub=str(uuid4()), aud="wrong-audience")

    monkeypatch.setattr(app.deps, "_jwks_client", lambda: _FakeJWKSClient(public_key))

    request = DummyRequest(token)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, MockConn())
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_unsupported_alg_rejected() -> None:
    from fastapi import HTTPException

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid4()),
        "email": "none@test.com",
        "role": "authenticated",
        "aud": "authenticated",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    token = jwt.encode(payload, "any-secret", algorithm="HS384", headers={"kid": "test-kid"})

    request = DummyRequest(token)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, MockConn())
    assert exc_info.value.status_code == 401
