"""The sign-in proxy: a password, then an e-mailed Sign-in Code (R1, T7,
ADR 0002, ADR 0005).

Signing in is two steps, and no session leaves here before both are done:

- `POST /api/auth/login` checks the e-mail and password with Supabase Auth,
  e-mails a Sign-in Code and answers with a Sign-in Challenge.
- `POST /api/auth/register` creates the (pending) Account with its full name
  and password, e-mails the code that finishes registering, and answers with
  a challenge too. An e-mail that already has an Account gets a decoy
  challenge, so the answer never reveals whether an Account exists.
- `POST /api/auth/code` sends a new code for a challenge.
- `POST /api/auth/verify` checks the code against the challenge, records the
  session as verified (only verified sessions get past `get_signed_in_user`),
  records *Login succeeded* and returns Supabase's session for `setSession`.
- `POST /api/auth/password/forgot` and `/password/reset` replace a forgotten
  password with an e-mailed code; every session of the Account then ends.

A new password (register, reset) has at least 12 characters, is not on the
common list and not known to Pwned Passwords (SR-02, `app.password_policy`,
`app.pwned_passwords`); otherwise 422 `weak_password`, before Supabase Auth
is asked. Signing in accepts any length, so older Accounts still get in.

Wrong passwords, wrong codes and an unreachable Supabase Auth are recorded as
*Login failed*.
"""

from typing import Annotated, Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, StringConstraints

from app import audit
from app.audit import AuditAction, audit_context_for, client_ip, request_audit_context
from app.deps import get_account
from app.deps import get_db
from app import password_policy
from app.models.auth import UserPayload
from app.pwned_passwords import PwnedPasswords, get_pwned_passwords
from app.services import sign_in
from app.supabase_auth import (
    AuthUnavailable,
    SignInRefused,
    SupabaseAuth,
    get_supabase_auth,
)

router = APIRouter(prefix="/auth", tags=["auth"])

Email = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=320)]
# A new password (SR-02). bcrypt reads at most 72 bytes; Supabase Auth
# refuses longer passwords.
Password = Annotated[
    str,
    StringConstraints(
        min_length=password_policy.MIN_LENGTH, max_length=password_policy.MAX_LENGTH
    ),
]
Code = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{6}$")]
ChallengeToken = Annotated[str, StringConstraints(min_length=1, max_length=200)]

CODE_SENT = "We've e-mailed you a 6-digit code."
RESET_SENT = "If an Account exists for this e-mail, we've sent a code."

# Supabase Auth's answers that the proxy acts on.
WRONG_PASSWORD = "invalid_credentials"
NOT_CONFIRMED = "email_not_confirmed"
ALREADY_REGISTERED = "user_already_exists"
SEND_RATE_LIMITED = "over_email_send_rate_limit"
WEAK_PASSWORD = "weak_password"


class LoginRequest(BaseModel):
    email: Email
    password: Annotated[str, StringConstraints(min_length=1, max_length=72)]


class RegisterRequest(BaseModel):
    email: Email
    full_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    password: Password


class ResendRequest(BaseModel):
    challenge: ChallengeToken


class VerifyRequest(BaseModel):
    email: Email
    challenge: ChallengeToken
    code: Code


class ForgotRequest(BaseModel):
    email: Email


class ResetRequest(BaseModel):
    email: Email
    code: Code
    password: Password


# --- step 1 -----------------------------------------------------------------------


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    supabase_auth: SupabaseAuth = Depends(get_supabase_auth),
) -> dict[str, str]:
    """Check the password, e-mail a Sign-in Code, answer with a challenge."""
    ip = client_ip(request)
    try:
        session = await supabase_auth.password_grant(body.email, body.password, ip)
    except SignInRefused as exc:
        if exc.code == NOT_CONFIRMED:
            # The password is right but Register was never finished: send
            # the code that finishes it again.
            return await _finish_registering(db, request, supabase_auth, body.email)
        await _record_failure(db, request, body.email, exc.code)
        raise _refusal(exc, "Wrong e-mail or password." if exc.code == WRONG_PASSWORD else None)
    except AuthUnavailable:
        await _record_failure(db, request, body.email, AuthUnavailable.code)
        raise _unavailable()

    # The password alone opens no session: this one ends now.
    await _sign_out_quietly(supabase_auth, session, ip)
    user = session.get("user") or {}
    return await _send_sign_in_code(
        db, request, supabase_auth, UUID(str(user["id"])), str(user.get("email") or body.email)
    )


@router.post("/register")
async def register(
    body: RegisterRequest,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    supabase_auth: SupabaseAuth = Depends(get_supabase_auth),
    pwned: PwnedPasswords = Depends(get_pwned_passwords),
) -> dict[str, str]:
    """Create the pending Account and e-mail the code that finishes it."""
    ip = client_ip(request)
    weakness = await _weakness(body.password, pwned)
    if weakness:
        raise _weak(weakness)
    try:
        created = await supabase_auth.sign_up(body.email, body.password, body.full_name, ip)
    except SignInRefused as exc:
        if exc.code == ALREADY_REGISTERED:
            return await _decoy(db, body.email)
        await _record_failure(db, request, body.email, exc.code)
        raise _refusal(exc)
    except AuthUnavailable:
        await _record_failure(db, request, body.email, AuthUnavailable.code)
        raise _unavailable()

    if created.get("access_token"):
        # E-mail confirmation is off (local Supabase): the Account exists and
        # is confirmed, so the second step is an ordinary Sign-in Code.
        await _sign_out_quietly(supabase_auth, created, ip)
        user = created.get("user") or {}
        return await _send_sign_in_code(
            db, request, supabase_auth, UUID(str(user["id"])), body.email
        )

    if not created.get("identities"):
        # Supabase Auth's answer for an e-mail that already has an Account:
        # a made-up user, and no e-mail sent.
        return await _decoy(db, body.email)

    # Supabase Auth e-mailed the code that confirms the address.
    token = await sign_in.create_challenge(db, UUID(str(created["id"])), body.email, "register")
    return _challenge_answer(token)


async def _finish_registering(
    db: asyncpg.Connection, request: Request, supabase_auth: SupabaseAuth, email: str
) -> dict[str, str]:
    account = await db.fetchrow(
        "SELECT id, email FROM public.users WHERE lower(email) = lower($1)", email
    )
    if account is None:
        await _record_failure(db, request, email, NOT_CONFIRMED)
        raise _refusal(SignInRefused(400, WRONG_PASSWORD, ""), "Wrong e-mail or password.")
    try:
        await supabase_auth.resend_confirmation(account["email"], client_ip(request))
    except SignInRefused as exc:
        # Asked again within a minute: the code already sent still works.
        if exc.code != SEND_RATE_LIMITED:
            await _record_failure(db, request, email, exc.code)
            raise _refusal(exc)
    except AuthUnavailable:
        await _record_failure(db, request, email, AuthUnavailable.code)
        raise _unavailable()
    token = await sign_in.create_challenge(db, account["id"], account["email"], "register")
    return _challenge_answer(token)


async def _send_sign_in_code(
    db: asyncpg.Connection,
    request: Request,
    supabase_auth: SupabaseAuth,
    user_id: UUID,
    email: str,
) -> dict[str, str]:
    await _send_code(db, request, supabase_auth, email, "sign_in")
    token = await sign_in.create_challenge(db, user_id, email, "sign_in")
    return _challenge_answer(token)


async def _send_code(
    db: asyncpg.Connection,
    request: Request,
    supabase_auth: SupabaseAuth,
    email: str,
    purpose: sign_in.Purpose,
) -> None:
    """E-mail the code for this step. Asked again within a minute, Supabase
    Auth sends nothing, but the code already sent still works."""
    ip = client_ip(request)
    try:
        if purpose == "register":
            await supabase_auth.resend_confirmation(email, ip)
        else:
            await supabase_auth.send_code(email, ip)
    except SignInRefused as exc:
        if exc.code != SEND_RATE_LIMITED:
            await _record_failure(db, request, email, exc.code)
            raise _refusal(exc)
    except AuthUnavailable:
        await _record_failure(db, request, email, AuthUnavailable.code)
        raise _unavailable()


async def _decoy(db: asyncpg.Connection, email: str) -> dict[str, str]:
    """A challenge no code can complete, answered exactly like a real one."""
    return _challenge_answer(await sign_in.create_challenge(db, None, email, "register"))


def _challenge_answer(token: str) -> dict[str, str]:
    return {"challenge": token, "message": CODE_SENT}


# --- step 2 -----------------------------------------------------------------------


@router.post("/code")
async def resend_code(
    body: ResendRequest,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    supabase_auth: SupabaseAuth = Depends(get_supabase_auth),
) -> dict[str, str]:
    """E-mail a new Sign-in Code for a challenge that is still open."""
    challenge = await sign_in.open_challenge(db, body.challenge)
    if challenge is None:
        raise _challenge_expired()
    if challenge.user_id is not None:
        await _send_code(db, request, supabase_auth, challenge.email, challenge.purpose)
    return {"message": CODE_SENT}


@router.post("/verify")
async def verify(
    body: VerifyRequest,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    supabase_auth: SupabaseAuth = Depends(get_supabase_auth),
) -> dict[str, Any]:
    """Check the Sign-in Code and return Supabase's session for `setSession`."""
    ip = client_ip(request)
    challenge = await sign_in.open_challenge(db, body.challenge, body.email)
    if challenge is None:
        await _record_failure(db, request, body.email, "challenge_expired")
        raise _challenge_expired()

    if challenge.user_id is None:
        await sign_in.count_wrong_code(db, challenge)
        await _record_failure(db, request, body.email, "otp_invalid")
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, {"code": "otp_invalid", "message": "Token is invalid"}
        )

    try:
        session = await supabase_auth.verify_code(challenge.email, body.code, ip)
    except SignInRefused as exc:
        await sign_in.count_wrong_code(db, challenge)
        await _record_failure(db, request, body.email, exc.code)
        raise HTTPException(exc.status_code, {"code": exc.code, "message": exc.message})
    except AuthUnavailable:
        await _record_failure(db, request, body.email, AuthUnavailable.code)
        raise _unavailable()

    session_id, user_id = sign_in.session_ids(session)
    if user_id != challenge.user_id:
        # A code for someone else's address: never let it in.
        await _sign_out_quietly(supabase_auth, session, ip)
        await sign_in.count_wrong_code(db, challenge)
        await _record_failure(db, request, body.email, "otp_invalid")
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, {"code": "otp_invalid", "message": "Token is invalid"}
        )

    account = await db.fetchrow(
        "SELECT email, role FROM public.users WHERE id = $1", user_id
    )
    ctx = request_audit_context(
        request, user_id, account["email"] if account else challenge.email,
        account["role"] if account else None,
    )
    async with db.transaction():
        await sign_in.complete(db, challenge, session_id, user_id)
        await audit.record(
            db, ctx, AuditAction.LOGIN_SUCCEEDED,
            target_type="account", target_id=user_id,
        )
    return session


# --- a forgotten password -------------------------------------------------------


@router.post("/password/forgot")
async def forgot_password(
    body: ForgotRequest,
    request: Request,
    supabase_auth: SupabaseAuth = Depends(get_supabase_auth),
) -> dict[str, str]:
    """E-mail a code for a new password. Same answer for every e-mail."""
    try:
        await supabase_auth.send_password_reset(body.email, client_ip(request))
    except SignInRefused:
        pass
    except AuthUnavailable:
        raise _unavailable()
    return {"message": RESET_SENT}


@router.post("/password/reset")
async def reset_password(
    body: ResetRequest,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    supabase_auth: SupabaseAuth = Depends(get_supabase_auth),
    pwned: PwnedPasswords = Depends(get_pwned_passwords),
) -> dict[str, str]:
    """Check the code, set the new password and end every session."""
    ip = client_ip(request)
    # Before the code is used, so it still works for a better password.
    weakness = await _weakness(body.password, pwned)
    if weakness:
        await _record_reset(db, request, body.email, outcome="refused", reason=WEAK_PASSWORD)
        raise _weak(weakness)
    try:
        session = await supabase_auth.verify_code(body.email, body.code, ip, type="recovery")
    except SignInRefused as exc:
        await _record_reset(db, request, body.email, outcome="refused", reason=exc.code)
        raise HTTPException(exc.status_code, {"code": exc.code, "message": exc.message})
    except AuthUnavailable:
        await _record_reset(db, request, body.email, outcome="refused", reason=AuthUnavailable.code)
        raise _unavailable()

    _, user_id = sign_in.session_ids(session)
    try:
        await supabase_auth.set_password(session["access_token"], body.password, ip)
    except SignInRefused as exc:
        await _sign_out_quietly(supabase_auth, session, ip)
        await _record_reset(db, request, body.email, outcome="refused", reason=exc.code)
        raise _refusal(exc)
    except AuthUnavailable:
        await _sign_out_quietly(supabase_auth, session, ip)
        await _record_reset(db, request, body.email, outcome="refused", reason=AuthUnavailable.code)
        raise _unavailable()

    # Whoever was signed in as this Account is signed out everywhere.
    await _sign_out_quietly(supabase_auth, session, ip, scope="global")
    async with db.transaction():
        await sign_in.end_all_sessions(db, user_id)
    await _record_reset(db, request, body.email, outcome="succeeded", reason=None)
    return {"message": "Your password has been changed. Sign in with it now."}


async def _record_reset(
    db: asyncpg.Connection, request: Request, email: str, *, outcome: str, reason: str | None
) -> None:
    account = await db.fetchrow(
        "SELECT id, role FROM public.users WHERE lower(email) = lower($1)", email
    )
    actor_id = account["id"] if account else None
    ctx = request_audit_context(request, actor_id, email, account["role"] if account else None)
    async with db.transaction():
        await audit.record(
            db, ctx, AuditAction.PASSWORD_RESET,
            target_type="account" if actor_id else None,
            target_id=actor_id,
            reason=reason,
            outcome=outcome,
        )


# --- shared ---------------------------------------------------------------------


async def _weakness(password: str, pwned: PwnedPasswords) -> str | None:
    """Why a new password (already 12 to 72 characters) is refused, or None.
    The common list first: a listed password never leaves the host."""
    if password_policy.is_common(password):
        return "This password is too common. Choose a less predictable one."
    if await pwned.is_breached(password):
        return (
            "This password has appeared in a known data breach. Choose a different one."
        )
    return None


def _weak(message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, {"code": WEAK_PASSWORD, "message": message}
    )


async def _sign_out_quietly(
    supabase_auth: SupabaseAuth,
    session: dict[str, Any],
    ip: str | None,
    scope: str = "local",
) -> None:
    """End a session that must not be used. Best effort: it can't get past
    the API anyway, because it is not a verified session."""
    token = session.get("access_token")
    if not token:
        return
    try:
        await supabase_auth.sign_out(str(token), scope, ip)  # type: ignore[arg-type]
    except (SignInRefused, AuthUnavailable):
        pass


def _refusal(exc: SignInRefused, message: str | None = None) -> HTTPException:
    return HTTPException(exc.status_code, {"code": exc.code, "message": message or exc.message})


def _challenge_expired() -> HTTPException:
    return HTTPException(
        status.HTTP_400_BAD_REQUEST,
        {
            "code": "challenge_expired",
            "message": "This sign-in has expired. Enter your password again.",
        },
    )


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


# --- logout ---------------------------------------------------------------------


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    user: UserPayload = Depends(get_account),
) -> Response:
    """Record *logout* and stop accepting the session. The frontend ends the
    Supabase session itself."""
    async with db.transaction():
        await sign_in.end_session(db, request.state.session_id)
        await audit.record(
            db, audit_context_for(request, user), AuditAction.LOGOUT,
            target_type="account", target_id=user.sub,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
