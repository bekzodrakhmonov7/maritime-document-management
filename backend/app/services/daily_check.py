"""The daily check (FR-16; T6, T9): raise Alerts, then send the digests.

A run has two phases:

1. Raise, in one transaction. Every Document of a non-Inactive seafarer whose
   Current Version has an expiry date is watched (required or not, unreviewed
   included). `domain.step_to_raise` picks the most urgent Alert Step reached
   that wasn't raised yet for that expiry date; earlier steps reached with it
   are stored as skipped. The raised Alert gets one unsent delivery per
   recipient (`domain.alert_recipients`). The unique (Document, step, expiry
   date) makes a second run, or two at once, raise nothing twice.
2. Send. Every unsent delivery whose Alert is still open, new ones and
   earlier failures alike, goes into one digest per recipient. A send that
   fails is kept unsent with its error and retried by the next run while the
   Alert stays open; the Alert itself is never raised again.

The scheduled run happens once per local date (company time zone), from the
configured check time on; a manual run by an administrator doesn't count as
the day's run and is audited. Settings are read at the start of each run.

The scheduled run ends with retention (`services.retention`): Replaced
Versions, Inactive seafarers and old Audit Records whose Retention Period has
ended are removed. The manual run never removes anything.
"""

import logging
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import asyncpg
from jinja2 import Environment

from app import audit, domain
from app.audit import AuditAction, AuditContext
from app.config import settings as app_config
from app.mail import MailFailed, Mailer
from app.services import documents, retention
from app.services.retention import CleanupResult
from app.storage import FileStorage, get_storage

logger = logging.getLogger(__name__)

TARGET = "daily_check_run"


@dataclass(frozen=True)
class RunResult:
    run_id: int
    local_date: date
    manual: bool
    raised: int
    skipped: int
    sent: int
    failed: int
    # Scheduled runs only; None when it didn't run or failed.
    retention: CleanupResult | None = None

    def as_dict(self) -> dict:
        return asdict(self)


# --- Running -----------------------------------------------------------------------------


async def run_if_due(
    conn: asyncpg.Connection,
    mailer: Mailer,
    *,
    now: datetime | None = None,
    storage: FileStorage | None = None,
) -> RunResult | None:
    """The scheduled run: once per local date, from the check time on. The
    run row is claimed first, so two workers never both run the same day."""
    config = await conn.fetchrow("SELECT time_zone, daily_check_time FROM public.settings")
    local_now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(config["time_zone"]))
    ran_today = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM public.daily_check_run WHERE local_date = $1 AND NOT manual)",
        local_now.date(),
    )
    if not domain.daily_check_due(local_now, config["daily_check_time"], ran_today):
        return None
    run_id = await conn.fetchval(
        """
        INSERT INTO public.daily_check_run (local_date) VALUES ($1)
        ON CONFLICT (local_date) WHERE NOT manual DO NOTHING
        RETURNING id
        """,
        local_now.date(),
    )
    if run_id is None:
        return None
    return await _check(
        conn, mailer, run_id, local_now.date(), manual=False, storage=storage or get_storage()
    )


async def run_manually(
    conn: asyncpg.Connection, mailer: Mailer, ctx: AuditContext, account_id: UUID
) -> RunResult:
    """An administrator's run now; it doesn't count as the day's scheduled run."""
    today = await _company_today(conn)
    async with conn.transaction():
        run_id = await conn.fetchval(
            """
            INSERT INTO public.daily_check_run (local_date, manual, started_by)
            VALUES ($1, true, $2) RETURNING id
            """,
            today,
            account_id,
        )
        await audit.record(
            conn, ctx, AuditAction.DAILY_CHECK_RUN_MANUALLY,
            target_type=TARGET, target_id=run_id,
            after={"local_date": today.isoformat(), "manual": True},
        )
    return await _check(conn, mailer, run_id, today, manual=True)


async def _company_today(conn: asyncpg.Connection) -> date:
    return domain.today_in(await conn.fetchval("SELECT time_zone FROM public.settings"))


async def _check(
    conn: asyncpg.Connection,
    mailer: Mailer,
    run_id: int,
    today: date,
    *,
    manual: bool,
    storage: FileStorage | None = None,
) -> RunResult:
    """Alerts, then (scheduled runs only, given `storage`) retention last."""
    raised, skipped = await raise_alerts(conn, today)
    sent, failed = await send_digests(conn, mailer, today)
    cleanup = None
    if not manual and storage is not None:
        try:
            cleanup = await retention.clean_up(conn, storage, run_id)
        except Exception:
            # The alerts went out; the clean-up is tried again tomorrow.
            logger.exception("Retention failed in daily check run %s", run_id)
    await conn.execute(
        "UPDATE public.daily_check_run SET finished_at = now() WHERE id = $1", run_id
    )
    result = RunResult(run_id, today, manual, raised, skipped, sent, failed, cleanup)
    logger.info("Daily check finished: %s", result)
    return result


# --- Raising -----------------------------------------------------------------------------


async def raise_alerts(conn: asyncpg.Connection, today: date) -> tuple[int, int]:
    """Raise the Alerts due today; returns (raised, skipped)."""
    async with conn.transaction():
        steps = await conn.fetchval("SELECT alert_steps FROM public.settings")
        watched = await conn.fetch(
            """
            SELECT d.id, d.seafarer_id
              FROM public.document d JOIN public.seafarer s ON s.id = d.seafarer_id
             WHERE s.inactive_since IS NULL
             ORDER BY d.id
            """
        )
        currents = await documents.current_versions(conn, [d["id"] for d in watched])
        already = await _raised_steps(conn, list(currents))
        recipients = await _Recipients.load(conn, today)

        raised = skipped = 0
        for document in watched:
            current = currents[document["id"]]
            if current is None or current["expiry_date"] is None:
                continue
            expiry = current["expiry_date"]
            choice = domain.step_to_raise(
                expiry, today, steps, already.get((document["id"], expiry), set())
            )
            if choice is None:
                continue
            for step in choice.skipped:
                if await _insert_alert(conn, document["id"], step, expiry, skipped=True) is not None:
                    skipped += 1
            alert_id = await _insert_alert(conn, document["id"], choice.step, expiry, skipped=False)
            if alert_id is None:
                continue  # Raised meanwhile by another run.
            raised += 1
            await conn.executemany(
                "INSERT INTO public.alert_delivery (alert_id, recipient_id) VALUES ($1, $2)",
                [(alert_id, r) for r in sorted(recipients.of(document["seafarer_id"]))],
            )
        return raised, skipped


async def _raised_steps(
    conn: asyncpg.Connection, document_ids: list[int]
) -> dict[tuple[int, date], set[int]]:
    rows = await conn.fetch(
        "SELECT document_id, expiry_date, step FROM public.alert WHERE document_id = ANY($1::bigint[])",
        document_ids,
    )
    raised: dict[tuple[int, date], set[int]] = defaultdict(set)
    for row in rows:
        raised[(row["document_id"], row["expiry_date"])].add(row["step"])
    return raised


async def _insert_alert(
    conn: asyncpg.Connection, document_id: int, step: int, expiry: date, *, skipped: bool
) -> int | None:
    return await conn.fetchval(
        """
        INSERT INTO public.alert (document_id, step, expiry_date, skipped)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT ON CONSTRAINT uq_alert_document_step_expiry DO NOTHING
        RETURNING id
        """,
        document_id, step, expiry, skipped,
    )


@dataclass(frozen=True)
class _Recipients:
    """Who is warned about whom, as of today."""

    vessels_by_seafarer: dict[int, list[int]]
    officers_by_vessel: dict[int, set[UUID]]
    administrators: set[UUID]

    @classmethod
    async def load(cls, conn: asyncpg.Connection, today: date) -> "_Recipients":
        vessels: dict[int, list[int]] = defaultdict(list)
        for row in await conn.fetch(
            """
            SELECT seafarer_id, vessel_id FROM public.assignment
             WHERE cancelled_at IS NULL AND end_date >= $1
             ORDER BY start_date
            """,
            today,
        ):
            vessels[row["seafarer_id"]].append(row["vessel_id"])
        officers: dict[int, set[UUID]] = defaultdict(set)
        for row in await conn.fetch(
            """
            SELECT ro.vessel_id, u.id
              FROM public.responsible_officer ro JOIN public.users u ON u.id = ro.user_id
             WHERE u.status = 'active' AND u.role = 'crewing_officer'
            """
        ):
            officers[row["vessel_id"]].add(row["id"])
        admins = await conn.fetch(
            "SELECT id FROM public.users WHERE status = 'active' AND role = 'administrator'"
        )
        return cls(dict(vessels), dict(officers), {r["id"] for r in admins})

    def of(self, seafarer_id: int) -> set[UUID]:
        return domain.alert_recipients(
            self.vessels_by_seafarer.get(seafarer_id, []), self.officers_by_vessel, self.administrators
        )


# --- Sending -----------------------------------------------------------------------------


async def send_digests(conn: asyncpg.Connection, mailer: Mailer, today: date) -> tuple[int, int]:
    """Send every unsent delivery of an open Alert, one digest per recipient;
    returns (digests sent, digests failed). The rows stay locked while
    sending, so a concurrent run skips them instead of sending twice."""
    async with conn.transaction():
        pending = await conn.fetch(
            """
            SELECT ad.id AS delivery_id, ad.recipient_id, u.email, u.full_name,
                   a.document_id, a.step, a.expiry_date,
                   s.first_name, s.last_name, s.inactive_since IS NOT NULL AS seafarer_inactive,
                   t.name AS document_type_name
              FROM public.alert_delivery ad
              JOIN public.users u ON u.id = ad.recipient_id
              JOIN public.alert a ON a.id = ad.alert_id
              JOIN public.document d ON d.id = a.document_id
              JOIN public.seafarer s ON s.id = d.seafarer_id
              JOIN public.document_type t ON t.id = d.document_type_id
             WHERE ad.sent_at IS NULL AND u.status = 'active'
             ORDER BY a.expiry_date, a.step, lower(s.last_name), lower(s.first_name), a.id
               FOR UPDATE OF ad SKIP LOCKED
            """
        )
        currents = await documents.current_versions(
            conn, sorted({p["document_id"] for p in pending})
        )
        digests: dict[UUID, list[dict]] = defaultdict(list)
        for p in pending:
            current = currents[p["document_id"]]
            if not domain.alert_is_open(
                p["expiry_date"],
                current_expiry=None if current is None else current["expiry_date"],
                seafarer_inactive=p["seafarer_inactive"],
            ):
                continue
            digests[p["recipient_id"]].append(
                {**p, "awaiting_review": current["review_state"] == "not_reviewed"}
            )

        sent = failed = 0
        for entries in digests.values():
            ids = [e["delivery_id"] for e in entries]
            try:
                await mailer.send(entries[0]["email"], _subject(entries), _render(entries, today))
            except MailFailed as exc:
                failed += 1
                logger.warning("Alert digest to %s failed: %s", entries[0]["email"], exc)
                await conn.execute(
                    """
                    UPDATE public.alert_delivery SET attempts = attempts + 1, last_error = $2
                     WHERE id = ANY($1::bigint[])
                    """,
                    ids, str(exc)[:1000],
                )
            else:
                sent += 1
                await conn.execute(
                    """
                    UPDATE public.alert_delivery
                       SET attempts = attempts + 1, sent_at = now(), last_error = NULL
                     WHERE id = ANY($1::bigint[])
                    """,
                    ids,
                )
        return sent, failed


def _subject(entries: list[dict]) -> str:
    n = len(entries)
    return f"Crew Monitor: {n} document alert{'s' if n != 1 else ''}"


def _step_label(step: int, expiry: date, today: date) -> str:
    """How far a document is from expiry, as shown in the digest."""
    days_left = (expiry - today).days
    if days_left < 0:
        return f"Expired {-days_left} day{'s' if days_left != -1 else ''} ago"
    if days_left == 0:
        return "Expires today"
    return f"Expires in {days_left} day{'s' if days_left != 1 else ''} ({step}-day step)"


_TEMPLATE = Environment(autoescape=True).from_string(
    """<!doctype html>
<html><body style="font-family: sans-serif; color: #102a43;">
<p>Hello {{ name }},</p>
<p>These documents have reached an alert step:</p>
<table cellpadding="6" style="border-collapse: collapse;">
<tr style="text-align: left;"><th>Seafarer</th><th>Document</th><th>Expiry date</th><th>Status</th></tr>
{% for e in entries %}<tr style="border-top: 1px solid #d9e2ec;">
<td>{{ e.first_name }} {{ e.last_name }}</td>
<td><a href="{{ base }}/documents/{{ e.document_id }}">{{ e.document_type_name }}</a></td>
<td>{{ e.expiry_date.isoformat() }}</td>
<td>{{ e.label }}{% if e.awaiting_review %} (awaiting review){% endif %}</td>
</tr>
{% endfor %}</table>
<p><a href="{{ base }}/alerts">Open the Alerts page</a></p>
</body></html>
"""
)


def _render(entries: list[dict], today: date) -> str:
    return _TEMPLATE.render(
        name=entries[0]["full_name"] or entries[0]["email"],
        base=app_config.frontend_url.rstrip("/"),
        entries=[
            {**e, "label": _step_label(e["step"], e["expiry_date"], today)} for e in entries
        ],
    )
