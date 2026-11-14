from functools import lru_cache
from typing import AsyncGenerator
from uuid import UUID

import asyncpg
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from jwt import PyJWKClient

from app.config import settings
from app.models.auth import UserPayload

security = HTTPBearer(auto_error=False)


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
    auth_header = request.headers.get("authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    token = parts[1]

    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    alg = header.get("alg")

    if alg == "ES256":
        try:
            signing_key = _jwks_client().get_signing_key_from_jwt(token)
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        key = signing_key.key
        algorithms = ["ES256"]
    elif alg == "HS256":
        key = settings.supabase_jwt_secret
        algorithms = ["HS256"]
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    try:
        sub = UUID(str(payload.get("sub")))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    # Remembered for the refused-access record (app/refused_access.py).
    request.state.token_sub = sub

    # The Account row is the only source of status and role: the token's role
    # claim is never trusted, and a token with no row is refused.
    row = await db.fetchrow(
        "SELECT email, full_name, status, role FROM public.users WHERE id = $1", sub
    )
    if row is None:
        raise account_refused("no_account", "There is no account for this sign-in.")

    request.state.account = UserPayload(
        sub=sub,
        email=row["email"],
        full_name=row["full_name"],
        status=row["status"],
        role=row["role"],
    )
    return request.state.account


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
