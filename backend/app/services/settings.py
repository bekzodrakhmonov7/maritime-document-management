"""The one Settings row (FR-25, T9).

Nothing is cached: every request reads the row, so a saved change applies
from the next request or the next daily run without a restart.

A save names the version it started from. Under the row lock a stale version
is refused, so two administrators can't overwrite each other. A save that
changes something bumps the version and writes one *settings changed* Audit
Record with the changed fields only; a save that changes nothing writes none.
"""

from datetime import date, time
from typing import Any
from uuid import UUID

import asyncpg

from app import audit, domain
from app.audit import AuditAction, AuditContext
from app.models.settings import EDITABLE
from app.services import retention

_COLUMNS = ", ".join((*EDITABLE, "version", "updated_at"))
_SELECT = f"SELECT {_COLUMNS} FROM public.settings"


class StaleVersion(Exception):
    pass


def _as_dict(row: asyncpg.Record) -> dict[str, Any]:
    """The row as API values: the check time `time` column becomes "HH:MM"."""
    values = dict(row)
    values["daily_check_time"] = values["daily_check_time"].strftime("%H:%M")
    return values


def _column_value(column: str, value: Any) -> Any:
    """An API value as its column takes it: "HH:MM" becomes a `time`."""
    return time.fromisoformat(value) if column == "daily_check_time" else value


async def get(conn: asyncpg.Connection) -> dict[str, Any]:
    """The current settings, with the check time as "HH:MM"."""
    return _as_dict(await conn.fetchrow(_SELECT))


async def with_last_cleanup(conn: asyncpg.Connection, values: dict[str, Any]) -> dict[str, Any]:
    """The settings plus what the last retention clean-ups removed."""
    return {
        **values,
        "last_cleanup": await retention.last_cleanup(conn),
        "last_audit_cleanup": await retention.last_audit_cleanup(conn),
    }


async def save(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    actor_id: UUID,
    values: dict[str, Any],
    version: int,
) -> dict[str, Any]:
    async with conn.transaction():
        current = _as_dict(await conn.fetchrow(f"{_SELECT} FOR UPDATE"))
        if current["version"] != version:
            raise StaleVersion()
        before, after = audit.changed_fields(
            {c: current[c] for c in EDITABLE}, {c: values[c] for c in EDITABLE}
        )
        if not after:
            return current

        params = [_column_value(c, v) for c, v in after.items()]
        assignments = ", ".join(f"{c} = ${i}" for i, c in enumerate(after, start=2))
        row = await conn.fetchrow(
            f"""
            UPDATE public.settings
               SET {assignments}, version = version + 1, updated_at = now(), updated_by = $1
         RETURNING {_COLUMNS}
            """,
            actor_id,
            *params,
        )
        await audit.record(
            conn, ctx, AuditAction.SETTINGS_CHANGED,
            target_type="settings", before=before, after=after,
        )
        return _as_dict(row)


async def company_today(conn: asyncpg.Connection) -> date:
    """Today's date in the configured company time zone."""
    return domain.today_in(await conn.fetchval("SELECT time_zone FROM public.settings"))
