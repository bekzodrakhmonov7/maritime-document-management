"""NFR-01 / NFR-07: count the shape of the seeded volume with plain SQL.

Expiry status is that of each Document's Current Version (latest upload),
own expiry date, against today (UTC, the Settings time zone after a reset) and
the largest Alert Step. Prints JSON; --out writes it too.

Usage (from the repo root):
    uv run python scripts/nfr/data_shape.py --out docs/nfr-evidence/nfr-01/data-shape.json
"""

import argparse
import asyncio
import json
import os
from pathlib import Path

import asyncpg

OWNER_URL = os.environ.get(
    "OWNER_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)

QUERIES = {
    "totals": """
        SELECT (SELECT count(*) FROM public.seafarer) AS seafarers,
               (SELECT count(*) FROM public.seafarer WHERE inactive_since IS NOT NULL) AS inactive_seafarers,
               (SELECT count(*) FROM public.seafarer WHERE char_length(first_name || ' ' || last_name) >= 40) AS long_names,
               (SELECT count(*) FROM public.vessel) AS vessels,
               (SELECT count(*) FROM public.document) AS documents,
               (SELECT count(*) FROM public.version) AS versions,
               (SELECT count(*) FROM public.review) AS reviews,
               (SELECT count(*) FROM public.verification) AS verifications,
               (SELECT count(*) FROM public.assignment) AS assignments,
               (SELECT count(*) FROM public.users WHERE status = 'active') AS active_accounts
    """,
    "versions_per_document": """
        SELECT n AS versions, count(*) AS documents FROM (
            SELECT count(*) AS n FROM public.version GROUP BY document_id) x
         GROUP BY n ORDER BY n
    """,
    "current_version_expiry_status": """
        WITH cur AS (
            SELECT DISTINCT ON (v.document_id) v.document_id, v.expiry_date, t.expires
              FROM public.version v
              JOIN public.document d ON d.id = v.document_id
              JOIN public.document_type t ON t.id = d.document_type_id
             ORDER BY v.document_id, v.uploaded_at DESC, v.id DESC),
        step AS (SELECT max(s) AS largest FROM public.settings, unnest(alert_steps) s)
        SELECT CASE
                 WHEN expiry_date IS NULL AND expires THEN 'expiry_not_stated'
                 WHEN expiry_date IS NULL THEN 'no_expiry_date'
                 WHEN expiry_date < CURRENT_DATE THEN 'expired'
                 WHEN expiry_date - CURRENT_DATE <= (SELECT largest FROM step) THEN 'expiring_soon'
                 ELSE 'unexpired' END AS status,
               count(*) AS documents,
               round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
          FROM cur GROUP BY 1 ORDER BY 1
    """,
    "review_state_of_versions": """
        SELECT coalesce(r.decision, 'not_reviewed') AS latest_review, count(*) AS versions,
               round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
          FROM public.version v
          LEFT JOIN LATERAL (SELECT decision FROM public.review
                              WHERE version_id = v.id ORDER BY id DESC LIMIT 1) r ON true
         GROUP BY 1 ORDER BY 1
    """,
    "assignment_states": """
        SELECT CASE WHEN cancelled_at IS NOT NULL THEN 'cancelled'
                    WHEN start_date > CURRENT_DATE THEN 'upcoming'
                    WHEN end_date < CURRENT_DATE THEN 'finished'
                    ELSE 'under_way' END AS state,
               count(*) AS assignments,
               round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct,
               count(*) FILTER (WHERE start_date <= CURRENT_DATE + 90) AS starting_within_90_days
          FROM public.assignment GROUP BY 1 ORDER BY 1
    """,
    "crew_under_way_per_vessel_top5": """
        SELECT v.id, v.name, count(*) AS under_way
          FROM public.assignment a JOIN public.vessel v ON v.id = a.vessel_id
         WHERE a.cancelled_at IS NULL AND a.start_date <= CURRENT_DATE AND a.end_date >= CURRENT_DATE
         GROUP BY v.id, v.name ORDER BY 3 DESC LIMIT 5
    """,
}


async def shape() -> dict:
    conn = await asyncpg.connect(OWNER_URL)
    try:
        out = {}
        for name, sql in QUERIES.items():
            rows = [{k: (float(v) if hasattr(v, "as_integer_ratio") and not isinstance(v, int) else v)
                     for k, v in dict(r).items()} for r in await conn.fetch(sql)]
            out[name] = rows[0] if name == "totals" else rows
        return out
    finally:
        await conn.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    text = json.dumps(asyncio.run(shape()), indent=2, default=str)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
