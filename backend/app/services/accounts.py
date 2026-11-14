"""Account approval and switch-off/on (FR-01, FR-02, T5).

Each change runs in one transaction with its Audit Record. Guards:
- nobody changes their own role or status;
- the last active administrator can't be deactivated or demoted.
"""

from typing import Any
from uuid import UUID

import asyncpg

from app import audit
from app.audit import AuditAction, AuditContext

ACCOUNT_COLUMNS = "id, email, full_name, status, role, status_reason, status_changed_at, created_at"


class AccountNotFound(Exception):
    pass


class AccountConflict(Exception):
    """The change isn't allowed in the account's current state."""


async def list_accounts(conn: asyncpg.Connection, status: str | None = None) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT {ACCOUNT_COLUMNS} FROM public.users
         WHERE $1::text IS NULL OR status = $1
         ORDER BY created_at DESC, email
        """,
        status,
    )
    return [dict(r) for r in rows]


async def count_pending(conn: asyncpg.Connection) -> int:
    return await conn.fetchval("SELECT count(*) FROM public.users WHERE status = 'pending'")


async def approve(
    conn: asyncpg.Connection, ctx: AuditContext, account_id: UUID, role: str, reason: str
) -> dict:
    async with conn.transaction():
        current = await _lock(conn, ctx, account_id)
        if current["status"] != "pending":
            raise AccountConflict("Only a pending account can be approved.")
        return await _apply(
            conn, ctx, current, AuditAction.ACCOUNT_APPROVED,
            {"status": "active", "role": role}, reason,
        )


async def change_role(
    conn: asyncpg.Connection, ctx: AuditContext, account_id: UUID, role: str, reason: str
) -> dict:
    async with conn.transaction():
        current = await _lock(conn, ctx, account_id)
        if current["status"] != "active":
            raise AccountConflict("Only an active account's role can be changed.")
        if current["role"] == role:
            raise AccountConflict("The account already has that role.")
        if current["role"] == "administrator":
            await _refuse_last_admin(conn, "demote")
        return await _apply(
            conn, ctx, current, AuditAction.ACCOUNT_ROLE_CHANGED, {"role": role}, reason
        )


async def deactivate(
    conn: asyncpg.Connection, ctx: AuditContext, account_id: UUID, reason: str
) -> dict:
    """Switch an account off. Rejecting a sign-up is deactivating it."""
    async with conn.transaction():
        current = await _lock(conn, ctx, account_id)
        if current["status"] == "deactivated":
            raise AccountConflict("The account is already deactivated.")
        if current["status"] == "active" and current["role"] == "administrator":
            await _refuse_last_admin(conn, "deactivate")
        return await _apply(
            conn, ctx, current, AuditAction.ACCOUNT_DEACTIVATED,
            {"status": "deactivated"}, reason,
        )


async def reactivate(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    account_id: UUID,
    reason: str,
    role: str | None = None,
) -> dict:
    """Switch an account back on, keeping its role unless a new one is given.
    A rejected sign-up never had a role, so it needs one now."""
    async with conn.transaction():
        current = await _lock(conn, ctx, account_id)
        if current["status"] != "deactivated":
            raise AccountConflict("Only a deactivated account can be reactivated.")
        new_role = role or current["role"]
        if new_role is None:
            raise AccountConflict("This account never had a role: pick one to reactivate it.")
        return await _apply(
            conn, ctx, current, AuditAction.ACCOUNT_REACTIVATED,
            {"status": "active", "role": new_role}, reason,
        )


async def _lock(conn: asyncpg.Connection, ctx: AuditContext, account_id: UUID) -> asyncpg.Record:
    if ctx.actor_id is not None and ctx.actor_id == account_id:
        raise AccountConflict("You can't change your own role or status.")
    row = await conn.fetchrow(
        f"SELECT {ACCOUNT_COLUMNS} FROM public.users WHERE id = $1 FOR UPDATE", account_id
    )
    if row is None:
        raise AccountNotFound()
    return row


async def _refuse_last_admin(conn: asyncpg.Connection, verb: str) -> None:
    # Locking every active administrator serialises concurrent attempts, so two
    # administrators can't switch each other off at the same time.
    admins = await conn.fetch(
        "SELECT id FROM public.users WHERE status = 'active' AND role = 'administrator' FOR UPDATE"
    )
    if len(admins) <= 1:
        raise AccountConflict(f"You can't {verb} the last active administrator.")


async def _apply(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    current: asyncpg.Record,
    action: AuditAction,
    changes: dict[str, Any],
    reason: str,
) -> dict:
    row = await conn.fetchrow(
        f"""
        UPDATE public.users
           SET status = $2, role = $3, status_reason = $4, status_changed_at = now()
         WHERE id = $1
     RETURNING {ACCOUNT_COLUMNS}
        """,
        current["id"],
        changes.get("status", current["status"]),
        changes.get("role", current["role"]),
        reason,
    )
    before, after = audit.changed_fields(
        {"status": current["status"], "role": current["role"]},
        {"status": row["status"], "role": row["role"]},
    )
    await audit.record(
        conn, ctx, action,
        target_type="account", target_id=row["id"],
        before=before, after=after, reason=reason,
    )
    return dict(row)
