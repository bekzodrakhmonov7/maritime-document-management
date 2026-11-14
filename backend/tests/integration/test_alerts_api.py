"""Alerts and the daily check (FR-16; T6, T9).

The check runs against the real database as app_backend: scheduled runs are
driven through the service with a chosen clock, manual runs through the HTTP
API. E-mail goes to an in-memory mailer instead of Resend.
"""

import json
import os
from datetime import datetime, time, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

from app.domain import today_in
from app.services import daily_check
from tests.conftest import auth_header

TODAY = today_in("UTC")


def day(offset: int):
    return TODAY + timedelta(days=offset)


class FakeMailer:
    """Keeps every digest; fails while `failing` is set."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.failing = False

    async def send(self, to: str, subject: str, html: str) -> None:
        from app.mail import MailFailed

        if self.failing:
            raise MailFailed("mail server unavailable")
        self.sent.append({"to": to, "subject": subject, "html": html})

    def to(self, address: str) -> list[dict]:
        return [m for m in self.sent if m["to"] == address]


@pytest_asyncio.fixture
async def mailer(app):
    from app.mail import get_mailer

    fake = FakeMailer()
    app.dependency_overrides[get_mailer] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_mailer, None)


@pytest_asyncio.fixture
async def alerts_cleanup(owner_db, documents_cleanup):
    """Empty the daily check runs before and after (documents_cleanup empties
    the Alert tables). Manual runs reference Accounts, so this goes first."""
    statement = "TRUNCATE public.daily_check_run"
    await owner_db.execute(statement)
    yield
    await owner_db.execute(statement)


@pytest_asyncio.fixture
async def app_db(app):
    """A connection as app_backend, for driving the service directly."""
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def world(crew, make_account, alerts_cleanup, settings_reset, owner_db):
    master = await crew.position("Master")
    alpha = await crew.vessel("Alpha")
    bravo = await crew.vessel("Bravo")  # no Responsible Officer
    ids = {
        "officer_a": await make_account(role="crewing_officer", email=f"a-{uuid4().hex[:8]}@example.com"),
        "officer_b": await make_account(role="crewing_officer", email=f"b-{uuid4().hex[:8]}@example.com"),
        "admin": await make_account(role="administrator", email=f"adm-{uuid4().hex[:8]}@example.com"),
        "manager": await make_account(role="manager"),
    }
    await crew.link(ids["officer_a"], alpha)
    emails = {
        k: await owner_db.fetchval("SELECT email FROM public.users WHERE id = $1", v)
        for k, v in ids.items()
    }
    passport = await owner_db.fetchval(
        "INSERT INTO public.document_type (name, expires) VALUES ('Passport', true) RETURNING id"
    )
    anna = await crew.seafarer(master, "Anna")  # under way on Alpha
    boris = await crew.seafarer(master, "Boris")  # Unassigned Pool
    carl = await crew.seafarer(master, "Carl")  # upcoming on Bravo
    for seafarer, vessel, start, end in ((anna, alpha, -10, 60), (carl, bravo, 5, 90)):
        await owner_db.execute(
            """
            INSERT INTO public.assignment (seafarer_id, vessel_id, position_id, start_date, end_date)
            VALUES ($1, $2, $3, $4, $5)
            """,
            seafarer, vessel, master, day(start), day(end),
        )

    class World:
        pass

    w = World()
    w.ids, w.emails, w.passport = ids, emails, passport
    w.anna, w.boris, w.carl, w.alpha, w.bravo, w.master = anna, boris, carl, alpha, bravo, master
    w.headers = {k: auth_header(v) for k, v in ids.items()}

    async def document(seafarer_id: int, expiry_offset: int | None) -> int:
        doc = await owner_db.fetchval(
            "INSERT INTO public.document (seafarer_id, document_type_id) VALUES ($1, $2) RETURNING id",
            seafarer_id, passport,
        )
        await w.version(doc, expiry_offset)
        return doc

    async def version(document_id: int, expiry_offset: int | None, number: str = "P-1") -> int:
        return await owner_db.fetchval(
            """
            INSERT INTO public.version (document_id, file_path, original_filename, content_type,
                                        document_number, issuing_authority, issue_date,
                                        expiry_date, uploaded_by, uploaded_at)
            VALUES ($1, $2, 'p.pdf', 'application/pdf', $3, 'Registry', $4, $5, $6,
                    now() + (SELECT count(*) FROM public.version) * interval '1 second')
            RETURNING id
            """,
            document_id, f"documents/{uuid4().hex}", number, day(-3000),
            None if expiry_offset is None else day(expiry_offset), ids["officer_a"],
        )

    w.document, w.version = document, version
    return w


async def _alerts(owner_db, document_id: int) -> list[dict]:
    rows = await owner_db.fetch(
        "SELECT step, expiry_date, skipped FROM public.alert WHERE document_id = $1 ORDER BY step DESC",
        document_id,
    )
    return [dict(r) for r in rows]


async def _run_now(client, w, headers=None):
    return await client.post("/api/admin/daily-check/run", headers=headers or w.headers["admin"])


async def _ran(client, w) -> dict:
    res = await _run_now(client, w)
    assert res.status_code == 200, res.text
    return res.json()


# --- Database guards -----------------------------------------------------------------------


async def test_one_alert_per_document_step_and_expiry_date(world, owner_db):
    doc = await world.document(world.anna, 20)
    insert = "INSERT INTO public.alert (document_id, step, expiry_date) VALUES ($1, 30, $2)"
    await owner_db.execute(insert, doc, day(20))
    with pytest.raises(asyncpg.UniqueViolationError):
        await owner_db.execute(insert, doc, day(20))
    # A new expiry date starts over.
    await owner_db.execute(insert, doc, day(400))


async def test_one_scheduled_run_per_local_date_in_the_database(world, owner_db):
    insert = "INSERT INTO public.daily_check_run (local_date) VALUES ($1)"
    await owner_db.execute(insert, TODAY)
    with pytest.raises(asyncpg.UniqueViolationError):
        await owner_db.execute(insert, TODAY)
    # Manual runs don't count as the day's run.
    for _ in range(2):
        await owner_db.execute(
            "INSERT INTO public.daily_check_run (local_date, manual, started_by) VALUES ($1, true, $2)",
            TODAY, world.ids["admin"],
        )


async def test_the_app_cannot_rewrite_or_remove_alerts(world, owner_db, app_db):
    doc = await world.document(world.anna, 20)
    await owner_db.execute(
        "INSERT INTO public.alert (document_id, step, expiry_date) VALUES ($1, 30, $2)", doc, day(20)
    )
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_db.execute("UPDATE public.alert SET step = 0")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_db.execute("DELETE FROM public.alert")


# --- Raising and sending -----------------------------------------------------------------


async def test_a_manual_run_sends_one_digest_per_recipient_and_a_second_sends_nothing(
    client, world, mailer, owner_db
):
    anna_doc = await world.document(world.anna, 25)
    anna_visa = await owner_db.fetchval(
        "INSERT INTO public.document_type (name, expires) VALUES ('Visa', true) RETURNING id"
    )
    visa = await owner_db.fetchval(
        "INSERT INTO public.document (seafarer_id, document_type_id) VALUES ($1, $2) RETURNING id",
        world.anna, anna_visa,
    )
    await world.version(visa, 3)
    await world.document(world.boris, 55)
    await world.document(world.carl, 85)

    result = await _ran(client, world)
    assert result["raised"] == 4

    [officer_mail] = mailer.to(world.emails["officer_a"])
    assert "Anna Petrova" in officer_mail["html"]
    assert "Boris" not in officer_mail["html"] and "Carl" not in officer_mail["html"]
    assert f"/documents/{anna_doc}" in officer_mail["html"]
    [admin_mail] = mailer.to(world.emails["admin"])
    assert "Boris Petrova" in admin_mail["html"] and "Carl Petrova" in admin_mail["html"]
    assert "Anna" not in admin_mail["html"]
    assert mailer.to(world.emails["officer_b"]) == []
    assert mailer.to(world.emails["manager"]) == []

    sent_before = len(mailer.sent)
    result = await _ran(client, world)
    assert result["raised"] == 0 and result["sent"] == 0
    assert len(mailer.sent) == sent_before


async def test_steps_reached_late_send_the_most_urgent_and_store_the_rest_skipped(
    client, world, mailer, owner_db
):
    doc = await world.document(world.anna, -3)  # already expired at upload
    await _ran(client, world)
    assert await _alerts(owner_db, doc) == [
        {"step": 90, "expiry_date": day(-3), "skipped": True},
        {"step": 60, "expiry_date": day(-3), "skipped": True},
        {"step": 30, "expiry_date": day(-3), "skipped": True},
        {"step": 0, "expiry_date": day(-3), "skipped": False},
    ]
    assert await owner_db.fetchval(
        "SELECT count(*) FROM public.alert_delivery ad JOIN public.alert a ON a.id = ad.alert_id "
        "WHERE a.document_id = $1", doc,
    ) == 1
    [mail] = mailer.to(world.emails["officer_a"])
    assert "Expired" in mail["html"]


async def test_a_renewal_with_a_new_expiry_restarts_the_steps_and_a_details_only_one_does_not(
    client, world, mailer, owner_db
):
    doc = await world.document(world.anna, 25)
    await _ran(client, world)
    # A corrected document number with the same expiry: nothing new.
    await world.version(doc, 25, number="P-1b")
    assert (await _ran(client, world))["raised"] == 0
    # A renewal expiring within 90 days starts over at 90.
    await world.version(doc, 80, number="P-2")
    assert (await _ran(client, world))["raised"] == 1
    assert [(a["step"], a["expiry_date"]) for a in await _alerts(owner_db, doc) if not a["skipped"]] == [
        (90, day(80)), (30, day(25)),
    ]


async def test_inactive_seafarers_and_documents_without_expiry_are_not_watched(
    client, world, mailer, owner_db
):
    await owner_db.execute(
        "UPDATE public.seafarer SET inactive_since = now(), inactive_reason = 'Left' WHERE id = $1",
        world.boris,
    )
    await world.document(world.boris, 5)
    await world.document(world.anna, None)
    assert (await _ran(client, world))["raised"] == 0
    assert mailer.sent == []


async def test_unreviewed_versions_alert_too_marked_awaiting_review(client, world, mailer, owner_db):
    await world.document(world.anna, 10)
    await _ran(client, world)
    [mail] = mailer.to(world.emails["officer_a"])
    assert "awaiting review" in mail["html"]


async def test_a_failed_send_is_retried_without_raising_the_alert_again(
    client, world, mailer, owner_db
):
    doc = await world.document(world.anna, 25)
    mailer.failing = True
    result = await _ran(client, world)
    assert result["raised"] == 1 and result["failed"] >= 1
    [delivery] = await owner_db.fetch(
        "SELECT ad.* FROM public.alert_delivery ad JOIN public.alert a ON a.id = ad.alert_id "
        "WHERE a.document_id = $1", doc,
    )
    assert delivery["sent_at"] is None and delivery["attempts"] == 1
    assert delivery["last_error"] == "mail server unavailable"

    mailer.failing = False
    result = await _ran(client, world)
    assert result["raised"] == 0
    [mail] = mailer.to(world.emails["officer_a"])
    assert "Anna Petrova" in mail["html"]
    [delivery] = await owner_db.fetch(
        "SELECT ad.* FROM public.alert_delivery ad JOIN public.alert a ON a.id = ad.alert_id "
        "WHERE a.document_id = $1", doc,
    )
    assert delivery["sent_at"] is not None and delivery["attempts"] == 2
    assert len(await _alerts(owner_db, doc)) == 3  # 90 and 60 skipped, 30 raised once


async def test_a_failed_send_is_not_retried_once_the_alert_has_closed(client, world, mailer, owner_db):
    doc = await world.document(world.anna, 25)
    mailer.failing = True
    await _ran(client, world)
    mailer.failing = False
    await world.version(doc, 700, number="P-2")  # renewed: the alert closes
    await _ran(client, world)
    assert mailer.sent == []


# --- The schedule ------------------------------------------------------------------------


def _utc(t: time):
    return datetime.combine(TODAY, t, tzinfo=timezone.utc)


async def test_the_scheduled_check_runs_once_per_local_date_from_the_check_time(
    world, mailer, owner_db, app_db
):
    await world.document(world.anna, 25)
    assert await daily_check.run_if_due(app_db, mailer, now=_utc(time(6, 55))) is None
    first = await daily_check.run_if_due(app_db, mailer, now=_utc(time(7, 0)))
    assert first is not None and first.raised == 1 and not first.manual
    assert await daily_check.run_if_due(app_db, mailer, now=_utc(time(7, 5))) is None
    assert await daily_check.run_if_due(app_db, mailer, now=_utc(time(23, 55))) is None
    [run] = await owner_db.fetch("SELECT * FROM public.daily_check_run")
    assert run["local_date"] == TODAY and run["manual"] is False and run["finished_at"] is not None


async def test_the_local_date_and_check_time_follow_the_settings(world, mailer, owner_db, app_db):
    # 23:30 UTC is already the next day, 08:30, in Tokyo.
    await owner_db.execute(
        "UPDATE public.settings SET time_zone = 'Asia/Tokyo', daily_check_time = '08:30'"
    )
    result = await daily_check.run_if_due(app_db, mailer, now=_utc(time(23, 30)))
    assert result is not None and result.local_date == TODAY + timedelta(days=1)
    await owner_db.execute("UPDATE public.settings SET daily_check_time = '09:00'")
    assert await daily_check.run_if_due(
        app_db, mailer, now=_utc(time(23, 30)) + timedelta(days=1)
    ) is None


async def test_a_manual_run_does_not_count_as_the_days_scheduled_run(
    client, world, mailer, owner_db, app_db
):
    await _ran(client, world)
    assert await daily_check.run_if_due(app_db, mailer, now=_utc(time(7, 0))) is not None


async def test_the_manual_run_writes_its_audit_record(client, world, mailer, owner_db):
    await world.document(world.anna, 25)
    result = await _ran(client, world)
    [record] = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE action = 'daily_check_run_manually' AND target_id = $1 "
        "AND target_type = 'daily_check_run'",
        str(result["run_id"]),
    )
    assert record["actor_id"] == world.ids["admin"]
    assert json.loads(record["after"])["local_date"] == TODAY.isoformat()
    run = await owner_db.fetchrow("SELECT * FROM public.daily_check_run WHERE id = $1", result["run_id"])
    assert run["manual"] is True and run["started_by"] == world.ids["admin"]


@pytest.mark.parametrize("who", ["officer_a", "manager"])
async def test_only_administrators_run_the_check(client, world, mailer, owner_db, who):
    res = await _run_now(client, world, world.headers[who])
    assert res.status_code == 403
    assert await owner_db.fetchval("SELECT count(*) FROM public.daily_check_run") == 0
    assert await owner_db.fetchval(
        "SELECT count(*) FROM public.audit_log WHERE action = 'access_refused' AND actor_id = $1",
        world.ids[who],
    ) == 1


# --- The Alerts page ---------------------------------------------------------------------


async def test_open_alerts_within_scope_most_urgent_first(client, world, mailer, owner_db):
    soon = await world.document(world.anna, 5)
    later = await world.document(world.boris, 50)
    await world.document(world.carl, 20)  # Bravo: outside officer A's Scope
    await _ran(client, world)

    res = await client.get("/api/alerts", headers=world.headers["officer_a"])
    assert res.status_code == 200
    alerts = res.json()
    assert [a["document_id"] for a in alerts] == [soon, later]
    first = alerts[0]
    assert first["step"] == 30 and first["days_left"] == 5
    assert first["seafarer_id"] == world.anna and first["seafarer_name"] == "Anna Petrova"
    assert first["document_type_name"] == "Passport" and first["awaiting_review"] is True
    assert first["expiry_date"] == day(5).isoformat()

    res = await client.get("/api/alerts/count", headers=world.headers["officer_a"])
    assert res.json() == {"open": 2}
    res = await client.get("/api/alerts", headers=world.headers["admin"])
    assert len(res.json()) == 3


async def test_a_document_shows_once_with_its_most_urgent_open_step(client, world, mailer, owner_db):
    doc = await world.document(world.anna, 25)
    await owner_db.execute(
        "INSERT INTO public.alert (document_id, step, expiry_date) VALUES ($1, 90, $2), ($1, 60, $2)",
        doc, day(25),
    )
    await _ran(client, world)
    [alert] = (await client.get("/api/alerts", headers=world.headers["admin"])).json()
    assert alert["step"] == 30


async def test_alerts_close_on_a_new_expiry_or_an_inactive_seafarer(client, world, mailer, owner_db):
    anna_doc = await world.document(world.anna, 5)
    await world.document(world.boris, 5)
    await _ran(client, world)
    await world.version(anna_doc, 700, number="P-2")
    await owner_db.execute(
        "UPDATE public.seafarer SET inactive_since = now(), inactive_reason = 'Left' WHERE id = $1",
        world.boris,
    )
    assert (await client.get("/api/alerts", headers=world.headers["admin"])).json() == []
    assert (await client.get("/api/alerts/count", headers=world.headers["admin"])).json() == {"open": 0}


@pytest.mark.parametrize("path", ["/api/alerts", "/api/alerts/count"])
async def test_managers_get_403_on_alerts_and_it_is_recorded(client, world, owner_db, path):
    res = await client.get(path, headers=world.headers["manager"])
    assert res.status_code == 403
    assert await owner_db.fetchval(
        "SELECT count(*) FROM public.audit_log WHERE action = 'access_refused' AND actor_id = $1 "
        "AND target_id = $2",
        world.ids["manager"], f"GET {path}",
    ) == 1
