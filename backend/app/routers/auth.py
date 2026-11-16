"""The sign-in proxy (Sign-in Codes) and logout (R1, T7, ADR 0002, ADR 0004).

Every sign-in step goes through here so failed attempts reach the Audit Log:

- `POST /api/auth/register` asks Supabase Auth to e-mail a Sign-in Code and
  lets it create the Account (with its full name); an e-mail that already has
  an Account just gets a code.
- `POST /api/auth/code` asks for a code and never creates an Account. A code
  asked for an unknown e-mail is recorded as *Login failed*
  (`unknown_email`), but both endpoints answer every e-mail with the same 200,
  rate limits included, so the answer never reveals whether an Account exists.
- `POST /api/auth/verify` checks the code and returns Supabase's session for
  `setSession`; a refused code is recorded with Supabase's error code.

Supabase Auth being unreachable is a recorded failure and a 503. *Login
succeeded* is not written here: a trigger copies it from Supabase's own auth
audit table, so sign-ins that skip this proxy are recorded too.
"""

from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, StringConstraints

from app import audit
from app.audit import AuditAction, audit_context_for, client_ip, request_audit_context
from app.deps import get_account, get_db
from app.models.auth import UserPayload
from app.supabase_auth import (
    AuthUnavailable,
    SignInRefused,
    SupabaseAuth,
    get_supabase_auth,
)

router = APIRouter(prefix="/auth", tags=["auth"])

Email = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=320)]

# Supabase answers a code request for an unknown e-mail (with create_user off)
# with 422 `otp_disabled`.
UNKNOWN_EMAIL = "otp_disabled"

CODE_SENT = {"message": "If an Account exists for this e-mail, we've sent a code."}


class CodeRequest(BaseModel):
    email: Email


class RegisterRequest(BaseModel):
    email: Email
    full_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


class VerifyRequest(BaseModel):
    email: Email
    code: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{6}$")]


@router.post("/register")
async def register(
    body: RegisterRequest,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    supabase_auth: SupabaseAuth = Depends(get_supabase_auth),
) -> dict[str, str]:
    """E-mail a Sign-in Code, creating the (pending) Account if there is none."""
    return await _send_code(db, request, supabase_auth, body.email, body.full_name)


@router.post("/code")
async def send_code(
    body: CodeRequest,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    supabase_auth: SupabaseAuth = Depends(get_supabase_auth),
) -> dict[str, str]:
    """E-mail a Sign-in Code to an existing Account. Never creates one."""
    return await _send_code(db, request, supabase_auth, body.email, full_name=None)


async def _send_code(
    db: asyncpg.Connection,
    request: Request,
    supabase_auth: SupabaseAuth,
    email: str,
    full_name: str | None,
) -> dict[str, str]:
    """Same 200 for every e-mail; only an unreachable Supabase Auth shows."""
    create = full_name is not None
    try:
        await supabase_auth.send_code(email, create, full_name, client_ip(request))
    except SignInRefused as exc:
        reason = "unknown_email" if not create and exc.code == UNKNOWN_EMAIL else exc.code
        await _record_failure(db, request, email, reason)
    except AuthUnavailable:
        await _record_failure(db, request, email, AuthUnavailable.code)
        raise _unavailable()
    return CODE_SENT


@router.post("/verify")
async def verify(
    body: VerifyRequest,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    supabase_auth: SupabaseAuth = Depends(get_supabase_auth),
) -> dict[str, Any]:
    """Check the Sign-in Code and return Supabase's session for `setSession`."""
    try:
        return await supabase_auth.verify_code(body.email, body.code, client_ip(request))
    except SignInRefused as exc:
        await _record_failure(db, request, body.email, exc.code)
        raise HTTPException(exc.status_code, {"code": exc.code, "message": exc.message})
    except AuthUnavailable:
        await _record_failure(db, request, body.email, AuthUnavailable.code)
        raise _unavailable()


def _unavailable() -> HTTPException:
    return HTTPException(
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
