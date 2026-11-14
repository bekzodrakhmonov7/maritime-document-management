"""Assignments (FR-06, T3, T5).

An Assignment is read through its seafarer's Scope: outside it, the record is
answered like a missing one (OutOfScope). Its state (upcoming / under way /
finished) is derived from the dates against the Scope's "today"; only
cancelled is stored. Finished and cancelled Assignments are read-only, and the
seafarer never changes. Each change runs in one transaction with its Audit
Record; an edit that changes nothing writes none.

Crewing officers act only on vessels they are a Responsible Officer for:
planning needs the new vessel, editing the old and the new one, cancelling
the Assignment's own. Administrators are unrestricted.
"""

from collections.abc import Mapping
from datetime import date
from typing import Any

import asyncpg

from app import audit, domain
from app.audit import AuditAction, AuditContext
from app.models.assignment import AssignmentStatus
from app.models.auth import UserPayload
from app.scope import Scope
from app.services import reference_data, responsible_officers, seafarers
from app.services.errors import Conflict, Invalid, NotFound, NotResponsible, OutOfScope

TARGET = "assignment"
EDITABLE = ("vessel_id", "position_id", "start_date", "end_date")

_FIELDS = """
           a.id, a.seafarer_id, s.first_name AS seafarer_first_name,
           s.last_name AS seafarer_last_name, a.vessel_id, v.name AS vessel_name,
           a.position_id, p.name AS position_name, s.position_id AS held_position_id,
           a.start_date, a.end_date, a.cancelled_at, a.cancel_reason, a.created_at, a.updated_at
      FROM public.assignment a
      JOIN public.seafarer s ON s.id = a.seafarer_id
      JOIN public.vessel v ON v.id = a.vessel_id
      JOIN public.position p ON p.id = a.position_id
"""


def _select(scope: Scope | None = None) -> str:
    """The Assignment read, plus whether its seafarer is in `scope` when given."""
    in_scope = f"{scope.where('s')} AS in_scope," if scope else ""
    return f"SELECT {in_scope} {_FIELDS}"


def _state(row: Mapping[str, Any], today: date) -> AssignmentStatus:
    if row["cancelled_at"] is not None:
        return "cancelled"
    return domain.assignment_state(row["start_date"], row["end_date"], today)


def _read(row: asyncpg.Record, scope: Scope) -> dict:
    found = dict(row)
    found.pop("in_scope", None)
    found["position_differs"] = found["position_id"] != found.pop("held_position_id")
    found["state"] = _state(found, scope.today)
    return found


async def list_for_seafarer(conn: asyncpg.Connection, scope: Scope, seafarer_id: int) -> list[dict]:
    """Every Assignment of a seafarer in Scope, finished and cancelled ones
    included, latest first."""
    await seafarers.fetch_in_scope(conn, scope, seafarer_id)
    rows = await conn.fetch(
        f"{_select()} WHERE a.seafarer_id = $1 ORDER BY a.start_date DESC, a.id DESC", seafarer_id
    )
    return [_read(r, scope) for r in rows]


async def list_for_vessel(conn: asyncpg.Connection, scope: Scope, vessel_id: int) -> list[dict]:
    """A vessel's crew under way and upcoming, limited to the caller's Scope."""
    await reference_data.get_row(conn, reference_data.VESSEL, vessel_id)
    rows = await conn.fetch(
        f"""
        {_select()}
         WHERE a.vessel_id = $1 AND a.cancelled_at IS NULL AND a.end_date >= $2
           AND {scope.where("s")}
         ORDER BY a.start_date, lower(s.last_name), lower(s.first_name), a.id
        """,
        vessel_id,
        scope.today,
    )
    return [_read(r, scope) for r in rows]


async def get(conn: asyncpg.Connection, scope: Scope, assignment_id: int) -> dict:
    row = await conn.fetchrow(
        f"""
        {_select(scope)}
         WHERE a.id = $1
        """,
        assignment_id,
    )
    _check_in_scope(row, assignment_id)
    return _read(row, scope)


async def _reread(conn: asyncpg.Connection, scope: Scope, assignment_id: int) -> dict:
    """The Assignment just changed. A change may take its seafarer out of the
    caller's Scope (e.g. cancelling their only Assignment on the officer's
    vessel), so the answer to the change itself isn't scoped again."""
    return _read(await conn.fetchrow(f"{_select()} WHERE a.id = $1", assignment_id), scope)


async def create(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    scope: Scope,
    account: UserPayload,
    values: dict[str, Any],
) -> dict:
    """Plan an Assignment for a seafarer in Scope. The seafarer row is locked,
    so setting them Inactive can't cross this."""
    async with conn.transaction():
        seafarer = await seafarers.lock_in_scope(conn, scope, values["seafarer_id"])
        if seafarer["inactive_since"] is not None:
            raise Conflict("The seafarer is Inactive: reactivate them before planning an Assignment.")
        await _require_responsible(conn, account, values["vessel_id"])
        await reference_data.check_pickable(conn, reference_data.VESSEL, values["vessel_id"])
        await reference_data.check_pickable(conn, reference_data.POSITION, values["position_id"])
        columns = ("seafarer_id", *EDITABLE)
        assignment_id = await _write(
            conn,
            f"""
            INSERT INTO public.assignment ({", ".join(columns)})
            VALUES ({", ".join(f"${i}" for i in range(1, len(columns) + 1))})
            RETURNING id
            """,
            *(values[c] for c in columns),
        )
        await audit.record(
            conn, ctx, AuditAction.ASSIGNMENT_CREATED,
            target_type=TARGET, target_id=assignment_id, seafarer_id=values["seafarer_id"],
            after={c: values[c] for c in columns},
        )
        return await _reread(conn, scope, assignment_id)


async def edit(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    scope: Scope,
    account: UserPayload,
    assignment_id: int,
    values: dict[str, Any],
) -> dict:
    """Change the vessel, Position or dates of an Assignment not yet finished."""
    async with conn.transaction():
        current = await _lock_changeable(conn, scope, assignment_id)
        await _require_responsible(conn, account, current["vessel_id"], values["vessel_id"])
        before, after = audit.changed_fields(
            {c: current[c] for c in EDITABLE}, {c: values[c] for c in EDITABLE}
        )
        if not after:
            return await _reread(conn, scope, assignment_id)
        # A vessel or Position switched off since may be kept, not newly picked.
        if "vessel_id" in after:
            await reference_data.check_pickable(conn, reference_data.VESSEL, after["vessel_id"])
        if "position_id" in after:
            await reference_data.check_pickable(conn, reference_data.POSITION, after["position_id"])
        set_clause = ", ".join(f"{c} = ${i}" for i, c in enumerate(after, start=2))
        await _write(
            conn,
            f"UPDATE public.assignment SET {set_clause}, updated_at = now() WHERE id = $1",
            assignment_id,
            *after.values(),
        )
        await audit.record(
            conn, ctx, AuditAction.ASSIGNMENT_EDITED,
            target_type=TARGET, target_id=assignment_id, seafarer_id=current["seafarer_id"],
            before=before, after=after,
        )
        return await _reread(conn, scope, assignment_id)


async def cancel(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    scope: Scope,
    account: UserPayload,
    assignment_id: int,
    reason: str,
) -> dict:
    """Cancel an Assignment not yet finished. It is kept, with the reason."""
    async with conn.transaction():
        current = await _lock_changeable(conn, scope, assignment_id)
        await _require_responsible(conn, account, current["vessel_id"])
        cancelled_at = await conn.fetchval(
            """
            UPDATE public.assignment
               SET cancelled_at = now(), cancel_reason = $2, updated_at = now()
             WHERE id = $1
         RETURNING cancelled_at
            """,
            assignment_id,
            reason,
        )
        await audit.record(
            conn, ctx, AuditAction.ASSIGNMENT_CANCELLED,
            target_type=TARGET, target_id=assignment_id, seafarer_id=current["seafarer_id"],
            before={"cancelled_at": None}, after={"cancelled_at": cancelled_at},
            reason=reason,
        )
        return await _reread(conn, scope, assignment_id)


async def _require_responsible(
    conn: asyncpg.Connection, account: UserPayload, *vessel_ids: int
) -> None:
    if account.role == "administrator":
        return
    responsible_for = await responsible_officers.vessel_ids(conn, account.sub)
    if not set(vessel_ids) <= responsible_for:
        raise NotResponsible("You aren't a Responsible Officer for that vessel.")


async def _lock_changeable(conn: asyncpg.Connection, scope: Scope, assignment_id: int) -> dict:
    """Lock an Assignment in Scope that is neither cancelled nor finished."""
    row = await conn.fetchrow(
        f"""
        SELECT a.*, {scope.where("s")} AS in_scope
          FROM public.assignment a JOIN public.seafarer s ON s.id = a.seafarer_id
         WHERE a.id = $1
           FOR UPDATE OF a
        """,
        assignment_id,
    )
    _check_in_scope(row, assignment_id)
    if row["cancelled_at"] is not None:
        raise Conflict("The Assignment is cancelled.")
    if domain.assignment_state(row["start_date"], row["end_date"], scope.today) == "finished":
        raise Conflict("The Assignment is finished, so it is read-only.")
    return dict(row)


def _check_in_scope(row: asyncpg.Record | None, assignment_id: int) -> None:
    if row is None:
        raise NotFound()
    if not row["in_scope"]:
        raise OutOfScope(TARGET, assignment_id, row["seafarer_id"])


async def _write(conn: asyncpg.Connection, query: str, *args: Any) -> Any:
    try:
        return await conn.fetchval(query, *args)
    except asyncpg.ExclusionViolationError:
        raise Conflict("The seafarer already has an Assignment overlapping these dates.")
    except asyncpg.CheckViolationError:
        raise Invalid("The end date can't be before the start date.")
