"""Responsible Officer links through the HTTP API (FR-02, FR-03, T5, T7).

Administrators link crewing officers to vessels and remove the links. A role
change away from crewing officer drops them; a deactivated officer keeps them
(ignored until reactivated). The approval form may link vessels at once.
"""

import pytest

from tests.conftest import auth_header


@pytest.fixture
async def world(crew, make_account):
    return {
        "alpha": await crew.vessel("Alpha"),
        "bravo": await crew.vessel("Bravo"),
        "officer": await make_account(role="crewing_officer", full_name="Olga Officer"),
        "admin": auth_header(await make_account(role="administrator")),
    }


def _path(vessel_id: int, account_id=None) -> str:
    base = f"/api/vessels/{vessel_id}/responsible-officers"
    return f"{base}/{account_id}" if account_id else base


async def _links(owner_db, account_id) -> set[int]:
    rows = await owner_db.fetch(
        "SELECT vessel_id FROM public.responsible_officer WHERE user_id = $1", account_id
    )
    return {r["vessel_id"] for r in rows}


async def _records(owner_db, action: str, vessel_id: int) -> list[dict]:
    rows = await owner_db.fetch(
        """
        SELECT * FROM public.audit_log
         WHERE action = $1 AND target_type = 'vessel' AND target_id = $2 ORDER BY id
        """,
        action, str(vessel_id),
    )
    return [dict(r) for r in rows]


async def _add(client, world, vessel: str, account_id=None):
    return await client.post(
        _path(world[vessel]),
        json={"account_id": str(account_id or world["officer"])},
        headers=world["admin"],
    )


async def test_an_administrator_links_and_unlinks_an_officer(client, world, owner_db):
    res = await _add(client, world, "alpha")
    assert res.status_code == 201
    assert [(o["full_name"], o["status"]) for o in res.json()] == [("Olga Officer", "active")]
    assert await _links(owner_db, world["officer"]) == {world["alpha"]}
    assert (await _add(client, world, "alpha")).status_code == 409

    [added] = await _records(owner_db, "responsible_officer_added", world["alpha"])
    assert str(world["officer"]) in added["after"]

    listed = await client.get(_path(world["alpha"]), headers=world["admin"])
    assert [o["id"] for o in listed.json()] == [str(world["officer"])]

    res = await client.delete(_path(world["alpha"], world["officer"]), headers=world["admin"])
    assert res.status_code == 204
    assert await _links(owner_db, world["officer"]) == set()
    [removed] = await _records(owner_db, "responsible_officer_removed", world["alpha"])
    assert str(world["officer"]) in removed["before"]

    res = await client.delete(_path(world["alpha"], world["officer"]), headers=world["admin"])
    assert res.status_code == 404


@pytest.mark.parametrize("role", ["administrator", "manager"])
async def test_only_a_crewing_officer_can_be_linked(client, world, make_account, role):
    other = await make_account(role=role)
    assert (await _add(client, world, "alpha", other)).status_code == 422


async def test_an_inactive_vessel_or_unknown_one_cannot_be_linked(client, world, crew):
    laid_up = await crew.vessel("Laid Up", active=False)
    res = await client.post(
        _path(laid_up), json={"account_id": str(world["officer"])}, headers=world["admin"]
    )
    assert res.status_code == 422
    res = await client.post(
        _path(999999), json={"account_id": str(world["officer"])}, headers=world["admin"]
    )
    assert res.status_code == 404


@pytest.mark.parametrize(
    "method, suffix, role",
    [
        ("POST", "", "crewing_officer"),
        ("DELETE", "/{account}", "crewing_officer"),
        ("POST", "", "manager"),
        ("GET", "", "manager"),
    ],
)
async def test_the_wrong_role_gets_403_and_is_recorded(
    client, world, make_account, crew, owner_db, method, suffix, role
):
    await crew.link(world["officer"], world["alpha"])
    caller = await make_account(role=role)
    path = _path(world["alpha"]) + suffix.format(account=world["officer"])
    res = await client.request(
        method, path, json={"account_id": str(world["officer"])}, headers=auth_header(caller)
    )
    assert res.status_code == 403
    assert await _links(owner_db, world["officer"]) == {world["alpha"]}
    assert await owner_db.fetchval(
        """
        SELECT count(*) FROM public.audit_log
         WHERE action = 'access_refused' AND actor_id = $1 AND target_id = $2
        """,
        caller, f"{method} {path}",
    ) == 1


async def test_an_officer_reads_a_vessels_responsible_officers(client, world, crew, make_account):
    await crew.link(world["officer"], world["alpha"])
    reader = auth_header(await make_account(role="crewing_officer"))
    res = await client.get(_path(world["alpha"]), headers=reader)
    assert res.status_code == 200
    assert len(res.json()) == 1


# --- Accounts ------------------------------------------------------------------------------


async def test_a_role_change_away_from_crewing_officer_drops_the_links(client, world, crew, owner_db):
    await crew.link(world["officer"], world["alpha"], world["bravo"])
    res = await client.post(
        f"/api/accounts/{world['officer']}/role",
        json={"role": "manager", "reason": "Moved to management"},
        headers=world["admin"],
    )
    assert res.status_code == 200, res.text
    assert await _links(owner_db, world["officer"]) == set()
    for vessel in ("alpha", "bravo"):
        [removed] = await _records(owner_db, "responsible_officer_removed", world[vessel])
        assert removed["reason"] == "Moved to management"


async def test_a_deactivated_officers_links_are_kept_and_count_again_on_reactivation(
    client, world, crew, owner_db
):
    await crew.link(world["officer"], world["alpha"])
    account = f"/api/accounts/{world['officer']}"
    filtered = {"without_active_officer": "true"}

    res = await client.get("/api/vessels", params=filtered, headers=world["admin"])
    assert [v["name"] for v in res.json()] == ["Bravo"]

    await client.post(f"{account}/deactivate", json={"reason": "Leave"}, headers=world["admin"])
    assert await _links(owner_db, world["officer"]) == {world["alpha"]}
    res = await client.get("/api/vessels", params=filtered, headers=world["admin"])
    assert [v["name"] for v in res.json()] == ["Alpha", "Bravo"]

    await client.post(f"{account}/reactivate", json={"reason": "Back"}, headers=world["admin"])
    res = await client.get("/api/vessels", params=filtered, headers=world["admin"])
    assert [v["name"] for v in res.json()] == ["Bravo"]


async def test_reactivating_with_another_role_drops_the_links(client, world, crew, owner_db):
    await crew.link(world["officer"], world["alpha"])
    account = f"/api/accounts/{world['officer']}"
    await client.post(f"{account}/deactivate", json={"reason": "Leave"}, headers=world["admin"])
    res = await client.post(
        f"{account}/reactivate", json={"reason": "Back", "role": "manager"}, headers=world["admin"]
    )
    assert res.status_code == 200, res.text
    assert await _links(owner_db, world["officer"]) == set()


async def test_approving_an_officer_links_the_picked_vessels(client, world, make_account, owner_db):
    pending = await make_account(status="pending")
    res = await client.post(
        f"/api/accounts/{pending}/approve",
        json={
            "role": "crewing_officer",
            "reason": "New hire",
            "vessel_ids": [world["alpha"], world["bravo"]],
        },
        headers=world["admin"],
    )
    assert res.status_code == 200, res.text
    assert await _links(owner_db, pending) == {world["alpha"], world["bravo"]}
    [added] = await _records(owner_db, "responsible_officer_added", world["alpha"])
    assert added["reason"] == "New hire"


async def test_approving_with_no_vessels_leaves_the_pool_only(client, world, make_account, owner_db):
    pending = await make_account(status="pending")
    res = await client.post(
        f"/api/accounts/{pending}/approve",
        json={"role": "crewing_officer", "reason": "New hire", "vessel_ids": []},
        headers=world["admin"],
    )
    assert res.status_code == 200
    assert await _links(owner_db, pending) == set()


async def test_only_a_crewing_officer_is_approved_with_vessels(client, world, make_account, owner_db):
    pending = await make_account(status="pending")
    res = await client.post(
        f"/api/accounts/{pending}/approve",
        json={"role": "manager", "reason": "Boss", "vessel_ids": [world["alpha"]]},
        headers=world["admin"],
    )
    assert res.status_code == 422
    status = await owner_db.fetchval("SELECT status FROM public.users WHERE id = $1", pending)
    assert status == "pending"


async def test_the_vessels_filter_is_open_to_officers(client, world, make_account):
    officer = auth_header(await make_account(role="crewing_officer"))
    res = await client.get(
        "/api/vessels", params={"without_active_officer": "true"}, headers=officer
    )
    assert res.status_code == 200
