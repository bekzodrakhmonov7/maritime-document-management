"""Seafarer records through the HTTP API (FR-04, T3, T5, T7).

Administrators and crewing officers (within Scope) keep one record per
Seafarer with a held Position; managers get 403. Seafarers are set Inactive
and reactivated, never deleted. Every write leaves an Audit Record.
"""

from datetime import date
from uuid import uuid4

import pytest

from app.domain import today_in
from app.models.auth import UserPayload
from app.scope import seafarer_scope
from app.services import errors, seafarers
from tests.conftest import auth_header

pytestmark = pytest.mark.usefixtures("reference_cleanup")


async def _audit(owner_db, seafarer_id) -> list[dict]:
    rows = await owner_db.fetch(
        """
        SELECT * FROM public.audit_log
         WHERE target_type = 'seafarer' AND target_id = $1
         ORDER BY id
        """,
        str(seafarer_id),
    )
    return [dict(r) for r in rows]


@pytest.fixture
async def admin(make_account):
    return auth_header(await make_account(role="administrator"))


@pytest.fixture
async def officer(make_account):
    return auth_header(await make_account(role="crewing_officer"))


@pytest.fixture
async def manager(make_account):
    return auth_header(await make_account(role="manager"))


@pytest.fixture
async def master(owner_db) -> int:
    return await owner_db.fetchval("INSERT INTO public.position (name) VALUES ('Master') RETURNING id")


@pytest.fixture
async def cook(owner_db) -> int:
    return await owner_db.fetchval("INSERT INTO public.position (name) VALUES ('Cook') RETURNING id")


def _body(position_id: int, **fields) -> dict:
    return {
        "first_name": "Anna",
        "last_name": "Petrova",
        "date_of_birth": "1988-03-14",
        "nationality": "BG",
        "position_id": position_id,
        **fields,
    }


async def _create(client, headers, body: dict) -> dict:
    res = await client.post("/api/seafarers", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


async def _set_inactive(client, headers, seafarer_id: int, reason: str = "Left the company"):
    return await client.post(
        f"/api/seafarers/{seafarer_id}/set-inactive", json={"reason": reason}, headers=headers
    )


# --- Create, read, edit ------------------------------------------------------------


async def test_an_officer_creates_a_seafarer_with_a_held_position(client, officer, master, owner_db):
    seafarer = await _create(client, officer, _body(master))
    assert seafarer["position_id"] == master
    assert seafarer["position_name"] == "Master"
    assert seafarer["nationality"] == "BG"
    assert seafarer["inactive_since"] is None

    [record] = await _audit(owner_db, seafarer["id"])
    assert record["action"] == "seafarer_created"
    assert record["seafarer_id"] == seafarer["id"]
    assert '"last_name": "Petrova"' in record["after"]


async def test_the_seafarer_table_has_no_vessel_or_rank(owner_db):
    columns = await owner_db.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'seafarer'"
    )
    names = {c["column_name"] for c in columns}
    assert {"position_id", "inactive_since", "inactive_reason"} <= names
    assert not names & {"vessel_id", "rank"}


async def test_an_officer_reads_a_seafarer(client, officer, master):
    seafarer = await _create(client, officer, _body(master))
    res = await client.get(f"/api/seafarers/{seafarer['id']}", headers=officer)
    assert res.status_code == 200
    assert res.json()["first_name"] == "Anna"


async def test_an_unknown_seafarer_is_404(client, admin):
    assert (await client.get("/api/seafarers/999999", headers=admin)).status_code == 404


async def test_a_retired_position_cannot_be_picked(client, admin, master, owner_db):
    await owner_db.execute("UPDATE public.position SET retired = true WHERE id = $1", master)
    res = await client.post("/api/seafarers", json=_body(master), headers=admin)
    assert res.status_code == 422
    assert "retired" in res.json()["detail"]


async def test_an_unknown_position_cannot_be_picked(client, admin):
    res = await client.post("/api/seafarers", json=_body(999999), headers=admin)
    assert res.status_code == 422


async def test_a_nationality_must_be_an_assigned_iso_code(client, admin, master):
    res = await client.post("/api/seafarers", json=_body(master, nationality="XX"), headers=admin)
    assert res.status_code == 422


async def test_the_date_of_birth_is_checked_against_the_company_today(
    client, admin, master, owner_db, settings_reset
):
    # Kiritimati (UTC+14) is always at least a day ahead of Pago Pago (UTC-11).
    ahead = today_in("Pacific/Kiritimati").isoformat()
    await owner_db.execute("UPDATE public.settings SET time_zone = 'Pacific/Pago_Pago'")
    res = await client.post("/api/seafarers", json=_body(master, date_of_birth=ahead), headers=admin)
    assert res.status_code == 422
    [error] = res.json()["detail"]
    assert error["loc"] == ["body", "date_of_birth"]
    assert "must be a date in the past" in error["msg"]

    await owner_db.execute("UPDATE public.settings SET time_zone = 'Pacific/Kiritimati'")
    seafarer = await _create(client, admin, _body(master, date_of_birth=ahead))
    await owner_db.execute("UPDATE public.settings SET time_zone = 'Pacific/Pago_Pago'")
    res = await client.put(
        f"/api/seafarers/{seafarer['id']}", json=_body(master, date_of_birth=ahead), headers=admin
    )
    assert res.status_code == 422


async def test_editing_records_only_the_changed_fields(client, officer, master, cook, owner_db):
    seafarer = await _create(client, officer, _body(master))
    res = await client.put(
        f"/api/seafarers/{seafarer['id']}", json=_body(cook), headers=officer
    )
    assert res.status_code == 200
    assert res.json()["position_name"] == "Cook"

    record = (await _audit(owner_db, seafarer["id"]))[-1]
    assert record["action"] == "seafarer_edited"
    assert record["seafarer_id"] == seafarer["id"]
    assert record["before"] == f'{{"position_id": {master}}}'
    assert record["after"] == f'{{"position_id": {cook}}}'


async def test_an_edit_that_changes_nothing_writes_no_record(client, officer, master, owner_db):
    seafarer = await _create(client, officer, _body(master))
    res = await client.put(f"/api/seafarers/{seafarer['id']}", json=_body(master), headers=officer)
    assert res.status_code == 200
    assert [r["action"] for r in await _audit(owner_db, seafarer["id"])] == ["seafarer_created"]


async def test_an_edit_may_keep_a_position_retired_since(client, admin, master, cook, owner_db):
    seafarer = await _create(client, admin, _body(master))
    await owner_db.execute("UPDATE public.position SET retired = true WHERE id = $1", master)

    kept = await client.put(
        f"/api/seafarers/{seafarer['id']}", json=_body(master, first_name="Ana"), headers=admin
    )
    assert kept.status_code == 200
    await owner_db.execute("UPDATE public.position SET retired = true WHERE id = $1", cook)
    moved = await client.put(f"/api/seafarers/{seafarer['id']}", json=_body(cook), headers=admin)
    assert moved.status_code == 422


async def test_a_used_position_cannot_be_deleted(client, admin, master):
    await _create(client, admin, _body(master))
    res = await client.delete(f"/api/positions/{master}", headers=admin)
    assert res.status_code == 409
    assert "retire" in res.json()["detail"].lower()


# --- Inactive ------------------------------------------------------------------------


async def test_set_inactive_and_reactivate_are_audited(client, officer, master, owner_db):
    seafarer = await _create(client, officer, _body(master))
    sid = seafarer["id"]

    res = await _set_inactive(client, officer, sid, "  Retired from the sea  ")
    assert res.status_code == 200
    assert res.json()["inactive_since"] is not None
    assert res.json()["inactive_reason"] == "Retired from the sea"
    assert (await _set_inactive(client, officer, sid)).status_code == 409

    res = await client.post(f"/api/seafarers/{sid}/reactivate", headers=officer)
    assert res.status_code == 200
    assert res.json()["inactive_since"] is None
    assert res.json()["inactive_reason"] is None
    assert (await client.post(f"/api/seafarers/{sid}/reactivate", headers=officer)).status_code == 409

    records = await _audit(owner_db, sid)
    assert [r["action"] for r in records] == [
        "seafarer_created",
        "seafarer_set_inactive",
        "seafarer_reactivated",
    ]
    assert records[1]["reason"] == "Retired from the sea"
    assert all(r["seafarer_id"] == sid for r in records)


async def test_set_inactive_needs_a_reason(client, officer, master):
    seafarer = await _create(client, officer, _body(master))
    res = await _set_inactive(client, officer, seafarer["id"], "   ")
    assert res.status_code == 422


async def test_inactive_seafarers_are_hidden_unless_asked_for(client, officer, master):
    active = await _create(client, officer, _body(master, first_name="Ivan"))
    gone = await _create(client, officer, _body(master, first_name="Olga"))
    assert (await _set_inactive(client, officer, gone["id"])).status_code == 200

    default = await client.get("/api/seafarers", headers=officer)
    assert default.status_code == 200
    assert [s["id"] for s in default.json()] == [active["id"]]

    shown = await client.get("/api/seafarers", params={"show_inactive": "true"}, headers=officer)
    assert {s["id"] for s in shown.json()} == {active["id"], gone["id"]}


async def test_the_list_searches_by_name(client, officer, master):
    anna = await _create(client, officer, _body(master))
    await _create(client, officer, _body(master, first_name="Ivan", last_name="Horvat"))
    await _create(client, officer, _body(master, first_name="Maria", last_name="50%_off"))

    for search in ("petro", "ANNA", "anna petrova", "Petrova Anna"):
        res = await client.get("/api/seafarers", params={"search": search}, headers=officer)
        assert [s["id"] for s in res.json()] == [anna["id"]], search
    res = await client.get("/api/seafarers", params={"search": "%"}, headers=officer)
    assert [s["last_name"] for s in res.json()] == ["50%_off"]


# --- Who may do it ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/api/seafarers"),
        ("GET", "/api/seafarers/{id}"),
        ("POST", "/api/seafarers"),
        ("PUT", "/api/seafarers/{id}"),
        ("POST", "/api/seafarers/{id}/set-inactive"),
        ("POST", "/api/seafarers/{id}/reactivate"),
    ],
)
async def test_a_manager_gets_403(client, admin, manager, master, owner_db, method, path):
    seafarer = await _create(client, admin, _body(master))
    res = await client.request(
        method,
        path.format(id=seafarer["id"]),
        json={**_body(master, first_name="Hijacked"), "reason": "x"},
        headers=manager,
    )
    assert res.status_code == 403
    row = await owner_db.fetchrow(
        "SELECT first_name, inactive_since FROM public.seafarer WHERE id = $1", seafarer["id"]
    )
    assert (row["first_name"], row["inactive_since"]) == ("Anna", None)
    refused = await owner_db.fetchval(
        """
        SELECT count(*) FROM public.audit_log
         WHERE action = 'access_refused' AND target_id = $1
        """,
        f"{method} {path.format(id=seafarer['id'])}",
    )
    assert refused >= 1


async def test_there_is_no_delete(client, admin, master, owner_db):
    seafarer = await _create(client, admin, _body(master))
    res = await client.delete(f"/api/seafarers/{seafarer['id']}", headers=admin)
    assert res.status_code == 405
    assert await owner_db.fetchval(
        "SELECT count(*) FROM public.seafarer WHERE id = $1", seafarer["id"]
    ) == 1


async def test_app_backend_cannot_delete_seafarers(owner_db):
    can_delete = await owner_db.fetchval(
        "SELECT has_table_privilege('app_backend', 'public.seafarer', 'DELETE')"
    )
    assert can_delete is False


# --- The Scope function -----------------------------------------------------------------


def _account(role: str, status: str = "active") -> UserPayload:
    return UserPayload(sub=uuid4(), email="x@example.com", status=status, role=role)


@pytest.mark.parametrize(
    "role, status, sees_everyone",
    [
        ("administrator", "active", True),
        # With no Assignments, everyone is in the Unassigned Pool.
        ("crewing_officer", "active", True),
        ("crewing_officer", "deactivated", False),
        ("manager", "active", False),
        ("administrator", "deactivated", False),
    ],
)
async def test_the_scope_function(client, admin, master, owner_db, role, status, sees_everyone):
    first = await _create(client, admin, _body(master))
    second = await _create(client, admin, _body(master, first_name="Ivan"))
    scope = seafarer_scope(_account(role, status), date.today())

    listed = await seafarers.list_seafarers(owner_db, scope)
    expected = {first["id"], second["id"]} if sees_everyone else set()
    assert {s["id"] for s in listed} == expected


async def test_a_seafarer_outside_the_scope_is_told_apart_from_a_missing_one(
    client, admin, master, owner_db
):
    seafarer = await _create(client, admin, _body(master))
    nobody = seafarer_scope(_account("manager"), date.today())

    with pytest.raises(errors.OutOfScope) as refused:
        await seafarers.get_seafarer(owner_db, nobody, seafarer["id"])
    assert refused.value.seafarer_id == seafarer["id"]
    with pytest.raises(errors.NotFound):
        await seafarers.get_seafarer(owner_db, nobody, 999999)
