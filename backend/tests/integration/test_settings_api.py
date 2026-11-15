"""The Settings page through the HTTP API (FR-25, T9, T7).

Any active account reads; administrators save. A save carries the version it
started from, and a stale one is refused. A changing save writes one
*settings changed* Audit Record; a no-change save writes nothing.
"""

import json

import pytest

from tests.conftest import auth_header

DEFAULTS = {
    "alert_steps": [90, 60, 30, 0],
    "planning_horizon_days": 90,
    "max_file_size_mb": 4,
    "max_pdf_pages": 50,
    "time_zone": "UTC",
    "daily_check_time": "07:00",
}


@pytest.fixture
async def admin_id(make_account, settings_reset):
    return await make_account(role="administrator")


@pytest.fixture
def admin(admin_id):
    return auth_header(admin_id)


async def _settings_records(owner_db, actor_id) -> list[dict]:
    rows = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE action = 'settings_changed' AND actor_id = $1 ORDER BY id",
        actor_id,
    )
    return [dict(r) for r in rows]


async def _current(client, headers) -> dict:
    res = await client.get("/api/settings", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


async def test_any_active_account_reads_the_settings(client, make_account, settings_reset):
    for role in ("administrator", "crewing_officer", "manager"):
        body = await _current(client, auth_header(await make_account(role=role)))
        assert {k: body[k] for k in DEFAULTS} == DEFAULTS
        assert body["version"] == 1


async def test_a_pending_account_cannot_read_the_settings(client, make_account, settings_reset):
    res = await client.get("/api/settings", headers=auth_header(await make_account(status="pending")))
    assert res.status_code == 403


async def test_an_officer_cannot_save(client, make_account, settings_reset, owner_db):
    officer = auth_header(await make_account(role="crewing_officer"))
    res = await client.put(
        "/api/settings", json={**DEFAULTS, "planning_horizon_days": 30, "version": 1}, headers=officer
    )
    assert res.status_code == 403
    assert await owner_db.fetchval("SELECT planning_horizon_days FROM public.settings") == 90


async def test_a_changing_save_applies_and_writes_one_record(client, admin, admin_id, owner_db):
    body = {
        **DEFAULTS,
        "alert_steps": [0, 14, 60],
        "planning_horizon_days": 120,
        "time_zone": "Europe/Malta",
        "version": 1,
    }
    res = await client.put("/api/settings", json=body, headers=admin)
    assert res.status_code == 200, res.text
    saved = res.json()
    assert saved["alert_steps"] == [60, 14, 0]
    assert saved["version"] == 2

    # Applies from the next request, no restart.
    current = await _current(client, admin)
    assert current["planning_horizon_days"] == 120
    assert current["time_zone"] == "Europe/Malta"
    assert current["version"] == 2

    [record] = await _settings_records(owner_db, admin_id)
    assert record["target_type"] == "settings"
    assert record["outcome"] == "succeeded"
    assert json.loads(record["before"]) == {
        "alert_steps": [90, 60, 30, 0],
        "planning_horizon_days": 90,
        "time_zone": "UTC",
    }
    assert json.loads(record["after"]) == {
        "alert_steps": [60, 14, 0],
        "planning_horizon_days": 120,
        "time_zone": "Europe/Malta",
    }
    assert await owner_db.fetchval("SELECT updated_by FROM public.settings") == admin_id


async def test_the_check_time_is_recorded_as_hh_mm(client, admin, admin_id, owner_db):
    res = await client.put(
        "/api/settings", json={**DEFAULTS, "daily_check_time": "06:45", "version": 1}, headers=admin
    )
    assert res.status_code == 200
    assert res.json()["daily_check_time"] == "06:45"
    [record] = await _settings_records(owner_db, admin_id)
    assert json.loads(record["before"]) == {"daily_check_time": "07:00"}
    assert json.loads(record["after"]) == {"daily_check_time": "06:45"}


async def test_a_no_change_save_writes_nothing(client, admin, admin_id, owner_db):
    # Same steps in another order are no change either.
    body = {**DEFAULTS, "alert_steps": [0, 30, 60, 90], "version": 1}
    res = await client.put("/api/settings", json=body, headers=admin)
    assert res.status_code == 200
    assert res.json()["version"] == 1
    assert await _settings_records(owner_db, admin_id) == []


async def test_a_stale_save_is_a_conflict(client, admin, admin_id, owner_db):
    first = await client.put(
        "/api/settings", json={**DEFAULTS, "max_pdf_pages": 100, "version": 1}, headers=admin
    )
    assert first.status_code == 200

    # A second editor still holding version 1.
    stale = await client.put(
        "/api/settings", json={**DEFAULTS, "max_file_size_mb": 3, "version": 1}, headers=admin
    )
    assert stale.status_code == 409
    assert "reload" in stale.json()["detail"].lower()

    row = await owner_db.fetchrow("SELECT max_pdf_pages, max_file_size_mb, version FROM public.settings")
    assert dict(row) == {"max_pdf_pages": 100, "max_file_size_mb": 4, "version": 2}
    assert len(await _settings_records(owner_db, admin_id)) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"alert_steps": [90, 60]},
        {"planning_horizon_days": 366},
        {"max_file_size_mb": 5},
        {"max_pdf_pages": 0},
        {"time_zone": "Mars/Olympus"},
        {"daily_check_time": "07:10"},
    ],
)
async def test_invalid_values_are_refused(client, admin, owner_db, change):
    res = await client.put("/api/settings", json={**DEFAULTS, **change, "version": 1}, headers=admin)
    assert res.status_code == 422
    assert await owner_db.fetchval("SELECT version FROM public.settings") == 1
