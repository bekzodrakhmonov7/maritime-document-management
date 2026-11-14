"""Requirements: the Position Requirement matrix and its exceptions (FR-08, T2).

The matrix says which Document Types each Position needs. An exception adds
or removes one type for one vessel or one flag, for one Position or all of
them, with a reason. The required set itself is computed by
`app.domain.required_set` over rows read live, so a change counts from the
next request.

Each change runs in one transaction with its Audit Record. Setting a cell
that is already set, clearing one that isn't, and an edit that changes
nothing write no record. Only a non-retired Position or Document Type and an
active vessel can be newly picked; an exception may keep one retired since.
"""

from collections.abc import Iterable, Mapping
from typing import Any

import asyncpg

from app import audit
from app.audit import AuditAction, AuditContext
from app.domain import (
    RequirementException,
    RequirementRows,
    VesselRef,
    deciding_exceptions,
    required_set,
)
from app.services.errors import Conflict, Invalid, NotFound

MATRIX_TARGET = "position_requirement"
EXCEPTION_TARGET = "requirement_exception"
EXCEPTION_WRITABLE = ("vessel_id", "flag", "position_id", "document_type_id", "effect", "reason")

_EXCEPTION_COLUMNS = """
    e.id, e.vessel_id, v.name AS vessel_name, e.flag,
    e.position_id, p.name AS position_name,
    e.document_type_id, t.name AS document_type_name,
    e.effect, e.reason, e.created_at, e.updated_at
"""
_EXCEPTION_FROM = """
    public.requirement_exception e
    JOIN public.document_type t ON t.id = e.document_type_id
    LEFT JOIN public.position p ON p.id = e.position_id
    LEFT JOIN public.vessel v ON v.id = e.vessel_id
"""
_EXCEPTION_ORDER = """
    ORDER BY e.flag NULLS LAST, lower(v.name), lower(p.name) NULLS FIRST, lower(t.name), e.id
"""


# --- Picking reference rows ------------------------------------------------------

# table -> (label, SQL that is true when the row can't be newly picked, why)
_PICKABLE = {
    "position": ("Position", "retired", "is retired"),
    "document_type": ("Document Type", "retired", "is retired"),
    "vessel": ("vessel", "NOT active", "is not active"),
}


async def _check_pickable(
    conn: asyncpg.Connection, table: str, row_id: int, *, missing: type[Exception]
) -> None:
    """Lock the row against a concurrent retire; refuse it if it can't be picked.

    `missing` is raised for an unknown id: NotFound when it came in the path,
    Invalid when it came in a body.
    """
    label, unpickable, why = _PICKABLE[table]
    refused = await conn.fetchval(
        f"SELECT {unpickable} FROM public.{table} WHERE id = $1 FOR SHARE", row_id
    )
    if refused is None:
        raise missing(f"No such {label}.")
    if refused:
        raise Invalid(f"The {label} {why}, so it can't be picked.")


# --- The matrix ------------------------------------------------------------------


async def get_matrix(conn: asyncpg.Connection) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT position_id, document_type_id FROM public.position_requirement
         ORDER BY position_id, document_type_id
        """
    )
    return [dict(r) for r in rows]


def _cell_target(position_id: int, document_type_id: int) -> str:
    return f"{position_id}/{document_type_id}"


async def _record_cell(
    conn: asyncpg.Connection, ctx: AuditContext, action: AuditAction, position_id: int, type_id: int
) -> None:
    cell = {"position_id": position_id, "document_type_id": type_id}
    added = action == AuditAction.REQUIREMENT_ADDED
    await audit.record(
        conn, ctx, action,
        target_type=MATRIX_TARGET, target_id=_cell_target(position_id, type_id),
        before=None if added else cell, after=cell if added else None,
    )


async def set_requirement(
    conn: asyncpg.Connection, ctx: AuditContext, position_id: int, document_type_id: int
) -> None:
    async with conn.transaction():
        await _check_pickable(conn, "position", position_id, missing=NotFound)
        await _check_pickable(conn, "document_type", document_type_id, missing=NotFound)
        added = await conn.fetchval(
            """
            INSERT INTO public.position_requirement (position_id, document_type_id)
            VALUES ($1, $2) ON CONFLICT DO NOTHING RETURNING true
            """,
            position_id,
            document_type_id,
        )
        if added:
            await _record_cell(conn, ctx, AuditAction.REQUIREMENT_ADDED, position_id, document_type_id)


async def clear_requirement(
    conn: asyncpg.Connection, ctx: AuditContext, position_id: int, document_type_id: int
) -> None:
    """Clearing a cell never touches other cells: an Endorsement's requirement
    stays when its certificate's goes."""
    async with conn.transaction():
        removed = await conn.fetchval(
            """
            DELETE FROM public.position_requirement
             WHERE position_id = $1 AND document_type_id = $2
            RETURNING true
            """,
            position_id,
            document_type_id,
        )
        if removed:
            await _record_cell(conn, ctx, AuditAction.REQUIREMENT_REMOVED, position_id, document_type_id)


async def add_to_all_positions(
    conn: asyncpg.Connection, ctx: AuditContext, document_type_id: int
) -> list[int]:
    """Require the type for every non-retired Position; returns those that got it."""
    async with conn.transaction():
        await _check_pickable(conn, "document_type", document_type_id, missing=Invalid)
        positions = await conn.fetch(
            "SELECT id FROM public.position WHERE NOT retired ORDER BY id FOR SHARE"
        )
        added = await conn.fetch(
            """
            INSERT INTO public.position_requirement (position_id, document_type_id)
            SELECT unnest($1::bigint[]), $2
            ON CONFLICT DO NOTHING
            RETURNING position_id
            """,
            [p["id"] for p in positions],
            document_type_id,
        )
        position_ids = sorted(r["position_id"] for r in added)
        for position_id in position_ids:
            await _record_cell(conn, ctx, AuditAction.REQUIREMENT_ADDED, position_id, document_type_id)
        return position_ids


# --- Exceptions ------------------------------------------------------------------

_CONSTRAINT_MESSAGES = {
    "uq_requirement_exception": (
        "An exception for that vessel or flag, Position and Document Type already exists: edit it instead."
    ),
    "requirement_exception_one_scope": "Give exactly one of a vessel or a flag.",
}


async def _write(conn: asyncpg.Connection, query: str, *args: Any) -> Any:
    try:
        return await conn.fetchval(query, *args)
    except asyncpg.UniqueViolationError as exc:
        raise Conflict(_CONSTRAINT_MESSAGES.get(exc.constraint_name or "", str(exc)))
    except (asyncpg.CheckViolationError, asyncpg.ForeignKeyViolationError) as exc:
        raise Invalid(_CONSTRAINT_MESSAGES.get(exc.constraint_name or "", str(exc)))


async def _check_picks(conn: asyncpg.Connection, values: dict[str, Any]) -> None:
    """Check the reference rows among `values` (only those being newly picked)."""
    for column, table in (
        ("vessel_id", "vessel"),
        ("position_id", "position"),
        ("document_type_id", "document_type"),
    ):
        if values.get(column) is not None:
            await _check_pickable(conn, table, values[column], missing=Invalid)


async def list_exceptions(conn: asyncpg.Connection) -> list[dict]:
    rows = await conn.fetch(f"SELECT {_EXCEPTION_COLUMNS} FROM {_EXCEPTION_FROM} {_EXCEPTION_ORDER}")
    return [dict(r) for r in rows]


async def _fetch_exception(conn: asyncpg.Connection, exception_id: int) -> dict:
    row = await conn.fetchrow(
        f"SELECT {_EXCEPTION_COLUMNS} FROM {_EXCEPTION_FROM} WHERE e.id = $1", exception_id
    )
    return dict(row)


async def _lock_exception(conn: asyncpg.Connection, exception_id: int) -> asyncpg.Record:
    row = await conn.fetchrow(
        f"""
        SELECT {", ".join(EXCEPTION_WRITABLE)} FROM public.requirement_exception
         WHERE id = $1 FOR UPDATE
        """,
        exception_id,
    )
    if row is None:
        raise NotFound("No such exception.")
    return row


async def create_exception(
    conn: asyncpg.Connection, ctx: AuditContext, values: dict[str, Any]
) -> dict:
    async with conn.transaction():
        await _check_picks(conn, values)
        exception_id = await _write(
            conn,
            f"""
            INSERT INTO public.requirement_exception ({", ".join(EXCEPTION_WRITABLE)})
            VALUES ({", ".join(f"${i}" for i in range(1, len(EXCEPTION_WRITABLE) + 1))})
            RETURNING id
            """,
            *(values[c] for c in EXCEPTION_WRITABLE),
        )
        await audit.record(
            conn, ctx, AuditAction.REQUIREMENT_EXCEPTION_CREATED,
            target_type=EXCEPTION_TARGET, target_id=exception_id,
            after={c: values[c] for c in EXCEPTION_WRITABLE},
        )
        return await _fetch_exception(conn, exception_id)


async def edit_exception(
    conn: asyncpg.Connection, ctx: AuditContext, exception_id: int, values: dict[str, Any]
) -> dict:
    async with conn.transaction():
        current = await _lock_exception(conn, exception_id)
        before, after = audit.changed_fields(
            {c: current[c] for c in EXCEPTION_WRITABLE}, {c: values[c] for c in EXCEPTION_WRITABLE}
        )
        if after:
            await _check_picks(conn, after)
            assignments = ", ".join(f"{c} = ${i}" for i, c in enumerate(after, start=2))
            await _write(
                conn,
                f"""
                UPDATE public.requirement_exception SET {assignments}, updated_at = now()
                 WHERE id = $1
                RETURNING id
                """,
                exception_id,
                *after.values(),
            )
            await audit.record(
                conn, ctx, AuditAction.REQUIREMENT_EXCEPTION_EDITED,
                target_type=EXCEPTION_TARGET, target_id=exception_id, before=before, after=after,
            )
        return await _fetch_exception(conn, exception_id)


async def delete_exception(conn: asyncpg.Connection, ctx: AuditContext, exception_id: int) -> None:
    async with conn.transaction():
        current = await _lock_exception(conn, exception_id)
        await conn.execute("DELETE FROM public.requirement_exception WHERE id = $1", exception_id)
        await audit.record(
            conn, ctx, AuditAction.REQUIREMENT_EXCEPTION_DELETED,
            target_type=EXCEPTION_TARGET, target_id=exception_id,
            before={c: current[c] for c in EXCEPTION_WRITABLE},
        )


# --- The required set --------------------------------------------------------------


async def _matrix_pairs(conn: asyncpg.Connection, position_id: int) -> list[tuple[int, int]]:
    rows = await conn.fetch(
        "SELECT position_id, document_type_id FROM public.position_requirement WHERE position_id = $1",
        position_id,
    )
    return [(r["position_id"], r["document_type_id"]) for r in rows]


async def _exception_rows(
    conn: asyncpg.Connection, position_id: int, vessel: VesselRef | None
) -> list[asyncpg.Record]:
    """The exceptions that can speak about this pair; with no vessel, none."""
    if vessel is None:
        return []
    return await conn.fetch(
        f"""
        SELECT {_EXCEPTION_COLUMNS} FROM {_EXCEPTION_FROM}
         WHERE (e.position_id IS NULL OR e.position_id = $1)
           AND (e.vessel_id = $2 OR e.flag = $3)
        """,
        position_id,
        vessel.id,
        vessel.flag,
    )


def _as_exception(row: Mapping[str, Any]) -> RequirementException:
    return RequirementException(
        id=row["id"],
        document_type_id=row["document_type_id"],
        effect=row["effect"],
        vessel_id=row["vessel_id"],
        flag=row["flag"],
        position_id=row["position_id"],
    )


async def requirement_rows(
    conn: asyncpg.Connection, position_id: int, vessel: VesselRef | None
) -> RequirementRows:
    """The rows the required set of this pair is decided by, read live."""
    return RequirementRows(
        matrix=await _matrix_pairs(conn, position_id),
        exceptions=[_as_exception(r) for r in await _exception_rows(conn, position_id, vessel)],
        retired_types=[
            r["id"] for r in await conn.fetch("SELECT id FROM public.document_type WHERE retired")
        ],
    )


async def fleet_requirement_rows(conn: asyncpg.Connection) -> RequirementRows:
    """Every matrix row and exception, for the required sets of many pairs at
    once (the dashboard); `RequirementRows.required` picks what applies."""
    matrix = await conn.fetch("SELECT position_id, document_type_id FROM public.position_requirement")
    return RequirementRows(
        matrix=[(r["position_id"], r["document_type_id"]) for r in matrix],
        exceptions=[
            _as_exception(r)
            for r in await conn.fetch(f"SELECT {_EXCEPTION_COLUMNS} FROM {_EXCEPTION_FROM}")
        ],
        retired_types=[
            r["id"] for r in await conn.fetch("SELECT id FROM public.document_type WHERE retired")
        ],
    )


async def document_types(conn: asyncpg.Connection, type_ids: Iterable[int]) -> list[dict]:
    """Document Types by name: id, name and the renewable-at-sea rule."""
    rows = await conn.fetch(
        """
        SELECT id, name, renewable_at_sea FROM public.document_type
         WHERE id = ANY($1::bigint[]) ORDER BY lower(name), id
        """,
        list(type_ids),
    )
    return [dict(r) for r in rows]


# --- The preview -------------------------------------------------------------------


async def evaluate(conn: asyncpg.Connection, position_id: int, vessel_id: int | None) -> dict:
    """The required set for a Position on a vessel, or with no vessel (matrix only)."""
    if await conn.fetchval("SELECT id FROM public.position WHERE id = $1", position_id) is None:
        raise NotFound("No such Position.")
    vessel = None
    if vessel_id is not None:
        row = await conn.fetchrow("SELECT id, name, flag FROM public.vessel WHERE id = $1", vessel_id)
        if row is None:
            raise NotFound("No such vessel.")
        vessel = dict(row)

    vessel_ref = None if vessel is None else VesselRef(id=vessel["id"], flag=vessel["flag"])
    exception_rows = await _exception_rows(conn, position_id, vessel_ref)
    exceptions = [_as_exception(r) for r in exception_rows]
    types = await conn.fetch("SELECT id, name, retired FROM public.document_type")
    required = required_set(
        position_id,
        vessel_ref,
        await _matrix_pairs(conn, position_id),
        exceptions,
        {t["id"] for t in types if t["retired"]},
    )
    deciding = deciding_exceptions(position_id, vessel_ref, exceptions)
    names = {t["id"]: t["name"] for t in types}
    applied_ids = {e.id for e in deciding.values()}

    def by_name(type_id: int) -> tuple[str, int]:
        return names[type_id].lower(), type_id

    def adding_exception_id(type_id: int) -> int | None:
        e = deciding.get(type_id)
        return e.id if e is not None and e.effect == "add" else None

    return {
        "position_id": position_id,
        "vessel": vessel,
        "required": [
            {
                "id": type_id,
                "name": names[type_id],
                "exception_id": adding_exception_id(type_id),
            }
            for type_id in sorted(required, key=by_name)
        ],
        "applied_exceptions": sorted(
            (dict(r) for r in exception_rows if r["id"] in applied_ids),
            key=lambda r: by_name(r["document_type_id"]),
        ),
    }
