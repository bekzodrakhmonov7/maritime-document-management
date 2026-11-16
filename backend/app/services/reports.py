"""Status Reports (FR-21, T12, T5, T7).

Both kinds are built from `coverage.readiness`, so a report is the readiness
view frozen, as of today in the company time zone:

- assignment report: one upcoming or under-way Assignment in Scope (finished,
  cancelled and out-of-Scope ones answer like a missing one);
- vessel report: every non-cancelled Assignment on the vessel under way
  today or starting within the Planning Horizon. Administrators get any
  vessel; a crewing officer only one they are a Responsible Officer for
  (otherwise 404, recorded as refused access), and only seafarers in Scope.

Each generated report writes one *report generated* Audit Record (actor,
vessel or assignment, format) in the transaction that builds it: no record,
no report.
"""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import asyncpg

from app import audit, domain
from app.audit import AuditAction, AuditContext
from app.models.auth import UserPayload
from app.reports import ReportFormat, ReportKind, ReportSection, StatusReport, to_csv, to_pdf
from app.scope import Scope
from app.services import coverage, reference_data, responsible_officers
from app.services.errors import OutOfScope

MEDIA_TYPES: dict[ReportFormat, str] = {"pdf": "application/pdf", "csv": "text/csv; charset=utf-8"}


@dataclass(frozen=True)
class RenderedReport:
    content: bytes
    media_type: str
    filename: str


def _generated_by(account: UserPayload) -> str:
    return f"{account.full_name} ({account.email})" if account.full_name else account.email


async def _report(
    conn: asyncpg.Connection,
    account: UserPayload,
    scope: Scope,
    kind: ReportKind,
    vessel: dict,
    sections: list[ReportSection],
) -> StatusReport:
    zone = ZoneInfo(await conn.fetchval("SELECT time_zone FROM public.settings"))
    return StatusReport(
        kind=kind,
        vessel_name=vessel["name"],
        vessel_flag=vessel["flag"],
        today=scope.today,
        generated_at=datetime.now(zone).replace(microsecond=0),
        generated_by=_generated_by(account),
        sections=sections,
    )


def _render(report: StatusReport, target_id: int, fmt: ReportFormat) -> RenderedReport:
    content = to_pdf(report) if fmt == "pdf" else to_csv(report).encode("utf-8")
    return RenderedReport(content, MEDIA_TYPES[fmt], report.filename(target_id, fmt))


async def _section(conn: asyncpg.Connection, scope: Scope, assignment_id: int) -> ReportSection:
    found = await coverage.readiness(conn, scope, assignment_id)
    assignment = found.pop("assignment")
    return ReportSection(assignment=assignment, view=found)


async def assignment_report(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    account: UserPayload,
    scope: Scope,
    assignment_id: int,
    fmt: ReportFormat,
) -> RenderedReport:
    async with conn.transaction():
        section = await _section(conn, scope, assignment_id)
        a = section.assignment
        vessel = {"name": a["vessel_name"], "flag": a["vessel_flag"]}
        rendered = _render(
            await _report(conn, account, scope, "assignment", vessel, [section]), assignment_id, fmt
        )
        await audit.record(
            conn, ctx, AuditAction.REPORT_GENERATED,
            target_type="assignment", target_id=assignment_id, seafarer_id=a["seafarer_id"],
            after={"kind": "assignment", "format": fmt},
        )
    return rendered


async def _report_assignment_ids(
    conn: asyncpg.Connection, scope: Scope, vessel_id: int
) -> list[int]:
    """The vessel's Assignments under way today or starting within the
    Planning Horizon, not cancelled, with their seafarer in Scope."""
    horizon_days = await conn.fetchval("SELECT planning_horizon_days FROM public.settings")
    rows = await conn.fetch(
        f"""
        SELECT a.id, a.start_date, a.end_date
          FROM public.assignment a JOIN public.seafarer s ON s.id = a.seafarer_id
         WHERE a.vessel_id = $1 AND a.cancelled_at IS NULL AND a.end_date >= $2
           AND {scope.where("s")}
         ORDER BY a.start_date, lower(s.last_name), lower(s.first_name), a.id
        """,
        vessel_id,
        scope.today,
    )
    return [
        r["id"]
        for r in rows
        if domain.assignment_state(r["start_date"], r["end_date"], scope.today) == "under_way"
        or domain.starts_soon(r["start_date"], scope.today, horizon_days)
    ]


async def vessel_report(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    account: UserPayload,
    scope: Scope,
    vessel_id: int,
    fmt: ReportFormat,
) -> RenderedReport:
    async with conn.transaction():
        vessel = await reference_data.get_row(conn, reference_data.VESSEL, vessel_id)
        if account.role != "administrator" and vessel_id not in await responsible_officers.vessel_ids(
            conn, account.sub
        ):
            raise OutOfScope("vessel", vessel_id, seafarer_id=None)
        sections = [
            await _section(conn, scope, assignment_id)
            for assignment_id in await _report_assignment_ids(conn, scope, vessel_id)
        ]
        rendered = _render(
            await _report(conn, account, scope, "vessel", vessel, sections), vessel_id, fmt
        )
        await audit.record(
            conn, ctx, AuditAction.REPORT_GENERATED,
            target_type="vessel", target_id=vessel_id,
            after={"kind": "vessel", "format": fmt, "assignments": len(sections)},
        )
    return rendered
