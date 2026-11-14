"""The one Settings row (FR-25, T9).

Nothing is cached: every request reads the row, so a saved change applies
from the next request or the next daily run without a restart.

A save names the version it started from. Under the row lock a stale version
is refused, so two administrators can't overwrite each other. A save that
changes something bumps the version and writes one *settings changed* Audit
Record with the changed fields only; a save that changes nothing writes none.
"""

from datetime import time
from typing import Any
from uuid import UUID

import asyncpg

from app import audit
from app.audit import AuditAction, AuditContext
from app.models.settings import EDITABLE

_COLUMNS = ", ".join((*EDITABLE, "version", "updated_at"))


class StaleVersion(Exception):
    pass


def _hh_mm(value: time) -> str:
    return value.strftime("%H:%M")


def _as_dict(row: asyncpg.Record) -> dict[str, Any]:
    values = dict(row)
    values["daily_check_time"] = _hh_mm(values["daily_check_time"])
    return values


async def get(conn: asyncpg.Connection) -> dict[str, Any]:
    """The current settings, with the check time as "HH:MM"."""
    return _as_dict(await conn.fetchrow(f"SELECT {_COLUMNS} FROM public.settings"))


async def save(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    actor_id: UUID,
    values: dict[str, Any],
    version: int,
) -> dict[str, Any]:
    async with conn.transaction():
        current = _as_dict(
            await conn.fetchrow(f"SELECT {_COLUMNS} FROM public.settings FOR UPDATE")
        )
        if current["version"] != version:
            raise StaleVersion()
        before, after = audit.changed_fields(
            {c: current[c] for c in EDITABLE}, {c: values[c] for c in EDITABLE}
        )
        if not after:
            return current

        params = [
            time.fromisoformat(v) if c == "daily_check_time" else v for c, v in after.items()
        ]
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
