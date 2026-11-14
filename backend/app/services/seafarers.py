"""Seafarer records (FR-04, T3, T5).

Every read takes the caller's Scope (app/scope.py) and filters by it. A
record that exists but is outside the Scope raises OutOfScope, which the
router answers exactly like a missing one. Each change runs in one
transaction with its Audit Record; an edit that changes nothing writes none.
Seafarers are set Inactive and reactivated, never deleted.
"""

from typing import Any

import asyncpg

from app import audit
from app.audit import AuditAction, AuditContext
from app.scope import Scope
from app.services.errors import Conflict, Invalid, NotFound, OutOfScope

TARGET = "seafarer"
WRITABLE = ("first_name", "last_name", "date_of_birth", "nationality", "position_id")

_COLUMNS = """
    s.id, s.first_name, s.last_name, s.date_of_birth, s.nationality,
    s.position_id, p.name AS position_name, p.retired AS position_retired,
    s.inactive_since, s.inactive_reason, s.created_at, s.updated_at
"""
_FROM = "public.seafarer s JOIN public.position p ON p.id = s.position_id"


def _like_pattern(word: str) -> str:
    escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def list_seafarers(
    conn: asyncpg.Connection, scope: Scope, *, search: str = "", show_inactive: bool = False
) -> list[dict]:
    """The seafarers in Scope, by name. Every word of `search` must appear in
    the full name; Inactive seafarers only when asked for."""
    conditions = [scope.where("s")]
    args: list[Any] = []
    if not show_inactive:
        conditions.append("s.inactive_since IS NULL")
    for word in search.split():
        args.append(_like_pattern(word))
        conditions.append(f"(s.first_name || ' ' || s.last_name) ILIKE ${len(args)}")
    rows = await conn.fetch(
        f"""
        SELECT {_COLUMNS} FROM {_FROM}
         WHERE {" AND ".join(conditions)}
         ORDER BY lower(s.last_name), lower(s.first_name), s.id
        """,
        *args,
    )
    return [dict(r) for r in rows]


async def get_seafarer(conn: asyncpg.Connection, scope: Scope, seafarer_id: int) -> dict:
    return await _fetch_in_scope(conn, scope, seafarer_id)


async def create(
    conn: asyncpg.Connection, ctx: AuditContext, values: dict[str, Any]
) -> dict:
    """A new seafarer has no Assignment, so it starts in the Unassigned Pool."""
    async with conn.transaction():
        await _check_position_pickable(conn, values["position_id"])
        seafarer_id = await conn.fetchval(
            f"""
            INSERT INTO public.seafarer ({", ".join(WRITABLE)})
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            *(values[c] for c in WRITABLE),
        )
        await audit.record(
            conn, ctx, AuditAction.SEAFARER_CREATED,
            target_type=TARGET, target_id=seafarer_id, seafarer_id=seafarer_id,
            after={c: values[c] for c in WRITABLE},
        )
        return await _fetch(conn, seafarer_id)


async def edit(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    scope: Scope,
    seafarer_id: int,
    values: dict[str, Any],
) -> dict:
    async with conn.transaction():
        current = await _lock_in_scope(conn, scope, seafarer_id)
        before, after = audit.changed_fields(
            {c: current[c] for c in WRITABLE}, {c: values[c] for c in WRITABLE}
        )
        if not after:
            return await _fetch(conn, seafarer_id)
        # A held Position retired since may be kept; a newly picked one may not be retired.
        if "position_id" in after:
            await _check_position_pickable(conn, after["position_id"])
        assignments = ", ".join(f"{c} = ${i}" for i, c in enumerate(after, start=2))
        await conn.execute(
            f"UPDATE public.seafarer SET {assignments}, updated_at = now() WHERE id = $1",
            seafarer_id,
            *after.values(),
        )
        await audit.record(
            conn, ctx, AuditAction.SEAFARER_EDITED,
            target_type=TARGET, target_id=seafarer_id, seafarer_id=seafarer_id,
            before=before, after=after,
        )
        return await _fetch(conn, seafarer_id)


async def set_inactive(
    conn: asyncpg.Connection, ctx: AuditContext, scope: Scope, seafarer_id: int, reason: str
) -> dict:
    """Stop tracking a seafarer actively; `inactive_since` starts the retention clock.

    S6 adds the refusal while an upcoming or under-way Assignment exists.
    """
    async with conn.transaction():
        current = await _lock_in_scope(conn, scope, seafarer_id)
        if current["inactive_since"] is not None:
            raise Conflict("The seafarer is already Inactive.")
        row = await conn.fetchrow(
            """
            UPDATE public.seafarer
               SET inactive_since = now(), inactive_reason = $2, updated_at = now()
             WHERE id = $1
         RETURNING inactive_since, inactive_reason
            """,
            seafarer_id,
            reason,
        )
        await audit.record(
            conn, ctx, AuditAction.SEAFARER_SET_INACTIVE,
            target_type=TARGET, target_id=seafarer_id, seafarer_id=seafarer_id,
            before={"inactive_since": None}, after={"inactive_since": row["inactive_since"]},
            reason=reason,
        )
        return await _fetch(conn, seafarer_id)


async def reactivate(
    conn: asyncpg.Connection, ctx: AuditContext, scope: Scope, seafarer_id: int
) -> dict:
    """Make an Inactive seafarer active again; this clears `inactive_since`."""
    async with conn.transaction():
        current = await _lock_in_scope(conn, scope, seafarer_id)
        if current["inactive_since"] is None:
            raise Conflict("The seafarer is not Inactive.")
        await conn.execute(
            """
            UPDATE public.seafarer
               SET inactive_since = NULL, inactive_reason = NULL, updated_at = now()
             WHERE id = $1
            """,
            seafarer_id,
        )
        await audit.record(
            conn, ctx, AuditAction.SEAFARER_REACTIVATED,
            target_type=TARGET, target_id=seafarer_id, seafarer_id=seafarer_id,
            before={
                "inactive_since": current["inactive_since"],
                "inactive_reason": current["inactive_reason"],
            },
            after={"inactive_since": None, "inactive_reason": None},
        )
        return await _fetch(conn, seafarer_id)


async def _check_position_pickable(conn: asyncpg.Connection, position_id: int) -> None:
    """Only a non-retired Position from the managed list. The row is locked so
    it can't be retired or deleted until this change commits."""
    retired = await conn.fetchval(
        "SELECT retired FROM public.position WHERE id = $1 FOR SHARE", position_id
    )
    if retired is None:
        raise Invalid("That Position doesn't exist.")
    if retired:
        raise Invalid("That Position is retired: pick one from the current list.")


async def _fetch(conn: asyncpg.Connection, seafarer_id: int) -> dict:
    return dict(await conn.fetchrow(f"SELECT {_COLUMNS} FROM {_FROM} WHERE s.id = $1", seafarer_id))


async def _fetch_in_scope(conn: asyncpg.Connection, scope: Scope, seafarer_id: int) -> dict:
    row = await conn.fetchrow(
        f"SELECT {_COLUMNS}, {scope.where('s')} AS in_scope FROM {_FROM} WHERE s.id = $1",
        seafarer_id,
    )
    return _in_scope_or_raise(row, seafarer_id)


async def _lock_in_scope(conn: asyncpg.Connection, scope: Scope, seafarer_id: int) -> dict:
    row = await conn.fetchrow(
        f"""
        SELECT s.*, {scope.where("s")} AS in_scope
          FROM public.seafarer s
         WHERE s.id = $1
           FOR UPDATE OF s
        """,
        seafarer_id,
    )
    return _in_scope_or_raise(row, seafarer_id)


def _in_scope_or_raise(row: asyncpg.Record | None, seafarer_id: int) -> dict:
    if row is None:
        raise NotFound()
    if not row["in_scope"]:
        raise OutOfScope(TARGET, seafarer_id, seafarer_id)
    found = dict(row)
    del found["in_scope"]
    return found
