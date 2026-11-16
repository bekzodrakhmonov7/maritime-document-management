"""Missing documents and the readiness view (FR-17, FR-18, FR-19; T3, T4).

Both are plain reads computed by app/domain.py over rows fetched here:
requirements read live, and each Document's Current Version, review state
and Verified flag from the document summaries. Nothing is stored, and
nothing is recorded except refused access.

- Missing documents use the Assignment under way's Position and vessel,
  otherwise the held Position with no vessel.
- The readiness view uses the Assignment's own Position and vessel, and
  exists only for non-cancelled, unfinished Assignments within Scope.
"""

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

import asyncpg

from app import domain
from app.domain import RequiredDocument, VesselRef
from app.scope import Scope
from app.services import assignments, documents, requirements
from app.services.errors import NotFound


async def _held_documents(conn: asyncpg.Connection, seafarer_id: int, today: date) -> dict[int, dict]:
    """The seafarer's document summaries by Document Type."""
    summaries = await documents.summaries_for(conn, seafarer_id, today)
    return {d["document_type_id"]: d for d in summaries}


def required_documents(
    types: Iterable[Mapping[str, Any]], held: Mapping[int, Mapping[str, Any]]
) -> list[RequiredDocument]:
    """Each required Document Type (id, name, renewable at sea) with what the
    seafarer holds of it, from their document summaries by type."""
    required = []
    for t in types:
        doc = held.get(t["id"])
        current = None if doc is None else doc["current_version"]
        required.append(
            RequiredDocument(
                document_type_id=t["id"],
                name=t["name"],
                renewable_at_sea=t["renewable_at_sea"],
                document_id=None if doc is None else doc["id"],
                current_version=current,
                review_state=None if current is None else current["review_state"],
                verified=doc is not None and doc["verified"],
                effective=None if doc is None else doc["effective"],
            )
        )
    return required


async def _required_documents(
    conn: asyncpg.Connection,
    seafarer_id: int,
    position_id: int,
    vessel: VesselRef | None,
    today: date,
) -> list[RequiredDocument]:
    """The required Document Types for the pair, each with what the seafarer holds."""
    rows = await requirements.requirement_rows(conn, position_id, vessel)
    held = await _held_documents(conn, seafarer_id, today)
    types = await requirements.document_types(conn, rows.required(position_id, vessel))
    return required_documents(types, held)


async def missing_documents(conn: asyncpg.Connection, seafarer: dict, today: date) -> list[dict]:
    """The required documents a seafarer in Scope has no Current Version of, by name."""
    under_way_or_upcoming = await conn.fetch(
        """
        SELECT a.position_id, a.vessel_id, v.flag AS vessel_flag,
               a.start_date, a.end_date, a.cancelled_at
          FROM public.assignment a JOIN public.vessel v ON v.id = a.vessel_id
         WHERE a.seafarer_id = $1 AND a.cancelled_at IS NULL AND a.end_date >= $2
        """,
        seafarer["id"],
        today,
    )
    held_position_id = seafarer["position_id"]
    position_id, vessel = domain.evaluated_pair(held_position_id, under_way_or_upcoming, today)
    held = await _held_documents(conn, seafarer["id"], today)
    missing = domain.missing_documents(
        held_position_id,
        under_way_or_upcoming,
        today,
        await requirements.requirement_rows(conn, position_id, vessel),
        {type_id: d["current_version"] for type_id, d in held.items()},
    )
    return [
        {
            "document_type_id": t["id"],
            "name": t["name"],
            "document_id": held[t["id"]]["id"] if t["id"] in held else None,
        }
        for t in await requirements.document_types(conn, missing)
    ]


async def readiness(conn: asyncpg.Connection, scope: Scope, assignment_id: int) -> dict:
    """The readiness view of an upcoming or under-way Assignment. Finished and
    cancelled ones have none and are answered like a missing one."""
    assignment = await assignments.get(conn, scope, assignment_id)
    if assignment["state"] not in ("upcoming", "under_way"):
        raise NotFound()
    vessel = VesselRef(id=assignment["vessel_id"], flag=assignment["vessel_flag"])
    required = await _required_documents(
        conn, assignment["seafarer_id"], assignment["position_id"], vessel, scope.today
    )
    return {"assignment": assignment, **domain.readiness(assignment, required, scope.today)}
