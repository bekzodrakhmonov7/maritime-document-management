"""NFR-07: split one dashboard request into SQL / Python / response serialisation.

Calls `dashboard.dashboard` for the whole fleet on the LOCAL database (owner
role), counting the time spent awaiting asyncpg queries (SQL incl. transfer and
row decoding), then validates the result against DashboardRead and dumps it to
JSON with pydantic-core, as FastAPI 0.138 does for a response_model route
(field.validate + field.serialize_json). Repeats --n times. Read-only.

Usage (from the repo root):
    uv run python scripts/nfr/breakdown_dashboard.py [--n 5] [--out FILE.json]
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import asyncpg  # noqa: E402
from pydantic import TypeAdapter  # noqa: E402

from app import domain  # noqa: E402
from app.domain import DashboardFilters  # noqa: E402
from app.models.dashboard import DashboardRead  # noqa: E402
from app.scope import whole_fleet  # noqa: E402
from app.services import dashboard  # noqa: E402

OWNER_URL = os.environ.get(
    "OWNER_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)


class TimedConn:
    """Proxy that adds up the time spent in fetch/fetchrow/fetchval/execute."""

    def __init__(self, conn):
        self._conn = conn
        self.sql_s = 0.0
        self.queries = 0

    def __getattr__(self, name):
        attr = getattr(self._conn, name)
        if name in ("fetch", "fetchrow", "fetchval", "execute"):
            async def timed(*a, **k):
                t = time.perf_counter()
                try:
                    return await attr(*a, **k)
                finally:
                    self.sql_s += time.perf_counter() - t
                    self.queries += 1
            return timed
        return attr


async def main(args) -> None:
    conn = await asyncpg.connect(OWNER_URL)
    adapter = TypeAdapter(DashboardRead)
    rows = []
    try:
        today = domain.today_in("UTC")
        for i in range(args.n + 1):
            tc = TimedConn(conn)
            t0 = time.perf_counter()
            result = await dashboard.dashboard(tc, whole_fleet(today), DashboardFilters())
            t1 = time.perf_counter()
            model = adapter.validate_python(result, from_attributes=True)
            t2 = time.perf_counter()
            body = adapter.dump_json(model)
            t3 = time.perf_counter()
            row = {
                "run": i,
                "warmup": i == 0,
                "service_ms": round((t1 - t0) * 1000, 1),
                "sql_ms": round(tc.sql_s * 1000, 1),
                "python_ms": round((t1 - t0 - tc.sql_s) * 1000, 1),
                "validate_ms": round((t2 - t1) * 1000, 1),
                "dump_json_ms": round((t3 - t2) * 1000, 1),
                "total_ms": round((t3 - t0) * 1000, 1),
                "queries": tc.queries,
                "bytes": len(body),
            }
            rows.append(row)
            print(row)
    finally:
        await conn.close()
    counted = [r for r in rows if not r["warmup"]]
    med = {k: statistics.median(r[k] for r in counted)
           for k in ("service_ms", "sql_ms", "python_ms", "validate_ms", "dump_json_ms", "total_ms")}
    print("median:", med)
    if body:
        top = json.loads(body)
        sizes = {k: len(json.dumps(v, separators=(",", ":"))) for k, v in top.items()}
        counts = {k: len(v) for k, v in top.items() if isinstance(v, list)}
        print("bytes per top-level key:", sizes)
        print("items per list key:", counts)
    if args.out:
        args.out.write_text(json.dumps({"runs": rows, "median": med,
                                        "bytes_per_key": sizes, "items_per_key": counts},
                                       indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--out", type=Path)
    asyncio.run(main(p.parse_args()))
