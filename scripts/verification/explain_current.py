"""D3: EXPLAIN ANALYZE of the SQL the CURRENT dashboard code actually runs.

scripts/nfr/explain_dashboard.py holds copies of the queries of commit e15125c;
the dashboard changed in 1becbf1. This script instead records every query that
services.dashboard.dashboard() (whole fleet, default page) and
services.documents.summaries_by_seafarer() send, with their arguments, and runs
EXPLAIN (ANALYZE, BUFFERS) on each. It also reports database time (sum of the
queries' wall time) against the call's total wall time. Read-only.

    uv run python scripts/verification/explain_current.py > out.txt
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import asyncpg  # noqa: E402

import vlib  # noqa: E402
from app import domain  # noqa: E402
from app.domain import DashboardFilters  # noqa: E402
from app.scope import whole_fleet  # noqa: E402
from app.services import dashboard  # noqa: E402


class Recorder:
    def __init__(self, conn):
        self.conn, self.calls = conn, []

    def __getattr__(self, name):
        attr = getattr(self.conn, name)
        if name not in ("fetch", "fetchrow", "fetchval", "execute"):
            return attr

        async def wrapped(sql, *args, **kw):
            t = time.perf_counter()
            res = await attr(sql, *args, **kw)
            self.calls.append({"sql": sql, "args": args, "ms": (time.perf_counter() - t) * 1000,
                               "rows": len(res) if isinstance(res, list) else None})
            return res
        return wrapped


async def main() -> None:
    conn = await asyncpg.connect(vlib.OWNER_URL)
    today = domain.today_in("UTC")
    counts = {t: await conn.fetchval(f"SELECT count(*) FROM public.{t}") for t in
              ("seafarer", "document", "version", "review", "verification", "assignment")}
    print("table rows:", json.dumps(counts))
    for label in ("warm-up", "measured"):
        rec = Recorder(conn)
        t = time.perf_counter()
        await dashboard.dashboard(rec, whole_fleet(today), DashboardFilters())
        total = (time.perf_counter() - t) * 1000
        db_ms = sum(c["ms"] for c in rec.calls)
        print(f"\n[{label}] dashboard(): total {total:.1f} ms, in queries {db_ms:.1f} ms "
              f"({100 * db_ms / total:.0f} %), Python and transfer {total - db_ms:.1f} ms, {len(rec.calls)} queries")
    for i, c in enumerate(rec.calls, 1):
        print(f"\n--- query {i}: {c['ms']:.1f} ms wall, {c['rows']} rows\n{c['sql'].strip()[:600]}")
        if c["sql"].lstrip().upper().startswith(("SELECT", "WITH")):
            plan = await conn.fetch("EXPLAIN (ANALYZE, BUFFERS) " + c["sql"], *c["args"])
            for r in plan:
                print("   ", r[0])
    await conn.close()


asyncio.run(main())
