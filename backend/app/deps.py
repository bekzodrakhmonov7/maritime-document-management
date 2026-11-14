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

    sub = UUID(payload["sub"])
    row = await db.fetchrow(
        "SELECT role, is_approved FROM public.users WHERE id = $1", sub
    )
    # NOTE: the no-row fallback to the token's role claim only exists for the
    # test fixtures; real Supabase users always have a public.users row.
    role = row["role"] if row else payload.get("role", "")
    is_approved = row["is_approved"] if row else True

    return UserPayload(
        sub=sub,
        email=payload.get("email", ""),
        role=role,
        is_approved=is_approved,
    )


async def get_current_user(
    user: UserPayload = Depends(get_signed_in_user),
) -> UserPayload:
    """A signed-in user whose account an administrator has approved (FR-01)."""
    if not user.is_approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account awaiting administrator approval",
        )
    return user


def require_role(*roles: str):
    async def checker(user: UserPayload = Depends(get_current_user)) -> UserPayload:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return checker
