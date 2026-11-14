"""Sign-in proxy and logout (R1, T7, ADR 0002).

Sign-in goes through here so failed attempts reach the Audit Log, including
attempts on e-mails that have no Account. *Login succeeded* is not written
here: a trigger copies it from Supabase's own auth audit table, so sign-ins
that skip this endpoint are recorded too.
"""

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app import audit
from app.audit import AuditAction, audit_context_for, client_ip, request_audit_context
from app.deps import get_account, get_db
from app.models.auth import UserPayload
from app.supabase_auth import AuthUnavailable, SignInRefused, SupabaseAuth, get_supabase_auth

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    supabase_auth: SupabaseAuth = Depends(get_supabase_auth),
) -> dict[str, Any]:
    """Sign in with Supabase Auth and return its session for `setSession`."""
    email = body.email.strip()
    try:
        return await supabase_auth.sign_in_with_password(email, body.password, client_ip(request))
    except SignInRefused as exc:
        await _record_failure(db, request, email, exc.code)
        raise HTTPException(exc.status_code, {"code": exc.code, "message": exc.message})
    except AuthUnavailable:
        await _record_failure(db, request, email, AuthUnavailable.code)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {"code": AuthUnavailable.code, "message": "Sign-in is unavailable. Try again later."},
        )


async def _record_failure(
    db: asyncpg.Connection, request: Request, email: str, error_code: str
) -> None:
    """*Login failed* with the typed e-mail and the error code. The actor is
    the Account with that e-mail, or none when the e-mail is unknown."""
    account = await db.fetchrow(
        "SELECT id, role FROM public.users WHERE lower(email) = lower($1)", email
    )
    actor_id = account["id"] if account else None
    actor_role = account["role"] if account else None
    ctx = request_audit_context(request, actor_id, email, actor_role)
    async with db.transaction():
        await audit.record(
            db, ctx, AuditAction.LOGIN_FAILED,
            target_type="account" if actor_id else None,
            target_id=actor_id,
            reason=error_code,
            outcome="refused",
        )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    user: UserPayload = Depends(get_account),
) -> Response:
    """Record *logout*. The frontend ends the Supabase session itself."""
    async with db.transaction():
        await audit.record(
            db, audit_context_for(request, user), AuditAction.LOGOUT,
            target_type="account", target_id=user.sub,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
