"""Make a signed-up account an active administrator (T5).

    cd backend && uv run python -m app.scripts.make_admin <email>

Used once to bootstrap the first administrator after they sign up; later
administrators are approved in the app. Runs as app_backend (DATABASE_URL)
and is audited as a system action.
"""

import asyncio
import sys

import asyncpg

from app.audit import AuditContext
from app.services import accounts

REASON = "Made administrator with the make_admin command"


class NoSuchAccount(Exception):
    pass


async def make_admin(conn: asyncpg.Connection, email: str) -> str:
    row = await conn.fetchrow(
        "SELECT id, status, role FROM public.users WHERE lower(email) = lower($1)",
        email.strip(),
    )
    if row is None:
        raise NoSuchAccount(f"No account for {email}. Sign up in the app first, then run this again.")

    ctx = AuditContext.system()
    if row["status"] == "pending":
        await accounts.approve(conn, ctx, row["id"], "administrator", REASON)
    elif row["status"] == "deactivated":
        await accounts.reactivate(conn, ctx, row["id"], REASON, role="administrator")
    elif row["role"] != "administrator":
        await accounts.change_role(conn, ctx, row["id"], "administrator", REASON)
    else:
        return f"{email} is already an active administrator."
    return f"{email} is now an active administrator."


async def _main(email: str) -> int:
    from app.db import create_pool

    pool = await create_pool()
    try:
        async with pool.acquire() as conn:
            print(await make_admin(conn, email))
    except NoSuchAccount as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        await pool.close()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m app.scripts.make_admin <email>", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(_main(sys.argv[1])))
