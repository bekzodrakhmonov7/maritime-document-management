from functools import lru_cache
from typing import AsyncGenerator, NoReturn
from uuid import UUID

import asyncpg
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from jwt import PyJWKClient
from jwt.algorithms import AllowedPublicKeys

from app.config import settings
from app.models.auth import UserPayload

security = HTTPBearer(auto_error=False)

# A Session without these is refused: it would never expire, name no one
# or be meant for another audience (SR-01).
REQUIRED_CLAIMS = ["exp", "sub", "aud"]


class SessionRefused(HTTPException):
    """A Session refused with a 401, recorded as refused access (ADR-0006).
    The actor fields are set only when the signature checked out."""

    def __init__(
        self,
        reason: str,
        detail: object,
        *,
        account_id: UUID | None = None,
        email: str | None = None,
        role: str | None = None,
    ) -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail)
        self.reason = reason
        self.account_id = account_id
        self.email = email
        self.role = role


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    base = settings.supabase_url.rstrip("/")
    return PyJWKClient(f"{base}/auth/v1/.well-known/jwks.json")


async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    from app.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def get_signed_in_user(
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
) -> UserPayload:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise SessionRefused("invalid_session", "Invalid authorization header format")

    token = parts[1]

    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        raise SessionRefused("invalid_session", "Invalid token")

    alg = header.get("alg")

    if alg == "ES256":
        # Errors fetching our key set (down, no usable keys) are a server
        # fault and propagate; only a kid matching none of our keys is the visitor's.
        keys = _jwks_client()
        kid = header.get("kid")
        signing_key = keys.match_kid(keys.get_signing_keys(), kid) or keys.match_kid(
            keys.get_signing_keys(refresh=True), kid
        )
        if signing_key is None:
            raise SessionRefused("invalid_session", "Invalid token")
        key = signing_key.key
        algorithms = ["ES256"]
    elif alg == "HS256":
        key = settings.supabase_jwt_secret
        algorithms = ["HS256"]
    else:
        raise SessionRefused("invalid_session", "Invalid token")

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience="authenticated",
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.ExpiredSignatureError:
        raise await _refuse_expired(token, key, algorithms, db)
    except jwt.InvalidTokenError:
        raise SessionRefused("invalid_session", "Invalid token")

    try:
        sub = UUID(str(payload.get("sub")))
    except ValueError:
        raise SessionRefused("invalid_session", "Invalid token")

    try:
        session_id = UUID(str(payload.get("session_id")))
    except ValueError:
        session_id = None

    # Remembered for the refused-access record (app/refused_access.py).
    request.state.token_sub = sub
    request.state.session_id = session_id

    # The Account row is the only source of status and role: the token's role
    # claim is never trusted, and a token with no row is refused.
    row = await db.fetchrow(
        """
        SELECT u.email, u.full_name, u.status, u.role,
               EXISTS (SELECT 1 FROM public.verified_session AS v
                        WHERE v.session_id = $2 AND v.user_id = u.id) AS verified
          FROM public.users AS u
         WHERE u.id = $1
        """,
        sub,
        session_id,
    )
    if row is None:
        raise account_refused("no_account", "There is no account for this sign-in.")

    # Only a session that passed the second factor gets in (SR-03, ADR 0007):
    # Supabase Auth marks it aal2 once a TOTP code was verified. A token
    # without `aal` counts as aal1.
    if payload.get("aal") != "aal2":
        raise SessionRefused(
            "second_factor_missing",
            {
                "code": "second_factor_missing",
                "message": "Sign in again with your password and authenticator code.",
            },
            account_id=sub,
            email=row["email"],
            role=row["role"],
        )

    # Supabase Auth hands out a session to anyone holding the public key who
    # goes to it directly. Only a session that passed both steps of the
    # sign-in proxy gets in (ADR 0005, ADR 0007).
    if not row["verified"]:
        raise SessionRefused(
            "session_not_verified",
            {
                "code": "session_not_verified",
                "message": "Sign in again with your password and authenticator code.",
            },
            account_id=sub,
            email=row["email"],
            role=row["role"],
        )

    request.state.account = UserPayload(
        sub=sub,
        email=row["email"],
        full_name=row["full_name"],
        status=row["status"],
        role=row["role"],
    )
    return request.state.account


async def _refuse_expired(
    token: str, key: str | AllowedPublicKeys, algorithms: list[str], db: asyncpg.Connection
) -> NoReturn:
    """Refuse a genuine but expired Session, naming the Account it is for.
    Everything but the expiry is checked again, so a forged one stays invalid."""
    try:
        payload = jwt.decode(
            token, key, algorithms=algorithms, audience="authenticated",
            options={"verify_exp": False, "require": REQUIRED_CLAIMS},
        )
        sub = UUID(str(payload.get("sub")))
    except (jwt.InvalidTokenError, ValueError):
        raise SessionRefused("invalid_session", "Invalid token")
    row = await db.fetchrow("SELECT email, role FROM public.users WHERE id = $1", sub)
    raise SessionRefused(
        "session_expired", "Token has expired", account_id=sub,
        email=row["email"] if row else None, role=row["role"] if row else None,
    )


def account_refused(code: str, message: str) -> HTTPException:
    """A 403 whose `detail.code` the frontend can act on."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": code, "message": message},
    )


def _refuse_deactivated(user: UserPayload) -> None:
    if user.status == "deactivated":
        raise account_refused(
            "account_deactivated", "Your account has been switched off."
        )


async def get_account(
    user: UserPayload = Depends(get_signed_in_user),
) -> UserPayload:
    """Any Account that is not switched off, pending ones included (for /me)."""
    _refuse_deactivated(user)
    return user


async def get_current_user(
    user: UserPayload = Depends(get_signed_in_user),
) -> UserPayload:
    """An active Account. Pending and deactivated ones get 403 on every request,
    so switching someone off takes effect on their next request (FR-02)."""
    _refuse_deactivated(user)
    if user.status != "active":
        raise account_refused(
            "account_pending", "Your account is waiting for administrator approval."
        )
    return user


def require_role(*roles: str):
    async def checker(user: UserPayload = Depends(get_current_user)) -> UserPayload:
        if user.role not in roles:
            raise account_refused("wrong_role", "You don't have permission to do this.")
        return user

    return checker
