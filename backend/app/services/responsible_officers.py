"""Responsible Officer links (FR-03, T5).

Administrators link crewing officers to vessels, many to many. Each link added
or removed writes an Audit Record about the vessel, naming the officer. Links
are only for crewing officers: a role change away from it drops them (with a
record each, carrying the role change's reason). A deactivated officer keeps
their links; the Scope ignores them until the account is active again.
"""

from uuid import UUID

import asyncpg

from app import audit
from app.audit import AuditAction, AuditContext
from app.services import reference_data
from app.services.errors import Conflict, Invalid, NotFound

TARGET = "vessel"

_OFFICER_COLUMNS = "u.id, u.email, u.full_name, u.status"


async def vessel_ids(conn: asyncpg.Connection, account_id: UUID) -> set[int]:
    """The vessels an officer is a Responsible Officer for."""
    rows = await conn.fetch(
        "SELECT vessel_id FROM public.responsible_officer WHERE user_id = $1", account_id
    )
    return {r["vessel_id"] for r in rows}


async def list_for_vessel(conn: asyncpg.Connection, vessel_id: int) -> list[dict]:
    """A vessel's Responsible Officers, deactivated ones included (flagged by status)."""
    await reference_data.get_row(conn, reference_data.VESSEL, vessel_id)
    rows = await conn.fetch(
        f"""
        SELECT {_OFFICER_COLUMNS}
          FROM public.responsible_officer ro JOIN public.users u ON u.id = ro.user_id
         WHERE ro.vessel_id = $1
         ORDER BY lower(u.full_name), lower(u.email)
        """,
        vessel_id,
    )
    return [dict(r) for r in rows]


async def vessels_without_active_officer(conn: asyncpg.Connection) -> list[dict]:
    """Vessels no active crewing officer is responsible for (coverage gaps)."""
    columns = ", ".join(f"v.{c}" for c in reference_data.VESSEL.columns.split(", "))
    rows = await conn.fetch(
        f"""
        SELECT {columns} FROM public.vessel v
         WHERE NOT EXISTS (
                SELECT 1 FROM public.responsible_officer ro
                  JOIN public.users u ON u.id = ro.user_id
                 WHERE ro.vessel_id = v.id AND u.status = 'active')
         ORDER BY lower(v.name), v.id
        """
    )
    return [dict(r) for r in rows]


async def add(
    conn: asyncpg.Connection, ctx: AuditContext, vessel_id: int, account_id: UUID
) -> list[dict]:
    """Link an active crewing officer to an active vessel; returns the vessel's officers."""
    async with conn.transaction():
        await reference_data.get_row(conn, reference_data.VESSEL, vessel_id)
        await link(conn, ctx, account_id, vessel_id)
    return await list_for_vessel(conn, vessel_id)


async def remove(
    conn: asyncpg.Connection, ctx: AuditContext, vessel_id: int, account_id: UUID
) -> None:
    async with conn.transaction():
        email = await conn.fetchval(
            """
            DELETE FROM public.responsible_officer ro USING public.users u
             WHERE ro.user_id = $1 AND ro.vessel_id = $2 AND u.id = ro.user_id
         RETURNING u.email
            """,
            account_id,
            vessel_id,
        )
        if email is None:
            raise NotFound()
        await _record(conn, ctx, AuditAction.RESPONSIBLE_OFFICER_REMOVED, vessel_id, account_id, email)


async def link(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    account_id: UUID,
    vessel_id: int,
    reason: str | None = None,
) -> None:
    """Add one link inside the caller's transaction (also used on approval).
    The officer row is locked so its role can't change meanwhile."""
    account = await conn.fetchrow(
        "SELECT email, status, role FROM public.users WHERE id = $1 FOR SHARE", account_id
    )
    if account is None:
        raise Invalid("That account doesn't exist.")
    if account["role"] != "crewing_officer" or account["status"] != "active":
        raise Invalid("Only an active crewing officer can be a Responsible Officer.")
    await reference_data.check_pickable(conn, reference_data.VESSEL, vessel_id)
    inserted = await conn.fetchval(
        """
        INSERT INTO public.responsible_officer (user_id, vessel_id) VALUES ($1, $2)
        ON CONFLICT DO NOTHING
        RETURNING true
        """,
        account_id,
        vessel_id,
    )
    if not inserted:
        raise Conflict("That officer is already a Responsible Officer for this vessel.")
    await _record(
        conn, ctx, AuditAction.RESPONSIBLE_OFFICER_ADDED, vessel_id, account_id, account["email"],
        reason=reason,
    )


async def drop_all(
    conn: asyncpg.Connection, ctx: AuditContext, account_id: UUID, reason: str
) -> None:
    """Remove every link of an officer whose role changes away from crewing
    officer, inside the caller's transaction."""
    rows = await conn.fetch(
        """
        DELETE FROM public.responsible_officer ro USING public.users u
         WHERE ro.user_id = $1 AND u.id = ro.user_id
     RETURNING ro.vessel_id, u.email
        """,
        account_id,
    )
    for row in sorted(rows, key=lambda r: r["vessel_id"]):
        await _record(
            conn, ctx, AuditAction.RESPONSIBLE_OFFICER_REMOVED, row["vessel_id"], account_id,
            row["email"], reason=reason,
        )


async def _record(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    action: AuditAction,
    vessel_id: int,
    account_id: UUID,
    email: str,
    reason: str | None = None,
) -> None:
    officer = {"responsible_officer_id": str(account_id), "responsible_officer_email": email}
    added = action == AuditAction.RESPONSIBLE_OFFICER_ADDED
    await audit.record(
        conn, ctx, action,
        target_type=TARGET, target_id=vessel_id,
        before=None if added else officer, after=officer if added else None,
        reason=reason,
    )
