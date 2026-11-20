"""Retention (FR-24, FR-25 retention; T13).

Replaced Versions, the whole records of Inactive seafarers and old Audit
Records are removed when their Retention Period ends, as the last step of the
scheduled daily check only. The scheduled check is driven through the service
as app_backend with an in-memory Storage; the manual one through the HTTP API.
Rows are backdated through the owner connection.
"""

import json
import os
from datetime import datetime, timezone
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

from app.services import daily_check
from tests.conftest import FakeStorage, auth_header
from tests.integration.test_alerts_api import FakeMailer, mailer  # noqa: F401 (fixture)


class FailingStorage(FakeStorage):
    """Storage whose deletes fail while `failing` is set."""

    def __init__(self) -> None:
        super().__init__()
        self.failing = False

    async def delete(self, path: str) -> None:
        if self.failing:
            raise RuntimeError("storage unavailable")
        await super().delete(path)


@pytest_asyncio.fixture
async def app_db(app):
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def retention_cleanup(owner_db, documents_cleanup):
    """Empty the runs and the file removal queue before and after. Yields the
    last Audit Record id, so a test sees only the records written after it."""
    statement = "TRUNCATE public.daily_check_run, public.file_removal"
    await owner_db.execute(statement)
    yield await owner_db.fetchval("SELECT coalesce(max(id), 0) FROM public.audit_log")
    await owner_db.execute(statement)


def ago(years: int, days: int = 0) -> str:
    """An interval for `now() - ...` in SQL."""
    return f"{years} years {days} days"


@pytest_asyncio.fixture
async def w(crew, make_account, retention_cleanup, settings_reset, owner_db, app_db):
    master = await crew.position("Master")
    uploader = await make_account(role="crewing_officer")
    reviewer = await make_account(role="crewing_officer")
    admin = await make_account(role="administrator")

    class World:
        pass

    w = World()
    w.master, w.admin = master, admin
    w.storage = FailingStorage()
    w.mailer = FakeMailer()

    async def seafarer(inactive: str | None = None, name: str = "Anna") -> int:
        sid = await crew.seafarer(master, name)
        if inactive is not None:
            await owner_db.execute(
                "UPDATE public.seafarer SET inactive_since = now() - $2::text::interval, "
                "inactive_reason = 'Left the company' WHERE id = $1",
                sid, inactive,
            )
        return sid

    async def document(seafarer_id: int) -> int:
        """A Document of a new Document Type, so a seafarer can have several."""
        type_id = await owner_db.fetchval(
            "INSERT INTO public.document_type (name, expires) VALUES ($1, true) RETURNING id",
            f"Certificate {uuid4().hex[:8]}",
        )
        return await owner_db.fetchval(
            "INSERT INTO public.document (seafarer_id, document_type_id) VALUES ($1, $2) RETURNING id",
            seafarer_id, type_id,
        )

    async def version(document_id: int, uploaded: str, file_path: str | None = None) -> int:
        path = file_path or f"versions/{uuid4().hex}"
        w.storage.objects[path] = (b"%PDF", "application/pdf")
        return await owner_db.fetchval(
            """
            INSERT INTO public.version (document_id, file_path, original_filename, content_type,
                                        document_number, issuing_authority, issue_date,
                                        expiry_date, uploaded_by, uploaded_at)
            VALUES ($1, $2, 'p.pdf', 'application/pdf', 'P-1', 'Registry', '2000-01-01',
                    '2099-01-01', $3, now() - $4::text::interval)
            RETURNING id
            """,
            document_id, path, uploader, uploaded,
        )

    async def review(version_id: int, decision: str, at: str) -> None:
        await owner_db.execute(
            """
            INSERT INTO public.review (version_id, decision, comment, reviewed_by, reviewed_at)
            VALUES ($1, $2, 'Checked', $3, now() - $4::text::interval)
            """,
            version_id, decision, reviewer, at,
        )

    async def verification(version_id: int) -> str:
        path = f"proofs/{uuid4().hex}"
        w.storage.objects[path] = (b"%PDF", "application/pdf")
        await owner_db.execute(
            """
            INSERT INTO public.verification (version_id, checked_on, source, result, reference,
                                             proof_file_path, proof_original_filename,
                                             proof_content_type, recorded_by)
            VALUES ($1, '2001-01-01', 'Registry', 'confirmed', 'R-1', $2, 'proof.pdf',
                    'application/pdf', $3)
            """,
            version_id, path, reviewer,
        )
        return path

    async def path_of(version_id: int) -> str:
        return await owner_db.fetchval("SELECT file_path FROM public.version WHERE id = $1", version_id)

    async def exists(table: str, row_id: int) -> bool:
        return await owner_db.fetchval(f"SELECT EXISTS (SELECT 1 FROM public.{table} WHERE id = $1)", row_id)

    async def scheduled_run():
        await owner_db.execute(
            "UPDATE public.settings SET time_zone = 'UTC', daily_check_time = '00:00'"
        )
        await owner_db.execute("TRUNCATE public.daily_check_run")
        result = await daily_check.run_if_due(
            app_db, w.mailer, now=datetime.now(timezone.utc), storage=w.storage
        )
        assert result is not None
        return result

    async def records(target_type: str | None = None, target_id=None) -> list[dict]:
        """The retention removal records this test's runs wrote."""
        rows = await owner_db.fetch(
            """
            SELECT * FROM public.audit_log
             WHERE action = 'retention_removal' AND id > $3
               AND ($1::text IS NULL OR target_type = $1)
               AND ($2::text IS NULL OR target_id = $2)
             ORDER BY id
            """,
            target_type, None if target_id is None else str(target_id), retention_cleanup,
        )
        return [dict(r) for r in rows]

    w.seafarer, w.document, w.version, w.review = seafarer, document, version, review
    w.verification, w.path_of, w.exists = verification, path_of, exists
    w.scheduled_run, w.records = scheduled_run, records
    return w


# --- Replaced Versions -------------------------------------------------------------------


async def test_the_clock_starts_at_the_accepting_review_of_the_newer_version(w, owner_db):
    anna = await w.seafarer()
    # Both older Versions were uploaded long ago; only the Review date counts.
    due = await w.document(anna)
    old_due = await w.version(due, ago(9))
    new_due = await w.version(due, ago(8))
    await w.review(new_due, "accept", ago(5, 1))

    not_yet = await w.document(anna)
    old_kept = await w.version(not_yet, ago(9))
    new_kept = await w.version(not_yet, ago(8))
    await w.review(new_kept, "accept", ago(4, 360))

    result = await w.scheduled_run()

    assert result.retention is not None and result.retention.versions == 1
    assert not await w.exists("version", old_due)
    assert await w.exists("version", new_due)
    assert await w.exists("version", old_kept)


async def test_the_clock_starts_at_the_rejecting_review(w, owner_db):
    anna = await w.seafarer()
    doc = await w.document(anna)
    current = await w.version(doc, ago(9))
    rejected_due = await w.version(doc, ago(8))
    await w.review(rejected_due, "reject", ago(5, 1))
    rejected_kept = await w.version(doc, ago(8))
    await w.review(rejected_kept, "reject", ago(4, 360))

    await w.scheduled_run()

    assert not await w.exists("version", rejected_due)
    assert await w.exists("version", rejected_kept)
    assert await w.exists("version", current)


async def test_the_current_version_is_never_removed(w, owner_db):
    anna = await w.seafarer()
    # Accepted long ago and still the newest: current.
    alone = await w.version(await w.document(anna), ago(9))
    await w.review(alone, "accept", ago(9))
    # A newer unreviewed Version is current; the older one has no newer accepted one.
    doc = await w.document(anna)
    older = await w.version(doc, ago(9))
    await w.review(older, "accept", ago(9))
    await w.version(doc, ago(8))
    # A newer Version accepted, then overturned: the older one is current again.
    overturned_doc = await w.document(anna)
    back_to_current = await w.version(overturned_doc, ago(9))
    overturned = await w.version(overturned_doc, ago(8))
    await w.review(overturned, "accept", ago(8))
    await w.review(overturned, "reject", ago(1))

    result = await w.scheduled_run()

    assert result.retention.versions == 0
    for version_id in (alone, older, back_to_current):
        assert await w.exists("version", version_id)


async def test_a_shared_file_is_kept_while_another_version_points_to_it(w, owner_db):
    anna = await w.seafarer()
    doc = await w.document(anna)
    first = await w.version(doc, ago(9))
    shared = await w.path_of(first)
    details_only = await w.version(doc, ago(8), file_path=shared)
    await w.review(details_only, "accept", ago(6))

    renewed_doc = await w.document(anna)
    replaced = await w.version(renewed_doc, ago(9))
    own_file = await w.path_of(replaced)
    proof = await w.verification(replaced)
    renewal = await w.version(renewed_doc, ago(8))
    await w.review(renewal, "accept", ago(6))

    await w.scheduled_run()

    assert not await w.exists("version", first)
    assert not await w.exists("version", replaced)
    assert shared in w.storage.objects
    assert own_file not in w.storage.objects and proof not in w.storage.objects
    assert await owner_db.fetchval("SELECT count(*) FROM public.file_removal") == 0


async def test_each_removed_version_is_recorded_by_the_system(w, owner_db):
    anna = await w.seafarer()
    doc = await w.document(anna)
    old = await w.version(doc, ago(9))
    await w.verification(old)
    await w.review(old, "accept", ago(9))
    new = await w.version(doc, ago(8))
    await w.review(new, "accept", ago(6))

    await w.scheduled_run()

    [record] = await w.records("version", old)
    assert record["actor_id"] is None and record["actor_email"] is None
    assert record["actor_role"] == "system"
    assert record["outcome"] == "succeeded"
    assert record["seafarer_id"] == anna
    after = json.loads(record["after"])
    assert after["document_id"] == doc
    assert (after["reviews"], after["verifications"], after["files"]) == (1, 1, 2)


async def test_a_run_removes_at_most_500_versions(w, owner_db, app_db):
    with pytest.raises(asyncpg.InvalidParameterValueError):
        await app_db.fetchval("SELECT public.retention_remove_replaced_versions(501)")
    anna = await w.seafarer()
    doc = await w.document(anna)
    for _ in range(3):
        await w.review(await w.version(doc, ago(9)), "reject", ago(6))
    assert await app_db.fetchval("SELECT public.retention_remove_replaced_versions(2)") == 2


# --- Inactive seafarers ------------------------------------------------------------------


async def test_an_inactive_seafarer_is_removed_whole_and_their_audit_records_are_kept(
    w, owner_db, crew
):
    boris = await w.seafarer(inactive=ago(5, 1), name="Boris")
    vessel = await crew.vessel("Alpha")
    assignment = await owner_db.fetchval(
        """
        INSERT INTO public.assignment (seafarer_id, vessel_id, position_id, start_date, end_date)
        VALUES ($1, $2, $3, '2015-01-01', '2015-06-01') RETURNING id
        """,
        boris, vessel, w.master,
    )
    doc = await w.document(boris)
    old = await w.version(doc, ago(9))
    await w.review(old, "reject", ago(1))  # Not a Replaced Version due for removal yet.
    current = await w.version(doc, ago(8))
    await w.review(current, "accept", ago(8))
    proof = await w.verification(current)
    files = [await w.path_of(old), await w.path_of(current), proof]
    await owner_db.execute(
        "INSERT INTO public.alert (document_id, step, expiry_date) VALUES ($1, 0, '2099-01-01')", doc
    )
    about_boris = await owner_db.fetchval(
        """
        INSERT INTO public.audit_log (actor_role, action, target_type, target_id, seafarer_id)
        VALUES ('administrator', 'seafarer_set_inactive', 'seafarer', $1, $2) RETURNING id
        """,
        str(boris), boris,
    )
    recent = await w.seafarer(inactive=ago(4, 360), name="Carl")
    active = await w.seafarer(name="Dana")

    result = await w.scheduled_run()

    assert result.retention.seafarers == 1
    assert not await w.exists("seafarer", boris)
    assert not await w.exists("document", doc)
    assert not await w.exists("assignment", assignment)
    assert await owner_db.fetchval(
        "SELECT count(*) FROM public.alert WHERE document_id = $1", doc
    ) == 0
    assert all(path not in w.storage.objects for path in files)
    assert await w.exists("seafarer", recent) and await w.exists("seafarer", active)

    assert await w.exists("audit_log", about_boris)
    [record] = await w.records("seafarer", boris)
    assert record["actor_role"] == "system" and record["actor_id"] is None
    assert record["seafarer_id"] == boris
    after = json.loads(record["after"])
    assert {k: after[k] for k in ("documents", "versions", "reviews", "verifications",
                                  "assignments", "alerts", "files")} == {
        "documents": 1, "versions": 2, "reviews": 2, "verifications": 1,
        "assignments": 1, "alerts": 1, "files": 3,
    }


# --- Audit Records -----------------------------------------------------------------------


async def test_the_daily_check_leaves_old_audit_records_alone(w, owner_db):
    old = await owner_db.fetchval(
        "INSERT INTO public.audit_log (occurred_at, action) VALUES (now() - interval '8 years', "
        "'settings_changed') RETURNING id"
    )

    await w.scheduled_run()

    assert await w.exists("audit_log", old)
    assert await w.records("audit_log") == []
    run = await owner_db.fetchrow("SELECT * FROM public.daily_check_run")
    assert run["retention_finished_at"] is not None
    assert run["removed_audit_records"] is None


async def test_old_audit_records_go_with_one_summary(w, owner_db):
    insert = """
        INSERT INTO public.audit_log (occurred_at, actor_role, action)
        VALUES (now() - $1::text::interval, 'administrator', 'settings_changed') RETURNING id
    """
    # Old records other tests left behind go first.
    await owner_db.fetchval("SELECT public.retention_remove_old_audit_records()")
    old = await owner_db.fetchval(insert, ago(7, 1))
    kept = await owner_db.fetchval(insert, ago(6, 360))

    # The owner's nightly job (SR-14), not the daily check, calls it.
    assert await owner_db.fetchval("SELECT public.retention_remove_old_audit_records()") == 1

    assert not await w.exists("audit_log", old)
    assert await w.exists("audit_log", kept)
    [summary] = await w.records("audit_log")
    after = json.loads(summary["after"])
    assert after["rows"] == 1 and "cutoff" in after
    assert summary["actor_role"] == "system"


async def test_nothing_removed_records_nothing(w, owner_db):
    await w.version(await w.document(await w.seafarer()), ago(1))

    result = await w.scheduled_run()

    assert (result.retention.versions, result.retention.seafarers) == (0, 0)
    assert await w.records() == []


# --- The manual run and the file removal queue --------------------------------------------


async def test_the_manual_run_does_not_remove_anything(w, owner_db, client, mailer):
    doc = await w.document(await w.seafarer())
    old = await w.version(doc, ago(9))
    await w.review(await w.version(doc, ago(8)), "accept", ago(6))
    gone = await w.seafarer(inactive=ago(6), name="Boris")
    old_record = await owner_db.fetchval(
        "INSERT INTO public.audit_log (occurred_at, action) VALUES (now() - interval '8 years', "
        "'settings_changed') RETURNING id"
    )
    res = await client.post("/api/admin/daily-check/run", headers=auth_header(w.admin))
    assert res.status_code == 200, res.text

    assert await w.exists("version", old)
    assert await w.exists("seafarer", gone)
    assert await w.exists("audit_log", old_record)
    run = await owner_db.fetchrow("SELECT * FROM public.daily_check_run WHERE manual")
    assert run["retention_finished_at"] is None


async def test_files_that_fail_to_delete_are_retried_on_the_next_run(w, owner_db):
    doc = await w.document(await w.seafarer())
    old = await w.version(doc, ago(9))
    path = await w.path_of(old)
    await w.review(await w.version(doc, ago(8)), "accept", ago(6))
    w.storage.failing = True

    await w.scheduled_run()

    assert not await w.exists("version", old)
    assert path in w.storage.objects
    queued = await owner_db.fetchrow("SELECT * FROM public.file_removal WHERE file_path = $1", path)
    assert queued["attempts"] == 1 and "storage unavailable" in queued["last_error"]

    w.storage.failing = False
    await w.scheduled_run()

    assert path not in w.storage.objects
    assert await owner_db.fetchval("SELECT count(*) FROM public.file_removal") == 0


# --- The bypass flag -------------------------------------------------------------------------


async def test_the_bypass_flag_cannot_be_set_outside_the_functions(w, owner_db, app_db):
    doc = await w.document(await w.seafarer())
    version = await w.version(doc, ago(1))
    await w.verification(version)
    record = await owner_db.fetchval(
        "INSERT INTO public.audit_log (action) VALUES ('settings_changed') RETURNING id"
    )

    # app_backend can neither reach the flag nor delete anything itself.
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_db.execute("INSERT INTO private.retention_bypass VALUES (pg_current_xact_id())")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_db.execute("SELECT private.retention_bypass_on()")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_db.execute("DELETE FROM public.audit_log")

    # A setting any session can make doesn't count, even for the owner.
    async with owner_db.transaction():
        await owner_db.execute("SELECT set_config('app.retention_bypass', 'on', true)")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await owner_db.execute("DELETE FROM public.version WHERE id = $1", version)

    # The flag is lowered when a removal function returns, even in the same transaction.
    for statement in (
        "DELETE FROM public.version WHERE id = $1",
        "DELETE FROM public.review WHERE version_id = $1",
        "DELETE FROM public.verification WHERE version_id = $1",
        f"DELETE FROM public.audit_log WHERE id = {record} AND $1 > 0",
    ):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with owner_db.transaction():
                await owner_db.fetchval("SELECT public.retention_remove_replaced_versions()")
                await owner_db.execute("INSERT INTO public.review (version_id, decision, comment, "
                                       "reviewed_by) VALUES ($1, 'accept', 'x', $2)", version, w.admin)
                await owner_db.execute(statement, version)
    assert await w.exists("version", version)
    assert await w.exists("audit_log", record)


@pytest.mark.parametrize("role", ["anon", "authenticated", "service_role", "app_backend"])
async def test_who_may_call_the_removal_functions(w, owner_db, role):
    """The backend removes Versions and seafarers; only the owner removes Audit
    Records (SR-14)."""
    calls = ["public.retention_remove_old_audit_records()"]
    if role != "app_backend":
        calls += [
            "public.retention_remove_replaced_versions()",
            "public.retention_remove_inactive_seafarers()",
        ]
    for call in calls:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with owner_db.transaction():
                await owner_db.execute(f"SET LOCAL ROLE {role}")
                await owner_db.execute(f"SELECT {call}")


# --- The Settings page -------------------------------------------------------------------


async def test_the_settings_show_the_last_clean_up(w, owner_db, client):
    headers = auth_header(w.admin)
    res = await client.get("/api/settings", headers=headers)
    assert res.json()["last_cleanup"] is None

    doc = await w.document(await w.seafarer())
    await w.review(await w.version(doc, ago(9)), "reject", ago(6))
    await w.seafarer(inactive=ago(6), name="Boris")
    result = await w.scheduled_run()

    body = (await client.get("/api/settings", headers=headers)).json()
    assert body["last_cleanup"]["local_date"] == result.local_date.isoformat()
    assert body["last_cleanup"]["versions"] == 1
    assert body["last_cleanup"]["seafarers"] == 1
    assert "audit_records" not in body["last_cleanup"]
    assert body["last_cleanup"]["finished_at"]


async def test_the_settings_show_the_last_audit_record_removal(w, owner_db, client):
    headers = auth_header(w.admin)
    before = (await client.get("/api/settings", headers=headers)).json()["last_audit_cleanup"]

    await owner_db.execute(
        "INSERT INTO public.audit_log (occurred_at, action) VALUES (now() - interval '8 years', "
        "'settings_changed')"
    )
    removed = await owner_db.fetchval("SELECT public.retention_remove_old_audit_records()")

    after = (await client.get("/api/settings", headers=headers)).json()["last_audit_cleanup"]
    assert after["rows"] == removed >= 1
    assert after["removed_at"]
    assert before is None or before["removed_at"] < after["removed_at"]
