"""Searching and exporting the Audit Log (FR-23, T7, ADR 0002).

Reading the log is itself recorded: each search writes *audit searched* and
each export *audit exported*, in the same transaction as the read and after
it, so a search never finds its own record. The log is only ever read here;
the app's database role cannot change or remove it.

Date-range filters are whole days in the company time zone, and so are the
exported timestamps.
"""

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

from app import audit
from app.audit import AuditAction, AuditContext
from app.models.audit_log import AuditFilters

EXPORT_CAP = 50_000

COLUMNS = (
    "id",
    "occurred_at",
    "actor_id",
    "actor_email",
    "actor_role",
    "action",
    "outcome",
    "target_type",
    "target_id",
    "seafarer_id",
    "before",
    "after",
    "reason",
    "ip",
    "request_id",
)

_SELECT = f"SELECT {', '.join(COLUMNS)} FROM public.audit_log"
_ORDER = "ORDER BY occurred_at DESC, id DESC"
# A local calendar day as instants in the company time zone: where it starts,
# and where the next day starts.
_ZONE = "(SELECT time_zone FROM public.settings)"
_DAY_START = f"(({{}}::date)::timestamp AT TIME ZONE {_ZONE})"
_NEXT_DAY_START = f"(({{}}::date + 1)::timestamp AT TIME ZONE {_ZONE})"

# A cell starting with one of these is a formula to a spreadsheet.
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class Export:
    csv: str
    rows: int
    truncated: bool


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _where(filters: AuditFilters) -> tuple[str, list[Any]]:
    """The filters as one SQL condition and its parameters."""
    conditions: list[str] = []
    params: list[Any] = []

    def add(condition: str, value: Any) -> None:
        params.append(value)
        conditions.append(condition.format(f"${len(params)}"))

    if filters.date_from is not None:
        add(f"occurred_at >= {_DAY_START}", filters.date_from)
    if filters.date_to is not None:
        add(f"occurred_at < {_NEXT_DAY_START}", filters.date_to)
    if filters.actor_id is not None:
        add("actor_id = {}", filters.actor_id)
    if filters.actor_email:
        add("actor_email ILIKE '%' || {} || '%'", _escape_like(filters.actor_email))
    if filters.action:
        add("action = ANY({}::text[])", [a.value for a in filters.action])
    if filters.seafarer_id is not None:
        add("seafarer_id = {}", filters.seafarer_id)
    if filters.target_type:
        add("target_type = {}", filters.target_type)
    if filters.target_id:
        add("target_id = {}", filters.target_id)
    if filters.outcome is not None:
        add("outcome = {}", filters.outcome)

    return (f"WHERE {' AND '.join(conditions)}" if conditions else ""), params


def _as_dict(row: asyncpg.Record) -> dict[str, Any]:
    values = dict(row)
    for key in ("before", "after"):
        if values[key] is not None:
            values[key] = json.loads(values[key])
    if values["ip"] is not None:
        values["ip"] = str(values["ip"])
    return values


async def _time_zone(conn: asyncpg.Connection) -> str:
    return await conn.fetchval("SELECT time_zone FROM public.settings")


async def search(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    filters: AuditFilters,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """One page of matching records, newest first, plus the total."""
    where, params = _where(filters)
    async with conn.transaction():
        total = await conn.fetchval(f"SELECT count(*) FROM public.audit_log {where}", *params)
        rows = await conn.fetch(
            f"{_SELECT} {where} {_ORDER} LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
            *params,
            page_size,
            (page - 1) * page_size,
        )
        await audit.record(
            conn, ctx, AuditAction.AUDIT_SEARCHED,
            target_type="audit_log",
            after={"filters": filters.given(), "page": page, "results": total},
        )
        time_zone = await _time_zone(conn)
    return {
        "items": [_as_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "time_zone": time_zone,
    }


def _cell(value: Any, zone: ZoneInfo) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(zone).isoformat(sep=" ", timespec="seconds")
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    text = str(value)
    return f"'{text}" if text.startswith(_FORMULA_STARTS) else text


async def export(conn: asyncpg.Connection, ctx: AuditContext, filters: AuditFilters) -> Export:
    """Every matching record up to EXPORT_CAP, newest first, as CSV with
    timestamps in the company time zone."""
    where, params = _where(filters)
    cap = EXPORT_CAP
    async with conn.transaction():
        rows = await conn.fetch(
            f"{_SELECT} {where} {_ORDER} LIMIT ${len(params) + 1}", *params, cap + 1
        )
        truncated = len(rows) > cap
        rows = rows[:cap]
        await audit.record(
            conn, ctx, AuditAction.AUDIT_EXPORTED,
            target_type="audit_log",
            after={"filters": filters.given(), "rows": len(rows), "truncated": truncated},
        )
        zone = ZoneInfo(await _time_zone(conn))

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(COLUMNS)
    for row in rows:
        values = _as_dict(row)
        writer.writerow([_cell(values[c], zone) for c in COLUMNS])
    return Export(csv=out.getvalue(), rows=len(rows), truncated=truncated)
