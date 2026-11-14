"""Audit Log search and export through the HTTP API (FR-23, T7, ADR 0002).

Administrators only. The search is paginated and newest first; filters
combine. The export takes the same filters, is capped and shows timestamps in
the company time zone. Every search and export writes its own Audit Record.

The Audit Log is append-only and shared, so each test writes its records
under a fresh actor id and filters by it.
"""

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.services import audit_log
from tests.conftest import auth_header

NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture
async def admin_id(make_account, settings_reset):
    return await make_account(role="administrator")


@pytest.fixture
def admin(admin_id):
    return auth_header(admin_id)


@pytest.fixture
def actor() -> UUID:
    """The made-up actor whose records a test searches for."""
    return uuid4()


@pytest.fixture
def write(owner_db, actor):
    """Insert one Audit Record as the owner (the app may only insert through
    the helper) and return its id."""

    async def _write(action: str, occurred_at: datetime = NOW, **fields) -> int:
        values = {
            "actor_id": actor,
            "actor_email": "someone@example.com",
            "actor_role": "crewing_officer",
            "action": action,
            "outcome": "succeeded",
            "occurred_at": occurred_at,
            **fields,
        }
        columns = ", ".join(values)
        placeholders = ", ".join(f"${i}" for i in range(1, len(values) + 1))
        return await owner_db.fetchval(
            f"INSERT INTO public.audit_log ({columns}) VALUES ({placeholders}) RETURNING id",
            *values.values(),
        )

    return _write


async def _search(client, headers, **params) -> dict:
    res = await client.get("/api/audit", params=params, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _ids(body: dict) -> list[int]:
    return [item["id"] for item in body["items"]]


def _rows(res) -> list[dict]:
    return list(csv.DictReader(io.StringIO(res.text)))


async def _records(owner_db, actor_id: UUID, action: str) -> list[dict]:
    rows = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE actor_id = $1 AND action = $2 ORDER BY id",
        actor_id, action,
    )
    return [dict(r) for r in rows]


async def test_search_is_newest_first(client, admin, actor, write):
    old = await write("vessel_created", NOW - timedelta(days=2))
    new = await write("vessel_edited", NOW - timedelta(days=1))
    newest = await write("vessel_deactivated", NOW)

    body = await _search(client, admin, actor_id=str(actor))
    assert _ids(body) == [newest, new, old]
    assert body["total"] == 3


async def test_search_is_paginated(client, admin, actor, write):
    ids = [await write("vessel_edited", NOW - timedelta(minutes=m)) for m in range(5)]

    first = await _search(client, admin, actor_id=str(actor), page=1, page_size=2)
    third = await _search(client, admin, actor_id=str(actor), page=3, page_size=2)
    assert _ids(first) == ids[:2]
    assert _ids(third) == ids[4:]
    assert first["total"] == third["total"] == 5
    assert (first["page"], first["page_size"]) == (1, 2)


async def test_filters_combine(client, admin, actor, write):
    wanted = await write(
        "seafarer_edited", NOW - timedelta(days=1),
        seafarer_id=7, target_type="seafarer", target_id="7",
    )
    also_wanted = await write(
        "seafarer_created", NOW - timedelta(days=2),
        seafarer_id=7, target_type="seafarer", target_id="7",
    )
    await write("seafarer_edited", NOW - timedelta(days=10), seafarer_id=7,
                target_type="seafarer", target_id="7")  # before the range
    await write("seafarer_edited", NOW - timedelta(days=1), seafarer_id=8,
                target_type="seafarer", target_id="8")  # another seafarer
    await write("seafarer_set_inactive", NOW - timedelta(days=1), seafarer_id=7,
                target_type="seafarer", target_id="7")  # another action
    await write("seafarer_edited", NOW - timedelta(days=1), seafarer_id=7,
                target_type="seafarer", target_id="7", outcome="refused")  # refused
    await write("vessel_edited", NOW - timedelta(days=1))
    await write("seafarer_edited", NOW - timedelta(days=1), seafarer_id=7,
                target_type="seafarer", target_id="7", actor_id=uuid4())  # someone else

    params = [
        ("actor_id", str(actor)),
        ("action", "seafarer_edited"),
        ("action", "seafarer_created"),
        ("seafarer_id", "7"),
        ("target_type", "seafarer"),
        ("target_id", "7"),
        ("outcome", "succeeded"),
        ("date_from", (NOW - timedelta(days=5)).date().isoformat()),
        ("date_to", NOW.date().isoformat()),
    ]
    res = await client.get("/api/audit", params=params, headers=admin)
    assert res.status_code == 200, res.text
    assert _ids(res.json()) == [wanted, also_wanted]


async def test_outcome_filter_finds_refusals(client, admin, actor, write):
    refused = await write("access_refused", outcome="refused", reason="wrong_role")
    await write("vessel_edited")

    body = await _search(client, admin, actor_id=str(actor), outcome="refused")
    assert _ids(body) == [refused]
    assert body["items"][0]["reason"] == "wrong_role"


async def test_actor_email_filter_matches_part_of_the_address(client, admin, actor, write):
    found = await write("vessel_edited", actor_email="Maria.Ortiz@example.com")
    await write("vessel_edited", actor_email="someone@example.com")

    body = await _search(client, admin, actor_id=str(actor), actor_email="maria.ortiz")
    assert _ids(body) == [found]


async def test_date_range_is_whole_days_in_the_company_time_zone(
    client, admin, actor, write, owner_db
):
    await owner_db.execute("UPDATE public.settings SET time_zone = 'Pacific/Auckland'")
    # 2026-03-01 11:30 UTC is 2026-03-02 00:30 in Auckland (UTC+13).
    inside = await write("vessel_edited", datetime(2026, 3, 1, 11, 30, tzinfo=timezone.utc))
    # 2026-03-01 10:30 UTC is still 2026-03-01 23:30 in Auckland.
    await write("vessel_edited", datetime(2026, 3, 1, 10, 30, tzinfo=timezone.utc))

    body = await _search(
        client, admin, actor_id=str(actor), date_from="2026-03-02", date_to="2026-03-02"
    )
    assert _ids(body) == [inside]


@pytest.mark.parametrize(
    "params",
    [
        {"action": "not_an_action"},
        {"outcome": "maybe"},
        {"date_from": "2026-03-02", "date_to": "2026-03-01"},
        {"page": "0"},
        {"page_size": "1000"},
    ],
)
async def test_invalid_filters_are_refused(client, admin, params):
    res = await client.get("/api/audit", params=params, headers=admin)
    assert res.status_code == 422


async def test_each_search_writes_its_own_record(client, admin, admin_id, actor, write, owner_db):
    await write("vessel_edited")

    await _search(client, admin, actor_id=str(actor), action="vessel_edited")
    await _search(client, admin, actor_id=str(actor), page=2)

    first, second = await _records(owner_db, admin_id, "audit_searched")
    assert first["target_type"] == "audit_log"
    assert first["outcome"] == "succeeded"
    assert json.loads(first["after"]) == {
        "filters": {"actor_id": str(actor), "action": ["vessel_edited"]},
        "page": 1,
        "results": 1,
    }
    assert json.loads(second["after"])["page"] == 2


async def test_a_search_does_not_find_its_own_record(client, admin, admin_id):
    body = await _search(client, admin, actor_id=str(admin_id))
    assert body["items"] == []


async def test_export_has_the_filtered_records_newest_first(client, admin, actor, write):
    old = await write("vessel_created", NOW - timedelta(days=1), target_type="vessel",
                      target_id="3", before=json.dumps({"name": "A"}),
                      after=json.dumps({"name": "B"}))
    new = await write("vessel_edited", NOW, target_type="vessel", target_id="3")
    await write("position_created", NOW)

    res = await client.get(
        "/api/audit/export.csv",
        params=[("actor_id", str(actor)), ("action", "vessel_created"), ("action", "vessel_edited")],
        headers=admin,
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers["content-disposition"]
    assert res.headers["x-export-truncated"] == "false"
    rows = _rows(res)
    assert [int(r["id"]) for r in rows] == [new, old]
    assert rows[1]["action"] == "vessel_created"
    assert rows[1]["target_type"] == "vessel"
    assert json.loads(rows[1]["before"]) == {"name": "A"}
    assert rows[0]["before"] == ""


async def test_export_timestamps_are_in_the_company_time_zone(
    client, admin, actor, write, owner_db
):
    await owner_db.execute("UPDATE public.settings SET time_zone = 'Europe/Malta'")
    await write("vessel_edited", datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc))

    res = await client.get("/api/audit/export.csv", params={"actor_id": str(actor)}, headers=admin)
    [row] = _rows(res)
    assert row["occurred_at"] == "2026-07-01 12:00:00+02:00"


async def test_export_is_capped(client, admin, admin_id, actor, write, owner_db, monkeypatch):
    assert audit_log.EXPORT_CAP == 50_000
    monkeypatch.setattr(audit_log, "EXPORT_CAP", 2)
    ids = [await write("vessel_edited", NOW - timedelta(minutes=m)) for m in range(3)]

    res = await client.get("/api/audit/export.csv", params={"actor_id": str(actor)}, headers=admin)
    assert res.status_code == 200
    assert [int(r["id"]) for r in _rows(res)] == ids[:2]
    assert res.headers["x-export-truncated"] == "true"

    [record] = await _records(owner_db, admin_id, "audit_exported")
    assert json.loads(record["after"])["rows"] == 2
    assert json.loads(record["after"])["truncated"] is True


async def test_export_neutralises_spreadsheet_formulas(client, admin, actor, write):
    await write("access_refused", outcome="refused", reason="=HYPERLINK(\"x\")")

    res = await client.get("/api/audit/export.csv", params={"actor_id": str(actor)}, headers=admin)
    [row] = _rows(res)
    assert row["reason"] == "'=HYPERLINK(\"x\")"


async def test_each_export_writes_its_own_record(client, admin, admin_id, actor, write, owner_db):
    await write("vessel_edited")

    res = await client.get(
        "/api/audit/export.csv", params={"actor_id": str(actor), "outcome": "succeeded"},
        headers=admin,
    )
    assert res.status_code == 200
    # The export's own record isn't in the file it describes.
    assert len(_rows(res)) == 1

    [record] = await _records(owner_db, admin_id, "audit_exported")
    assert record["target_type"] == "audit_log"
    assert json.loads(record["after"]) == {
        "filters": {"actor_id": str(actor), "outcome": "succeeded"},
        "rows": 1,
        "truncated": False,
    }
    assert await _records(owner_db, admin_id, "audit_searched") == []


@pytest.mark.parametrize("path", ["/api/audit", "/api/audit/export.csv"])
@pytest.mark.parametrize("role", ["crewing_officer", "manager"])
async def test_only_administrators_search_or_export(client, make_account, owner_db, path, role):
    someone = await make_account(role=role)

    res = await client.get(path, headers=auth_header(someone))
    assert res.status_code == 403

    [refused] = await _records(owner_db, someone, "access_refused")
    assert refused["outcome"] == "refused"
    assert refused["reason"] == "wrong_role"
    assert refused["target_id"] == f"GET {path}"
    assert await _records(owner_db, someone, "audit_searched") == []
    assert await _records(owner_db, someone, "audit_exported") == []


async def test_the_app_cannot_change_or_remove_audit_records(app, actor, write):
    """Nobody can edit or delete the log, administrators included (ADR 0002)."""
    import asyncpg

    from app.db import get_pool

    record_id = await write("vessel_edited")
    pool = await get_pool()
    async with pool.acquire() as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("UPDATE public.audit_log SET reason = 'x' WHERE id = $1", record_id)
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("DELETE FROM public.audit_log WHERE id = $1", record_id)
