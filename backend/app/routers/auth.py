"""The sign-in proxy: a password, then a TOTP code from an authenticator
app (R1, T7, ADR 0002, ADR 0005, ADR 0007, SR-03).

Signing in is two steps, and no session leaves here before both are done:

- `POST /api/auth/login` checks the e-mail and password with Supabase Auth
  (an aal1 session, which stays here) and answers with a Sign-in Challenge
  and its step: `totp` when the Account has an authenticator, otherwise
  `enrol` with the QR code (SVG), the secret and the otpauth URI of a new
  TOTP factor. No e-mail is sent.
- `POST /api/auth/register` creates the (pending) Account with its full name
  and password, e-mails the code that finishes registering, and answers with
  a challenge whose step is `email`. An e-mail that already has an Account
  gets a decoy challenge, so the answer never reveals whether an Account
  exists. The right code leads on to the `enrol` step.
- `POST /api/auth/code` sends the registration code again.
- `POST /api/auth/verify` checks the code against the challenge. For the
  TOTP step it asks Supabase Auth for an MFA challenge and verifies the
  code, which raises the session to aal2; the session is then recorded as
  verified (only verified aal2 sessions get past `get_signed_in_user`),
  *Login succeeded* is recorded and Supabase's session is returned for
  `setSession`. Five wrong codes end the challenge.
- `POST /api/auth/password/forgot` and `/password/reset` replace a forgotten
  password with an e-mailed code; every session of the Account then ends.
  The next sign-in still needs the authenticator.

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
from app.deps import SessionRefused, account_refused, get_account
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
TOTP_ASKED = "Enter the 6-digit code from your authenticator app."
ENROL_ASKED = (
    "Set up two-step sign-in: scan the QR code with an authenticator app, or type the key,"
    " then enter the 6-digit code it shows."
)

# The step a challenge is for, as the frontend shows it.
STEP_EMAIL = "email"
STEP_TOTP = "totp"
STEP_ENROL = "enrol"
AAL2 = "aal2"
RESET_SENT = "If an Account exists for this e-mail, we've sent a code."

# Supabase Auth's answers that the proxy acts on.
WRONG_PASSWORD = "invalid_credentials"
NOT_CONFIRMED = "email_not_confirmed"
ALREADY_REGISTERED = "user_already_exists"
SEND_RATE_LIMITED = "over_email_send_rate_limit"
WEAK_PASSWORD = "weak_password"
TOTP_REFUSED = "mfa_verification_failed"
# Recorded and answered for a wrong authenticator code.
TOTP_INVALID = "totp_invalid"


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
    """Check the password and answer with a challenge for the TOTP step:
    the code of the enrolled authenticator, or an enrolment first."""
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

    return await _second_factor_step(db, request, supabase_auth, session, body.email)


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
        # E-mail confirmation is off: the Account exists and is confirmed,
        # so Register goes straight on to enrolling the authenticator.
        return await _second_factor_step(db, request, supabase_auth, created, body.email)

    if not created.get("identities"):
        # Supabase Auth's answer for an e-mail that already has an Account:
        # a made-up user, and no e-mail sent.
        return await _decoy(db, body.email)

    # Supabase Auth e-mailed the code that confirms the address.
    token = await sign_in.create_challenge(db, UUID(str(created["id"])), body.email, "register")
    return _email_step(token)


async def _finish_registering(
    db: asyncpg.Connection, request: Request, supabase_auth: SupabaseAuth, email: str
) -> dict[str, str]:
    account = await db.fetchrow(
        "SELECT id, email FROM public.users WHERE lower(email) = lower($1)", email
    )
    if account is None:
        await _record_failure(db, request, email, NOT_CONFIRMED)
        raise _refusal(SignInRefused(400, WRONG_PASSWORD, ""), "Wrong e-mail or password.")
    await _resend_confirmation(db, request, supabase_auth, account["email"])
    token = await sign_in.create_challenge(db, account["id"], account["email"], "register")
    return _email_step(token)


async def _resend_confirmation(
    db: asyncpg.Connection, request: Request, supabase_auth: SupabaseAuth, email: str
) -> None:
    """E-mail the code that finishes a Register again. Asked again within a
    minute, Supabase Auth sends nothing, but the code already sent still works."""
    try:
        await supabase_auth.resend_confirmation(email, client_ip(request))
    except SignInRefused as exc:
        if exc.code != SEND_RATE_LIMITED:
            await _record_failure(db, request, email, exc.code)
            raise _refusal(exc)
    except AuthUnavailable:
        await _record_failure(db, request, email, AuthUnavailable.code)
        raise _unavailable()


async def _second_factor_step(
    db: asyncpg.Connection,
    request: Request,
    supabase_auth: SupabaseAuth,
    session: dict[str, Any],
    email: str,
) -> dict[str, str]:
    """The TOTP step for an aal1 session (ADR 0007). With a verified TOTP
    factor: ask for its code. Without one: drop unfinished enrolments and
    start a new one. The aal1 token stays in the challenge row only."""
    ip = client_ip(request)
    access_token = str(session["access_token"])
    user = session.get("user") or {}
    user_id = UUID(str(user["id"]))
    email = str(user.get("email") or email)
    try:
        factors = [
            f for f in await supabase_auth.list_factors(access_token, ip)
            if f.get("factor_type") == "totp"
        ]
        verified = next((f for f in factors if f.get("status") == "verified"), None)
        if verified is None:
            for factor in factors:
                await supabase_auth.unenroll(access_token, str(factor["id"]), ip)
            enrolled = await supabase_auth.enroll_totp(access_token, ip)
    except SignInRefused as exc:
        await _sign_out_quietly(supabase_auth, session, ip)
        await _record_failure(db, request, email, exc.code)
        raise _refusal(exc)
    except AuthUnavailable:
        await _sign_out_quietly(supabase_auth, session, ip)
        await _record_failure(db, request, email, AuthUnavailable.code)
        raise _unavailable()

    if verified is not None:
        token = await sign_in.create_challenge(
            db, user_id, email, "sign_in",
            factor_id=UUID(str(verified["id"])), access_token=access_token,
        )
        return {"challenge": token, "step": STEP_TOTP, "message": TOTP_ASKED}

    token = await sign_in.create_challenge(
        db, user_id, email, "sign_in",
        factor_id=UUID(str(enrolled["id"])), access_token=access_token,
    )
    totp = enrolled.get("totp") or {}
    return {
        "challenge": token,
        "step": STEP_ENROL,
        "message": ENROL_ASKED,
        "qr_code": str(totp.get("qr_code") or ""),
        "secret": str(totp.get("secret") or ""),
        "uri": str(totp.get("uri") or ""),
    }


async def _decoy(db: asyncpg.Connection, email: str) -> dict[str, str]:
    """A challenge no code can complete, answered exactly like a real one."""
    return _email_step(await sign_in.create_challenge(db, None, email, "register"))


def _email_step(token: str) -> dict[str, str]:
    return {"challenge": token, "step": STEP_EMAIL, "message": CODE_SENT}


# --- step 2 -----------------------------------------------------------------------


@router.post("/code")
async def resend_code(
    body: ResendRequest,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    supabase_auth: SupabaseAuth = Depends(get_supabase_auth),
) -> dict[str, str]:
    """E-mail the code that finishes a Register again. The TOTP step has no
    e-mailed code."""
    challenge = await sign_in.open_challenge(db, body.challenge)
    if challenge is None:
        raise _challenge_expired()
    if challenge.purpose != "register":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            {
                "code": "no_emailed_code",
                "message": "This step needs the code from your authenticator app.",
            },
        )
    if challenge.user_id is not None:
        await _resend_confirmation(db, request, supabase_auth, challenge.email)
    return {"message": CODE_SENT}


@router.post("/verify")
async def verify(
    body: VerifyRequest,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    supabase_auth: SupabaseAuth = Depends(get_supabase_auth),
) -> dict[str, Any]:
    """Check the code against the challenge. The e-mailed code of a Register
    leads on to the TOTP step; the right TOTP code returns Supabase's aal2
    session for `setSession`."""
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

    if challenge.purpose == "register":
        return await _verify_emailed_code(db, request, supabase_auth, challenge, body)
    return await _verify_totp(db, request, supabase_auth, challenge, body)


async def _verify_emailed_code(
    db: asyncpg.Connection,
    request: Request,
    supabase_auth: SupabaseAuth,
    challenge: sign_in.Challenge,
    body: VerifyRequest,
) -> dict[str, Any]:
    """The confirmation code that finishes a Register; then the enrolment."""
    ip = client_ip(request)
    try:
        session = await supabase_auth.verify_code(challenge.email, body.code, ip)
    except SignInRefused as exc:
        await sign_in.count_wrong_code(db, challenge)
        await _record_failure(db, request, body.email, exc.code)
        raise HTTPException(exc.status_code, {"code": exc.code, "message": exc.message})
    except AuthUnavailable:
        await _record_failure(db, request, body.email, AuthUnavailable.code)
        raise _unavailable()

    _, user_id = sign_in.session_ids(session)
    if user_id != challenge.user_id:
        # A code for someone else's address: never let it in.
        await _sign_out_quietly(supabase_auth, session, ip)
        await sign_in.count_wrong_code(db, challenge)
        await _record_failure(db, request, body.email, "otp_invalid")
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, {"code": "otp_invalid", "message": "Token is invalid"}
        )

    await sign_in.use_up(db, challenge)
    return await _second_factor_step(db, request, supabase_auth, session, challenge.email)


async def _verify_totp(
    db: asyncpg.Connection,
    request: Request,
    supabase_auth: SupabaseAuth,
    challenge: sign_in.Challenge,
    body: VerifyRequest,
) -> dict[str, Any]:
    """The authenticator's code: challenge and verify at Supabase Auth with
    the aal1 token the challenge row keeps; the session becomes aal2."""
    ip = client_ip(request)
    access_token = challenge.access_token
    if access_token is None or challenge.factor_id is None:
        await _record_failure(db, request, body.email, "challenge_expired")
        raise _challenge_expired()
    factor_id = str(challenge.factor_id)
    try:
        challenge_id = await supabase_auth.challenge(access_token, factor_id, ip)
        session = await supabase_auth.verify_totp(
            access_token, factor_id, challenge_id, body.code, ip
        )
    except SignInRefused as exc:
        if exc.code == TOTP_REFUSED:
            if await sign_in.count_wrong_code(db, challenge):
                # Five wrong codes: the aal1 session is of no further use.
                await _sign_out_quietly(supabase_auth, {"access_token": access_token}, ip)
            await _record_failure(db, request, body.email, TOTP_INVALID)
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                {"code": TOTP_INVALID, "message": "That code is wrong. Check the app and try again."},
            )
        await _record_failure(db, request, body.email, exc.code)
        if exc.status_code in (401, 403, 404):
            # The aal1 session or the factor is gone: start again.
            await sign_in.use_up(db, challenge)
            raise _challenge_expired()
        raise HTTPException(exc.status_code, {"code": exc.code, "message": exc.message})
    except AuthUnavailable:
        await _record_failure(db, request, body.email, AuthUnavailable.code)
        raise _unavailable()

    claims = sign_in.claims(session)
    session_id, user_id = UUID(str(claims["session_id"])), UUID(str(claims["sub"]))
    if user_id != challenge.user_id or claims.get("aal") != AAL2:
        await _sign_out_quietly(supabase_auth, session, ip)
        await sign_in.use_up(db, challenge)
        await _record_failure(db, request, body.email, TOTP_INVALID)
        raise _challenge_expired()

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


# --- refresh and logout: the browser never calls Supabase Auth (SR-01) -----------


class RefreshRequest(BaseModel):
    refresh_token: Annotated[str, StringConstraints(min_length=1, max_length=200)]


@router.post("/refresh")
async def refresh(
    body: RefreshRequest,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    supabase_auth: SupabaseAuth = Depends(get_supabase_auth),
) -> dict[str, Any]:
    """Renew the session with its refresh token. The new session is returned
    only while it is a verified aal2 session of an Account that is not
    switched off; otherwise 401 (403 when switched off) and *access refused*."""
    ip = client_ip(request)
    try:
        session = await supabase_auth.refresh(body.refresh_token, ip)
    except SignInRefused:
        # Unknown, used or revoked: nothing names an Account.
        raise SessionRefused("invalid_session", _sign_in_again("invalid_session"))
    except AuthUnavailable:
        raise _unavailable()

    claims = sign_in.claims(session)
    session_id, user_id = UUID(str(claims["session_id"])), UUID(str(claims["sub"]))
    row = await db.fetchrow(
        """
        SELECT u.email, u.role, u.status,
               EXISTS (SELECT 1 FROM public.verified_session AS v
                        WHERE v.session_id = $2 AND v.user_id = u.id) AS verified
          FROM public.users AS u
         WHERE u.id = $1
        """,
        user_id, session_id,
    )
    reason = (
        "invalid_session" if row is None
        else "second_factor_missing" if claims.get("aal") != AAL2
        else "session_not_verified" if not row["verified"]
        else None
    )
    if reason is not None:
        # Of no use to anyone: end it at Supabase Auth as well.
        await _sign_out_quietly(supabase_auth, session, ip)
        raise SessionRefused(
            reason, _sign_in_again(reason),
            account_id=user_id if row else None,
            email=row["email"] if row else None,
            role=row["role"] if row else None,
        )
    if row["status"] == "deactivated":
        await _sign_out_quietly(supabase_auth, session, ip)
        request.state.account = UserPayload(
            sub=user_id, email=row["email"],
            status=row["status"], role=row["role"],
        )
        raise account_refused("account_deactivated", "Your account has been switched off.")
    return session


def _sign_in_again(code: str) -> dict[str, str]:
    return {"code": code, "message": "Sign in again with your password and authenticator code."}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    user: UserPayload = Depends(get_account),
    supabase_auth: SupabaseAuth = Depends(get_supabase_auth),
) -> Response:
    """Record *logout*, stop accepting the session and end it at Supabase
    Auth (this session only, so its refresh token stops working)."""
    async with db.transaction():
        await sign_in.end_session(db, request.state.session_id)
        await audit.record(
            db, audit_context_for(request, user), AuditAction.LOGOUT,
            target_type="account", target_id=user.sub,
        )
    token = request.headers["authorization"].split()[1]
    await _sign_out_quietly(supabase_auth, {"access_token": token}, client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
