"""NFR-01 / NFR-07: where the dashboard's time goes (database or Python).

Times `documents.summaries_by_seafarer` for every seafarer twice, then runs
`dashboard.dashboard` for the whole fleet under cProfile and prints the top 15
functions by cumulative time. Read-only.

Usage (from the repo root; BACKEND defaults to ./backend, pass a clean export
of a commit to profile that instead):
    uv run python scripts/nfr/profile_dashboard.py [BACKEND]
"""

import asyncio
import cProfile
import os
import pstats
import sys
import time
from pathlib import Path

BACKEND = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

import asyncpg  # noqa: E402

from app import domain  # noqa: E402
from app.domain import DashboardFilters  # noqa: E402
from app.scope import whole_fleet  # noqa: E402
from app.services import dashboard, documents  # noqa: E402

OWNER_URL = os.environ.get(
    "OWNER_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)


async def main() -> None:
    conn = await asyncpg.connect(OWNER_URL)
    try:
        today = domain.today_in("UTC")
        ids = [r[0] for r in await conn.fetch("SELECT id FROM public.seafarer")]
        for _ in range(2):
            t = time.perf_counter()
            await documents.summaries_by_seafarer(conn, ids, today)
            print(f"summaries_by_seafarer ({len(ids)} seafarers): {time.perf_counter() - t:.2f} s")
        prof = cProfile.Profile()
        prof.enable()
        t = time.perf_counter()
        await dashboard.dashboard(conn, whole_fleet(today), DashboardFilters())
        print(f"dashboard under cProfile: {time.perf_counter() - t:.2f} s")
        prof.disable()
        pstats.Stats(prof).sort_stats("cumulative").print_stats(15)
    finally:
        await conn.close()


asyncio.run(main())
