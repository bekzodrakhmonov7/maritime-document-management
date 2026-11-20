"""NFR-03: a missed run is caught up, a repeated or interrupted run adds no alert.

Drives `app.services.daily_check.run_if_due(conn, mailer, now=...)` on the LOCAL
Supabase database with a stub mailer, as the integration tests in
backend/tests/integration/test_alerts_api.py do.

Scenario A (three-day gap): one Document expiring D+32, alert steps 90/60/30/0.
  Runs on D, D+4 (D+1..D+3 missed; 28 days left) and D+4 again.
  Pass: D+4 raises exactly one alert (step 30), the repeat raises none, and the
  `alert` table holds no duplicate (document, step, expiry_date).

Scenario B (interrupted run): same Document set-up on a fresh date range.
  Run on D, then on D+4 the stub mailer raises RuntimeError on its second send
  (a crash in the middle of sending). Then a normal run on D+4 again and on D+5.
  Pass: no second alert for the Document, no duplicate rows.

DESTRUCTIVE for the local database: empties the reference, document, alert and
daily-check-run tables (like the test fixtures) and changes Settings. Afterwards
run `npx --yes supabase@2 db reset`. Refuses to run against a non-local host.

Usage (from the repo root):
    uv run python scripts/nfr/three_day_gap.py
"""

import asyncio
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import asyncpg  # noqa: E402

from app.config import settings  # noqa: E402  (reads ../.env)
from app.mail import MailFailed  # noqa: E402,F401
from app.services import daily_check  # noqa: E402

OWNER_URL = os.environ.get(
    "OWNER_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)
APP_URL = settings.database_url
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

TABLES = (
    "alert_delivery, alert, review, verification, version, document, assignment, "
    "responsible_officer, requirement_exception, position_requirement, seafarer, "
    "document_type, position, vessel, daily_check_run"
)

failures: list[str] = []


def check(ok: bool, label: str) -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        failures.append(label)


class StubMailer:
    """Keeps every digest; raises RuntimeError on send number `crash_on` (1-based)."""

    def __init__(self, crash_on: int | None = None) -> None:
        self.sent: list[tuple[str, str]] = []
        self.calls = 0
        self.crash_on = crash_on

    async def send(self, to: str, subject: str, html: str) -> None:
        self.calls += 1
        if self.crash_on is not None and self.calls == self.crash_on:
            raise RuntimeError("simulated crash in the middle of sending")
        self.sent.append((to, subject))


class FakeStorage:
    async def upload(self, path: str, content: bytes, content_type: str) -> None: ...
    async def delete(self, path: str) -> None: ...
    async def signed_url(self, path: str, ttl_seconds: int, download_name: str) -> str:
        return ""


def at(d: date) -> datetime:
    return datetime.combine(d, time(7, 0), tzinfo=timezone.utc)  # the check time, UTC


async def make_admin(owner: asyncpg.Connection, tag: str) -> UUID:
    uid = uuid4()
    await owner.execute(
        """
        INSERT INTO auth.users (id, email, encrypted_password, raw_user_meta_data,
                                email_confirmed_at, created_at, updated_at)
        VALUES ($1, $2, 'x', jsonb_build_object('full_name', $3::text), now(), now(), now())
        """,
        uid, f"nfr03-{tag}-{uid.hex[:6]}@example.com", f"NFR03 {tag}",
    )
    await owner.execute(
        "UPDATE public.users SET status = 'active', role = 'administrator' WHERE id = $1", uid
    )
    return uid


async def arrange(owner: asyncpg.Connection, d: date) -> tuple[int, list[UUID]]:
    """Empty tables, set Settings, create two admins and one Document expiring d+32."""
    await owner.execute(f"TRUNCATE {', '.join('public.' + t.strip() for t in TABLES.split(','))} CASCADE")
    await owner.execute(
        "UPDATE public.settings SET alert_steps = '{90,60,30,0}', time_zone = 'UTC', "
        "daily_check_time = '07:00'"
    )
    # Other active administrators (e.g. from the seed) would also be recipients;
    # make them inactive so the digest count is exactly ours.
    await owner.execute(
        "UPDATE public.users SET status = 'deactivated' WHERE role = 'administrator' AND status = 'active'"
    )
    admins = [await make_admin(owner, "a"), await make_admin(owner, "b")]
    position = await owner.fetchval("INSERT INTO public.position (name) VALUES ('Master') RETURNING id")
    seafarer = await owner.fetchval(
        "INSERT INTO public.seafarer (first_name, last_name, position_id) VALUES ('Anna', 'Gap', $1) RETURNING id",
        position,
    )
    dtype = await owner.fetchval(
        "INSERT INTO public.document_type (name, expires) VALUES ('Passport', true) RETURNING id"
    )
    doc = await owner.fetchval(
        "INSERT INTO public.document (seafarer_id, document_type_id) VALUES ($1, $2) RETURNING id",
        seafarer, dtype,
    )
    await owner.execute(
        """
        INSERT INTO public.version (document_id, file_path, original_filename, content_type,
                                    document_number, issuing_authority, issue_date, expiry_date,
                                    uploaded_by)
        VALUES ($1, $2, 'p.pdf', 'application/pdf', 'P-1', 'Registry', $3, $4, $5)
        """,
        doc, f"documents/{uuid4().hex}", d - timedelta(days=3000), d + timedelta(days=32), admins[0],
    )
    return doc, admins


async def alerts(owner: asyncpg.Connection, doc: int) -> list[dict]:
    rows = await owner.fetch(
        "SELECT id, step, expiry_date, skipped, raised_at FROM public.alert WHERE document_id = $1 ORDER BY step DESC",
        doc,
    )
    return [dict(r) for r in rows]


async def duplicates(owner: asyncpg.Connection) -> int:
    return await owner.fetchval(
        "SELECT count(*) FROM (SELECT 1 FROM public.alert GROUP BY document_id, step, expiry_date HAVING count(*) > 1) x"
    )


def show(label: str, result) -> None:
    if result is None:
        print(f"{label}: run_if_due returned None (not due / already ran)")
    else:
        print(
            f"{label}: run_id={result.run_id} local_date={result.local_date} raised={result.raised} "
            f"skipped={result.skipped} sent={result.sent} failed={result.failed}"
        )


def show_alerts(rows: list[dict]) -> None:
    for r in rows:
        print(f"    alert id={r['id']} step={r['step']} expiry={r['expiry_date']} skipped={r['skipped']}")


async def scenario_a(owner, app) -> None:
    d = date(2026, 12, 1)
    print(f"\n=== Scenario A: three-day gap (D={d}, expiry={d + timedelta(days=32)}) ===")
    doc, _ = await arrange(owner, d)
    mailer = StubMailer()

    r = await daily_check.run_if_due(app, mailer, now=at(d), storage=FakeStorage())
    show(f"Run on D   ({d})", r)
    show_alerts(await alerts(owner, doc))
    check(r is not None and r.raised == 1, "D: one alert raised (step 60, with 90 stored skipped)")
    before = await alerts(owner, doc)

    print(f"(no runs on {d + timedelta(1)}, {d + timedelta(2)}, {d + timedelta(3)})")
    d4 = d + timedelta(days=4)
    r = await daily_check.run_if_due(app, mailer, now=at(d4), storage=FakeStorage())
    show(f"Run on D+4 ({d4}, 28 days left)", r)
    after = await alerts(owner, doc)
    show_alerts(after)
    new = [a for a in after if a["id"] not in {b["id"] for b in before}]
    check(r is not None and r.raised == 1, "D+4: exactly one alert raised")
    check([(a["step"], a["skipped"]) for a in new] == [(30, False)], "D+4: the new alert is step 30, not skipped")

    r = await daily_check.run_if_due(app, mailer, now=at(d4) + timedelta(hours=2), storage=FakeStorage())
    show(f"Run on D+4 again ({d4} 09:00)", r)
    check(r is None or r.raised == 0, "D+4 repeat: no alert raised")
    # The same date never runs twice as a scheduled run; also drive the raise phase directly.
    raised, skipped = await daily_check.raise_alerts(app, d4)
    print(f"raise_alerts(conn, {d4}) called directly again: raised={raised} skipped={skipped}")
    check(raised == 0 and skipped == 0, "D+4 repeat of the raise phase directly: nothing raised")
    final = await alerts(owner, doc)
    check(len(final) == len(after), "alert row count unchanged by repeats")
    check(await duplicates(owner) == 0, "alert table: no duplicate (document, step, expiry_date)")
    print(f"digests sent in scenario A: {len(mailer.sent)} -> {mailer.sent}")


async def scenario_b(owner, app) -> None:
    d = date(2027, 3, 1)
    print(f"\n=== Scenario B: interrupted run (D={d}, expiry={d + timedelta(days=32)}) ===")
    doc, admins = await arrange(owner, d)
    ok_mailer = StubMailer()
    r = await daily_check.run_if_due(app, ok_mailer, now=at(d), storage=FakeStorage())
    show(f"Run on D   ({d})", r)
    before = await alerts(owner, doc)
    show_alerts(before)

    d4 = d + timedelta(days=4)
    crashing = StubMailer(crash_on=2)
    try:
        r = await daily_check.run_if_due(app, crashing, now=at(d4), storage=FakeStorage())
        show(f"Run on D+4 with crash ({d4})", r)
        check(False, "interrupted run should have raised")
    except RuntimeError as exc:
        print(f"Run on D+4 ({d4}): interrupted by {type(exc).__name__}: {exc}")
        print(f"  stub mailer: {crashing.calls} send calls, {len(crashing.sent)} delivered before the crash")
    mid = await alerts(owner, doc)
    show_alerts(mid)
    run_rows = await owner.fetch("SELECT id, local_date, manual, finished_at FROM public.daily_check_run ORDER BY id")
    for row in run_rows:
        print(f"    daily_check_run id={row['id']} local_date={row['local_date']} finished_at={row['finished_at']}")
    unsent = await owner.fetchval(
        "SELECT count(*) FROM public.alert_delivery ad JOIN public.alert a ON a.id = ad.alert_id "
        "WHERE a.document_id = $1 AND a.step = 30 AND ad.sent_at IS NULL", doc,
    )
    print(f"  step-30 deliveries still unsent after the crash: {unsent}")

    next_mailer = StubMailer()
    r = await daily_check.run_if_due(app, next_mailer, now=at(d4) + timedelta(hours=1), storage=FakeStorage())
    show(f"Next run on D+4 ({d4} 08:00)", r)
    r5 = await daily_check.run_if_due(app, next_mailer, now=at(d4 + timedelta(days=1)), storage=FakeStorage())
    show(f"Next run on D+5 ({d4 + timedelta(days=1)})", r5)
    final = await alerts(owner, doc)
    show_alerts(final)
    step30 = [a for a in final if a["step"] == 30]
    check(len(step30) == 1, "exactly one step-30 alert after crash + next runs")
    check(all(x is None or x.raised == 0 for x in (r, r5)), "runs after the crash raised no alert")
    check(await duplicates(owner) == 0, "alert table: no duplicate (document, step, expiry_date)")
    emails = {}
    for to, _ in crashing.sent + next_mailer.sent:
        emails[to] = emails.get(to, 0) + 1
    print(f"  step-30 digests per recipient across crash + next runs: {emails}")
    if any(n > 1 for n in emails.values()):
        print("  NOTE: a recipient got the same digest twice (sent before the crash, its "
              "sent_at update rolled back with the transaction). Alert not duplicated; e-mail is.")


async def main() -> int:
    for url in (OWNER_URL, APP_URL):
        host = urlsplit(url).hostname
        if host not in LOCAL_HOSTS:
            print(f"Refusing to run: database host {host!r} is not local.")
            return 2
    print(f"started {datetime.now(timezone.utc).isoformat()}  owner={urlsplit(OWNER_URL).hostname}:"
          f"{urlsplit(OWNER_URL).port}  app user={urlsplit(APP_URL).username}")
    owner = await asyncpg.connect(OWNER_URL)
    app = await asyncpg.connect(APP_URL)
    try:
        await scenario_a(owner, app)
        await scenario_b(owner, app)
    finally:
        await app.close()
        await owner.close()
    print(f"\nRESULT: {'PASS' if not failures else 'FAIL: ' + '; '.join(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
