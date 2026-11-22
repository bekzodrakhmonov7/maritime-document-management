"""The fleet, Positions and Document Types (FR-05, FR-07, T2, T5).

The three tables share one shape: create, edit, switch a flag (a vessel's
`active`, a Position's or Document Type's `retired`) and, for the latter two,
delete while unused. Each change runs in one transaction with its Audit
Record; an edit that changes nothing writes no record.

The database holds the rules (CHECKs, the depends-on trigger, unique names,
RESTRICT foreign keys); this module turns its refusals into messages.
"""

from dataclasses import dataclass
from typing import Any

import asyncpg

from app import audit
from app.audit import AuditAction, AuditContext
from app.services.errors import Conflict, Invalid, NotFound


@dataclass(frozen=True)
class Table:
    name: str  # SQL table, Audit Record target_type and action prefix
    label: str  # for messages
    writable: tuple[str, ...]
    flag: str  # the boolean set_flag switches: "active" or "retired"

    @property
    def columns(self) -> str:
        return ", ".join(("id", *self.writable, self.flag, "created_at", "updated_at"))

    def action(self, verb: str) -> AuditAction:
        return AuditAction(f"{self.name}_{verb}")


VESSEL = Table("vessel", "vessel", ("name", "imo_number", "flag"), flag="active")
POSITION = Table("position", "Position", ("name",), flag="retired")
DOCUMENT_TYPE = Table(
    "document_type",
    "Document Type",
    ("name", "expires", "max_validity_months", "renewable_at_sea", "depends_on_id"),
    flag="retired",
)

# Messages for the constraints a caller can trip; the depends-on trigger
# raises its own readable messages.
_CONSTRAINT_MESSAGES = {
    "vessel_imo_number_key": "A vessel with that IMO number already exists.",
    "uq_position_name": "A Position with that name already exists.",
    "uq_document_type_name": "A Document Type with that name already exists.",
    "document_type_no_self_dependency": "A Document Type can't depend on itself.",
    "document_type_max_validity_only_when_expires": (
        "A maximum validity is allowed only on a type that expires."
    ),
    "document_type_depends_on_id_fkey": "The Document Type it depends on doesn't exist.",
}

_ALREADY = {
    "deactivated": "already deactivated",
    "reactivated": "already active",
    "retired": "already retired",
    "unretired": "not retired",
}


def _message(exc: asyncpg.PostgresError) -> str:
    constraint = getattr(exc, "constraint_name", None)
    return _CONSTRAINT_MESSAGES.get(constraint or "", exc.args[0] if exc.args else str(exc))


async def _write(conn: asyncpg.Connection, query: str, *args: Any) -> asyncpg.Record:
    """Run an INSERT/UPDATE ... RETURNING, mapping refusals to our errors."""
    try:
        return await conn.fetchrow(query, *args)
    except asyncpg.UniqueViolationError as exc:
        raise Conflict(_message(exc))
    except (asyncpg.CheckViolationError, asyncpg.ForeignKeyViolationError) as exc:
        raise Invalid(_message(exc))


async def list_rows(conn: asyncpg.Connection, table: Table) -> list[dict]:
    rows = await conn.fetch(f"SELECT {table.columns} FROM public.{table.name} ORDER BY lower(name), id")
    return [dict(r) for r in rows]


async def get_row(conn: asyncpg.Connection, table: Table, row_id: int) -> dict:
    row = await conn.fetchrow(f"SELECT {table.columns} FROM public.{table.name} WHERE id = $1", row_id)
    if row is None:
        raise NotFound(f"No such {table.label}.")
    return dict(row)


async def create(
    conn: asyncpg.Connection, ctx: AuditContext, table: Table, values: dict[str, Any]
) -> dict:
    fields = [values[c] for c in table.writable]
    placeholders = ", ".join(f"${i}" for i in range(1, len(fields) + 1))
    async with conn.transaction():
        row = await _write(
            conn,
            f"""
            INSERT INTO public.{table.name} ({", ".join(table.writable)})
            VALUES ({placeholders})
            RETURNING {table.columns}
            """,
            *fields,
        )
        await audit.record(
            conn, ctx, table.action("created"),
            target_type=table.name, target_id=row["id"],
            after={c: row[c] for c in table.writable},
        )
        return dict(row)


async def edit(
    conn: asyncpg.Connection, ctx: AuditContext, table: Table, row_id: int, values: dict[str, Any]
) -> dict:
    async with conn.transaction():
        current = await _lock(conn, table, row_id)
        before, after = audit.changed_fields(
            {c: current[c] for c in table.writable}, {c: values[c] for c in table.writable}
        )
        if not after:
            return dict(current)
        assignments = ", ".join(f"{c} = ${i}" for i, c in enumerate(after, start=2))
        row = await _write(
            conn,
            f"""
            UPDATE public.{table.name} SET {assignments}, updated_at = now()
             WHERE id = $1
         RETURNING {table.columns}
            """,
            row_id,
            *after.values(),
        )
        await audit.record(
            conn, ctx, table.action("edited"),
            target_type=table.name, target_id=row_id, before=before, after=after,
        )
        return dict(row)


async def set_flag(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    table: Table,
    row_id: int,
    value: bool,
    verb: str,
) -> dict:
    """Deactivate/reactivate a vessel, or retire/unretire a Position or Document Type."""
    async with conn.transaction():
        current = await _lock(conn, table, row_id)
        if current[table.flag] == value:
            raise Conflict(f"The {table.label} is {_ALREADY[verb]}.")
        row = await conn.fetchrow(
            f"""
            UPDATE public.{table.name} SET {table.flag} = $2, updated_at = now()
             WHERE id = $1
         RETURNING {table.columns}
            """,
            row_id,
            value,
        )
        await audit.record(
            conn, ctx, table.action(verb),
            target_type=table.name, target_id=row_id,
            before={table.flag: current[table.flag]}, after={table.flag: value},
        )
        return dict(row)


async def delete(conn: asyncpg.Connection, ctx: AuditContext, table: Table, row_id: int) -> None:
    """Delete a row nothing refers to; a used one must be retired instead."""
    async with conn.transaction():
        current = await _lock(conn, table, row_id)
        try:
            await conn.execute(f"DELETE FROM public.{table.name} WHERE id = $1", row_id)
        except asyncpg.ForeignKeyViolationError:
            raise Conflict(f"This {table.label} is in use, so it can't be deleted: retire it instead.")
        await audit.record(
            conn, ctx, table.action("deleted"),
            target_type=table.name, target_id=row_id,
            before={c: current[c] for c in (*table.writable, table.flag)},
        )


_UNPICKABLE = {
    "active": "deactivated: pick an active one",
    "retired": "retired: pick one from the current list",
}


async def check_pickable(conn: asyncpg.Connection, table: Table, row_id: int) -> None:
    """Only an active vessel, or a Position or Document Type that isn't retired,
    can be picked for a new choice. The row is locked so it can't be switched
    off or deleted until the caller's change commits."""
    flag = await conn.fetchval(
        f"SELECT {table.flag} FROM public.{table.name} WHERE id = $1 FOR SHARE", row_id
    )
    if flag is None:
        raise Invalid(f"That {table.label} doesn't exist.")
    if flag != (table.flag == "active"):
        raise Invalid(f"That {table.label} is {_UNPICKABLE[table.flag]}.")


async def _lock(conn: asyncpg.Connection, table: Table, row_id: int) -> asyncpg.Record:
    row = await conn.fetchrow(
        f"SELECT {table.columns} FROM public.{table.name} WHERE id = $1 FOR UPDATE", row_id
    )
    if row is None:
        raise NotFound(f"No such {table.label}.")
    return row
