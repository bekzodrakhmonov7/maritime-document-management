"""The dashboard's work queues and the managers' fleet totals (FR-20; T5, T10).

Plain reads computed by app/domain.py over rows fetched here: the seafarers
in Scope with their Current Vessel, their document summaries, the required
sets read live, and their upcoming and under-way Assignments. Nothing is
stored and nothing is recorded.

- Missing uses each seafarer's evaluated pair (the Assignment under way's,
  else the held Position with no vessel), as on the seafarer record.
- Starting soon carries each Assignment's readiness counters, computed for
  its own Position and vessel as on the readiness view.
- The totals are fleet-wide counts with no names, for managers and
  administrators alike.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

import asyncpg

from app import domain
from app.domain import (
    Breakdown,
    DashboardFilters,
    DashboardSeafarer,
    DocumentLine,
    RequirementRows,
    StartingSoon,
    VesselRef,
)
from app.scope import Scope, whole_fleet
from app.services import documents, requirements
from app.services.coverage import required_documents


@dataclass(frozen=True)
class _Crew:
    """The seafarers read and their document lines, plus what the starting-soon
    readiness counters need: their unfinished Assignments, their document
    summaries by type, the fleet's requirement rows and the Document Types."""

    seafarers: list[DashboardSeafarer]
    lines: list[DocumentLine]
    assignments: dict[int, list[asyncpg.Record]]
    held: dict[int, dict[int, dict]]
    requirements: RequirementRows
    types: dict[int, dict]


async def _read_crew(conn: asyncpg.Connection, scope: Scope, *, include_inactive: bool) -> _Crew:
    today = scope.today
    inactive = "" if include_inactive else "AND s.inactive_since IS NULL"
    rows = await conn.fetch(
        f"""
        SELECT s.id, s.first_name, s.last_name, s.position_id, p.name AS position_name,
               s.inactive_since IS NOT NULL AS inactive
          FROM public.seafarer s JOIN public.position p ON p.id = s.position_id
         WHERE {scope.where("s")} {inactive}
        """
    )
    ids = [r["id"] for r in rows]
    assignment_rows = await conn.fetch(
        """
        SELECT a.id, a.seafarer_id, a.vessel_id, v.name AS vessel_name, v.flag AS vessel_flag,
               a.position_id, p.name AS position_name, a.start_date, a.end_date, a.cancelled_at
          FROM public.assignment a
          JOIN public.vessel v ON v.id = a.vessel_id
          JOIN public.position p ON p.id = a.position_id
         WHERE a.seafarer_id = ANY($1::bigint[]) AND a.cancelled_at IS NULL AND a.end_date >= $2
        """,
        ids,
        today,
    )
    assignments: dict[int, list[asyncpg.Record]] = {}
    for a in assignment_rows:
        assignments.setdefault(a["seafarer_id"], []).append(a)
    summaries = await documents.summaries_by_seafarer(conn, ids, today)
    held = {sid: {d["document_type_id"]: d for d in docs} for sid, docs in summaries.items()}
    rules = await requirements.fleet_requirement_rows(conn)
    types = {
        t["id"]: dict(t)
        for t in await conn.fetch("SELECT id, name, renewable_at_sea FROM public.document_type")
    }

    seafarers, lines = [], []
    for row in rows:
        own = assignments.get(row["id"], [])
        under_way = domain.current_assignment(own, today)
        seafarers.append(
            DashboardSeafarer(
                id=row["id"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                position_id=row["position_id"],
                position_name=row["position_name"],
                current_vessel_id=None if under_way is None else under_way["vessel_id"],
                current_vessel_name=None if under_way is None else under_way["vessel_name"],
                inactive=row["inactive"],
            )
        )
        docs = held.get(row["id"], {})
        lines += [_held_line(row["id"], d) for d in docs.values() if d["current_version"] is not None]
        missing = domain.missing_documents(
            row["position_id"], own, today, rules,
            {type_id: d["current_version"] for type_id, d in docs.items()},
        )
        lines += [
            DocumentLine(
                seafarer_id=row["id"],
                document_type_id=type_id,
                document_type_name=types[type_id]["name"],
                document_id=docs[type_id]["id"] if type_id in docs else None,
            )
            for type_id in missing
        ]
    return _Crew(seafarers, lines, assignments, held, rules, types)


def _held_line(seafarer_id: int, doc: Mapping[str, Any]) -> DocumentLine:
    current = doc["current_version"]
    return DocumentLine(
        seafarer_id=seafarer_id,
        document_type_id=doc["document_type_id"],
        document_type_name=doc["document_type_name"],
        document_id=doc["id"],
        expiry_date=current["expiry_date"],
        effective_expiry=doc["effective_expiry"],
        capped_by=doc["capped_by"],
        certificate_missing=doc["certificate_missing"],
        expiry_status=doc["expiry_status"],
        review_state=current["review_state"],
    )


def _starting_soon(crew: _Crew, today: date, horizon_days: int) -> list[StartingSoon]:
    """The non-cancelled upcoming Assignments within the horizon, each with the
    readiness counters for its own Position and vessel."""
    people = {s.id: s for s in crew.seafarers}
    found = []
    for seafarer_id, own in crew.assignments.items():
        seafarer = people[seafarer_id]
        for a in own:
            if not domain.starts_soon(a["start_date"], today, horizon_days):
                continue
            vessel = VesselRef(id=a["vessel_id"], flag=a["vessel_flag"])
            types = [crew.types[t] for t in crew.requirements.required(a["position_id"], vessel)]
            view = domain.readiness(
                {
                    **a,
                    "held_position_id": seafarer.position_id,
                    "held_position_name": seafarer.position_name,
                },
                required_documents(types, crew.held.get(seafarer_id, {})),
                today,
            )
            found.append(
                StartingSoon(
                    assignment_id=a["id"],
                    seafarer_id=seafarer_id,
                    vessel_id=a["vessel_id"],
                    vessel_name=a["vessel_name"],
                    position_id=a["position_id"],
                    position_name=a["position_name"],
                    start_date=a["start_date"],
                    end_date=a["end_date"],
                    cancelled=a["cancelled_at"] is not None,
                    counters=view["counters"],
                )
            )
    return found


async def dashboard(conn: asyncpg.Connection, scope: Scope, filters: DashboardFilters) -> dict:
    """The work queues and their counts within the caller's Scope, after the filters."""
    horizon_days = await conn.fetchval("SELECT planning_horizon_days FROM public.settings")
    crew = await _read_crew(conn, scope, include_inactive=filters.show_inactive)
    board = domain.dashboard(
        crew.seafarers,
        crew.lines,
        _starting_soon(crew, scope.today, horizon_days),
        filters,
        scope.today,
        horizon_days,
    )
    return {"today": scope.today, "planning_horizon_days": horizon_days, **board}


async def fleet_totals(conn: asyncpg.Connection, today: date, breakdown: Breakdown) -> dict:
    """Totals per Expiry Status plus Missing for the whole fleet, and one breakdown."""
    crew = await _read_crew(conn, whole_fleet(today), include_inactive=False)
    return {"today": today, **domain.fleet_totals(crew.seafarers, crew.lines, breakdown)}
