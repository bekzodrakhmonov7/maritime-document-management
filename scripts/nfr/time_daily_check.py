"""NFR-07 extra: how long one daily check takes at volume, with a stub mailer.

Runs `daily_check.run_manually` (raise Alerts, then send the digests; a manual
run removes nothing, so retention is not part of the time) once on the LOCAL
database as the app_backend role, as an administrator of seed_volume.py.
Prints the RunResult, the wall time and the time spent in each phase.

Usage (from the repo root; BACKEND defaults to ./backend):
    uv run python scripts/nfr/time_daily_check.py --seed-info docs/nfr-evidence/nfr-07/seed.json \
        [--backend PATH] [--out docs/nfr-evidence/nfr-07/daily-check.json]
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]


class StubMailer:
    def __init__(self) -> None:
        self.sent = 0
        self.bytes = 0

    async def send(self, to: str, subject: str, html: str) -> None:
        self.sent += 1
        self.bytes += len(html)


async def run(args) -> dict:
    sys.path.insert(0, str(args.backend))
    import asyncpg

    from app.audit import AuditContext
    from app.config import settings
    from app.services import daily_check

    if urlsplit(settings.database_url).hostname not in ("127.0.0.1", "localhost", "::1"):
        sys.exit("Refusing to run against a non-local database.")
    info = json.loads(args.seed_info.read_text(encoding="utf-8"))
    admin = next(a for a in info["accounts"] if a["id"] == info["admin_id"])
    conn = await asyncpg.connect(settings.database_url)
    phases: dict[str, float] = {}
    original_raise, original_send = daily_check.raise_alerts, daily_check.send_digests

    async def timed_raise(*a, **k):
        t = time.perf_counter()
        try:
            return await original_raise(*a, **k)
        finally:
            phases["raise_alerts_s"] = round(time.perf_counter() - t, 2)

    async def timed_send(*a, **k):
        t = time.perf_counter()
        try:
            return await original_send(*a, **k)
        finally:
            phases["send_digests_s"] = round(time.perf_counter() - t, 2)

    daily_check.raise_alerts, daily_check.send_digests = timed_raise, timed_send
    mailer = StubMailer()
    try:
        ctx = AuditContext(actor_id=UUID(admin["id"]), actor_email=admin["email"],
                           actor_role="administrator")
        t0 = time.perf_counter()
        result = await daily_check.run_manually(conn, mailer, ctx, UUID(admin["id"]))
        wall = time.perf_counter() - t0
    finally:
        await conn.close()
    return {"wall_s": round(wall, 2), **phases, "result": result.as_dict(),
            "stub_mails": mailer.sent, "stub_mail_bytes": mailer.bytes}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seed-info", type=Path, required=True)
    p.add_argument("--backend", type=Path, default=ROOT / "backend")
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    out = asyncio.run(run(args))
    text = json.dumps(out, indent=2, default=str)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
