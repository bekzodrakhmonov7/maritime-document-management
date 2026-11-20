"""Block after failed logins (SR-18).

Counted: *login failed* records of the last 15 minutes whose reason is a
wrong password or unknown e-mail (`invalid_credentials`) or a wrong
authenticator code (`totp_invalid`), per lower-case e-mail and per client
address. At 10, the e-mail or the address is blocked for 15 minutes
(`public.login_block`). Not counted: Supabase Auth being unavailable and the
blocked attempts themselves, so a blocked attempt never extends a block.
"""

import asyncpg

LIMIT = 10
WINDOW = "15 minutes"
COUNTED = ("invalid_credentials", "totp_invalid")


async def retry_after(db: asyncpg.Connection, email: str, ip: str | None) -> int | None:
    """Seconds until the block on the e-mail or the address ends, or None."""
    return await db.fetchval(
        """
        SELECT ceil(extract(epoch FROM max(blocked_until) - now()))::int
          FROM public.login_block
         WHERE blocked_until > now()
           AND ((kind = 'email' AND key = lower($1)) OR (kind = 'ip' AND key = $2))
        """,
        email,
        ip,
    )


async def count_failure(
    db: asyncpg.Connection, email: str, ip: str | None, reason: str
) -> None:
    """After a *login failed* record (same transaction): if its reason
    counts, block the e-mail and the address that have reached the limit."""
    if reason not in COUNTED:
        return
    await db.execute(
        f"""
        INSERT INTO public.login_block (kind, key, blocked_until)
        SELECT 'email', lower($1), now() + interval '{WINDOW}'
         WHERE (SELECT count(*) FROM public.audit_log
                 WHERE action = 'login_failed' AND reason = ANY($2::text[])
                   AND occurred_at > now() - interval '{WINDOW}'
                   AND lower(actor_email) = lower($1)) >= $3
        ON CONFLICT (kind, key) DO UPDATE SET blocked_until = excluded.blocked_until
        """,
        email,
        list(COUNTED),
        LIMIT,
    )
    if ip is None:
        return
    await db.execute(
        f"""
        INSERT INTO public.login_block (kind, key, blocked_until)
        SELECT 'ip', $1::text, now() + interval '{WINDOW}'
         WHERE (SELECT count(*) FROM public.audit_log
                 WHERE action = 'login_failed' AND reason = ANY($2::text[])
                   AND occurred_at > now() - interval '{WINDOW}'
                   AND ip = $1::text::inet) >= $3
        ON CONFLICT (kind, key) DO UPDATE SET blocked_until = excluded.blocked_until
        """,
        ip,
        list(COUNTED),
        LIMIT,
    )
