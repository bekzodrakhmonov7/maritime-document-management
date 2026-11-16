"""Sign-in Challenges and verified sessions (ADR-0005).

A Sign-in Challenge says "the first step (the password, or a Register) is
done for this e-mail". The browser holds its token; only the SHA-256 of the
token is stored. The Sign-in Code must be typed against it within
CHALLENGE_MINUTES, and MAX_WRONG_CODES wrong codes end it.

A verified session is a Supabase session (the access token's `session_id`)
that passed both steps. `get_signed_in_user` refuses every other session.
"""

import hashlib
import secrets
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import asyncpg
import jwt

CHALLENGE_MINUTES = 10
MAX_WRONG_CODES = 5

Purpose = Literal["sign_in", "register"]


@dataclass(frozen=True)
class Challenge:
    token_hash: str
    # None for a decoy: a Register with an e-mail that already has an Account.
    user_id: UUID | None
    email: str
    purpose: Purpose


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_challenge(
    db: asyncpg.Connection, user_id: UUID | None, email: str, purpose: Purpose
) -> str:
    """A new challenge; returns the token for the browser. Old, finished
    challenges are cleared out on the way."""
    token = secrets.token_urlsafe(32)
    await db.execute(
        "DELETE FROM public.sign_in_challenge"
        " WHERE expires_at < now() OR used_at IS NOT NULL OR wrong_codes >= $1",
        MAX_WRONG_CODES,
    )
    await db.execute(
        """
        INSERT INTO public.sign_in_challenge (token_hash, user_id, email, purpose, expires_at)
        VALUES ($1, $2, $3, $4, now() + make_interval(mins => $5))
        """,
        _hash(token), user_id, email, purpose, CHALLENGE_MINUTES,
    )
    return token


async def open_challenge(db: asyncpg.Connection, token: str, email: str | None = None) -> Challenge | None:
    """The challenge if it can still be used (and is for `email`, when given)."""
    row = await db.fetchrow(
        """
        SELECT token_hash, user_id, email, purpose
          FROM public.sign_in_challenge
         WHERE token_hash = $1 AND used_at IS NULL
           AND expires_at > now() AND wrong_codes < $2
        """,
        _hash(token), MAX_WRONG_CODES,
    )
    if row is None:
        return None
    if email is not None and row["email"].lower() != email.lower():
        return None
    return Challenge(row["token_hash"], row["user_id"], row["email"], row["purpose"])


async def count_wrong_code(db: asyncpg.Connection, challenge: Challenge) -> None:
    await db.execute(
        "UPDATE public.sign_in_challenge SET wrong_codes = wrong_codes + 1"
        " WHERE token_hash = $1 AND wrong_codes < $2",
        challenge.token_hash, MAX_WRONG_CODES,
    )


async def complete(
    db: asyncpg.Connection, challenge: Challenge, session_id: UUID, user_id: UUID
) -> None:
    """Use up the challenge and let the session in. Call inside a transaction."""
    await db.execute(
        "UPDATE public.sign_in_challenge SET used_at = now() WHERE token_hash = $1",
        challenge.token_hash,
    )
    await db.execute(
        "INSERT INTO public.verified_session (session_id, user_id) VALUES ($1, $2)"
        " ON CONFLICT (session_id) DO NOTHING",
        session_id, user_id,
    )


async def end_session(db: asyncpg.Connection, session_id: UUID) -> None:
    await db.execute("DELETE FROM public.verified_session WHERE session_id = $1", session_id)


async def end_all_sessions(db: asyncpg.Connection, user_id: UUID) -> None:
    await db.execute("DELETE FROM public.verified_session WHERE user_id = $1", user_id)


def session_ids(session: dict[str, Any]) -> tuple[UUID, UUID]:
    """(session_id, user_id) of a session Supabase Auth just returned to us.

    The token came straight from Supabase Auth over our own connection, so
    its claims are read without checking the signature here; every later
    request checks it in `get_signed_in_user`."""
    claims = jwt.decode(session["access_token"], options={"verify_signature": False})
    return UUID(str(claims["session_id"])), UUID(str(claims["sub"]))
