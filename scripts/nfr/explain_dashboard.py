"""NFR-07: EXPLAIN ANALYZE of the SQL behind the dashboard (whole fleet).

Runs the queries of services/dashboard._read_crew and
services/documents.summaries_by_seafarer (copied from commit e15125c) with
the parameters an administrator's dashboard request uses, and prints each plan
and its execution time. Read-only.

Usage (from the repo root):
    uv run python scripts/nfr/explain_dashboard.py > docs/nfr-evidence/nfr-07/explain-dashboard.txt
"""

import asyncio
import os
from datetime import datetime, timezone

import asyncpg

OWNER_URL = os.environ.get(
    "OWNER_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)

QUERIES = [
    ("seafarers", """
        SELECT s.id, s.first_name, s.last_name, s.position_id, p.name AS position_name,
               s.inactive_since IS NOT NULL AS inactive
          FROM public.seafarer s JOIN public.position p ON p.id = s.position_id
         WHERE true AND s.inactive_since IS NULL""", lambda ids, today: []),
    ("assignments", """
        SELECT a.id, a.seafarer_id, a.vessel_id, v.name AS vessel_name, v.flag AS vessel_flag,
               a.position_id, p.name AS position_name, a.start_date, a.end_date, a.cancelled_at
          FROM public.assignment a
          JOIN public.vessel v ON v.id = a.vessel_id
          JOIN public.position p ON p.id = a.position_id
         WHERE a.seafarer_id = ANY($1::bigint[]) AND a.cancelled_at IS NULL AND a.end_date >= $2""",
     lambda ids, today: [ids["seafarer"], today]),
    ("documents", """
        SELECT d.id, d.seafarer_id, d.document_type_id, d.created_at,
               t.name AS document_type_name, t.retired AS document_type_retired,
               t.expires, t.max_validity_months, t.depends_on_id, ct.name AS certificate_type_name
          FROM public.document d
          JOIN public.document_type t ON t.id = d.document_type_id
          LEFT JOIN public.document_type ct ON ct.id = t.depends_on_id
         WHERE d.seafarer_id = ANY($1::bigint[]) ORDER BY lower(t.name), d.id""",
     lambda ids, today: [ids["seafarer"]]),
    ("versions", """
        SELECT v.id, v.document_id, v.file_path, v.original_filename, v.content_type,
               v.document_number, v.issuing_authority, v.issue_date, v.expiry_date,
               v.uploaded_by, u.full_name AS uploaded_by_name, v.uploaded_at
          FROM public.version v JOIN public.users u ON u.id = v.uploaded_by
         WHERE v.document_id = ANY($1::bigint[]) ORDER BY v.uploaded_at, v.id""",
     lambda ids, today: [ids["document"]]),
    ("reviews", """
        SELECT r.id, r.version_id, r.decision, r.comment, r.reviewed_by,
               u.full_name AS reviewed_by_name, r.reviewed_at
          FROM public.review r JOIN public.users u ON u.id = r.reviewed_by
         WHERE r.version_id = ANY($1::bigint[]) ORDER BY r.id""",
     lambda ids, today: [ids["version"]]),
    ("verifications", """
        SELECT c.id, c.version_id, c.checked_on, c.source, c.result, c.reference,
               c.proof_original_filename, c.proof_content_type, c.recorded_by,
               u.full_name AS recorded_by_name, c.recorded_at
          FROM public.verification c JOIN public.users u ON u.id = c.recorded_by
         WHERE c.version_id = ANY($1::bigint[]) ORDER BY c.id""",
     lambda ids, today: [ids["version"]]),
]


async def main() -> None:
    conn = await asyncpg.connect(OWNER_URL)
    try:
        today = datetime.now(timezone.utc).date()
        ids = {
            "seafarer": [r[0] for r in await conn.fetch(
                "SELECT id FROM public.seafarer WHERE inactive_since IS NULL")],
        }
        ids["document"] = [r[0] for r in await conn.fetch(
            "SELECT id FROM public.document WHERE seafarer_id = ANY($1::bigint[])", ids["seafarer"])]
        ids["version"] = [r[0] for r in await conn.fetch(
            "SELECT id FROM public.version WHERE document_id = ANY($1::bigint[])", ids["document"])]
        total = 0.0
        for name, sql, params in QUERIES:
            plan = await conn.fetchval(
                f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}", *params(ids, today))
            import json
            p = json.loads(plan)[0]
            total += p["Execution Time"]
            print(f"=== {name}: execution {p['Execution Time']:.1f} ms, planning "
                  f"{p['Planning Time']:.1f} ms, rows {p['Plan']['Actual Rows']}")
            text = await conn.fetch(f"EXPLAIN (ANALYZE, BUFFERS) {sql}", *params(ids, today))
            print("\n".join(r[0] for r in text))
            print()
        print(f"=== total execution of the six queries: {total:.1f} ms")
    finally:
        await conn.close()


asyncio.run(main())
