"""Open Alerts for the Alerts page and the sidebar badge (FR-16, T6).

An Alert is open while its seafarer isn't Inactive and the Document's Current
Version still has the expiry date it was raised for; that is computed here on
read, never stored. Skipped Alerts were never sent and aren't listed. A
Document with several open steps for one expiry date shows once, with its
most urgent step. Read through the caller's Scope.
"""

import asyncpg

from app import domain
from app.scope import Scope
from app.services import documents


async def list_open(conn: asyncpg.Connection, scope: Scope) -> list[dict]:
    """Open Alerts within Scope, most urgent first (nearest expiry, lowest step)."""
    rows = await conn.fetch(
        f"""
        SELECT a.id, a.document_id, a.step, a.expiry_date, a.raised_at,
               d.seafarer_id, s.first_name || ' ' || s.last_name AS seafarer_name,
               s.inactive_since IS NOT NULL AS seafarer_inactive,
               t.name AS document_type_name
          FROM public.alert a
          JOIN public.document d ON d.id = a.document_id
          JOIN public.seafarer s ON s.id = d.seafarer_id
          JOIN public.document_type t ON t.id = d.document_type_id
         WHERE NOT a.skipped AND s.inactive_since IS NULL AND {scope.where("s")}
         ORDER BY a.expiry_date, a.step, lower(s.last_name), lower(s.first_name), a.id
        """
    )
    currents = await documents.current_versions(conn, sorted({r["document_id"] for r in rows}))
    listed: dict[int, dict] = {}
    for row in rows:
        if row["document_id"] in listed:
            continue  # Already listed with a more urgent step.
        current = currents[row["document_id"]]
        if not domain.alert_is_open(
            row["expiry_date"],
            current_expiry=None if current is None else current["expiry_date"],
            seafarer_inactive=row["seafarer_inactive"],
        ):
            continue
        alert = dict(row)
        del alert["seafarer_inactive"]
        listed[row["document_id"]] = {
            **alert,
            "days_left": (row["expiry_date"] - scope.today).days,
            "awaiting_review": current["review_state"] == "not_reviewed",
        }
    return list(listed.values())


async def count_open(conn: asyncpg.Connection, scope: Scope) -> int:
    return len(await list_open(conn, scope))
