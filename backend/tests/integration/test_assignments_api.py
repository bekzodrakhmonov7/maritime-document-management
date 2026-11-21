"""Assignments and Scope through the HTTP API (FR-03, FR-04, FR-06; T3, T5, T7).

Crewing staff plan, edit and cancel Assignments. Officers act only on vessels
they are a Responsible Officer for, and see only their vessels' crew plus the
Unassigned Pool. Out-of-Scope records answer 404 and are recorded.
"""

from datetime import date, timedelta

import pytest

from app.domain import today_in
from tests.conftest import auth_header

TODAY = today_in("UTC")


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


@pytest.fixture
async def world(crew, make_account):
    """Two vessels, each with its own officer; a seafarer in the Pool."""
    master = await crew.position("Master")
    cook = await crew.position("Cook")
    alpha = await crew.vessel("Alpha")
    bravo = await crew.vessel("Bravo")
    officer_a = await make_account(role="crewing_officer")
    officer_b = await make_account(role="crewing_officer")
    manager = await make_account(role="manager")
    await crew.link(officer_a, alpha)
    await crew.link(officer_b, bravo)
    return {
        "ids": {"officer_a": officer_a, "officer_b": officer_b, "manager": manager},
        "master": master,
        "cook": cook,
        "alpha": alpha,
        "bravo": bravo,
        "anna": await crew.seafarer(master, "Anna"),
        "admin": auth_header(await make_account(role="administrator")),
        "manager": auth_header(manager),
        "officer_a": auth_header(officer_a),
        "officer_b": auth_header(officer_b),
    }


def _body(w, vessel: str = "alpha", start: int = 10, end: int = 40, **fields) -> dict:
    return {
        "seafarer_id": w["anna"],
        "vessel_id": w[vessel],
        "position_id": w["master"],
        "start_date": day(start),
        "end_date": day(end),
        **fields,
    }


def _edit_body(body: dict) -> dict:
    return {k: v for k, v in body.items() if k != "seafarer_id"}


async def _plan(client, headers, body) -> dict:
    res = await client.post("/api/assignments", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


async def _records(owner_db, action: str, target_id) -> list[dict]:
    rows = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE action = $1 AND target_id = $2 ORDER BY id",
        action, str(target_id),
    )
    return [dict(r) for r in rows]


async def _visible(client, headers) -> set[int]:
    res = await client.get("/api/seafarers", params={"show_inactive": "true"}, headers=headers)
    assert res.status_code == 200
    return {s["id"] for s in res.json()}


# --- Planning, editing, cancelling -----------------------------------------------------


async def test_an_officer_plans_an_assignment_on_their_vessel(client, world, owner_db):
    planned = await _plan(client, world["officer_a"], _body(world))
    assert planned["vessel_name"] == "Alpha"
    assert planned["position_name"] == "Master"
    assert planned["state"] == "upcoming"
    assert planned["position_differs"] is False

    [record] = await _records(owner_db, "assignment_created", planned["id"])
    assert record["target_type"] == "assignment"
    assert record["seafarer_id"] == world["anna"]
    assert f'"vessel_id": {world["alpha"]}' in record["after"]


async def test_the_state_and_current_vessel_come_from_the_dates(client, world):
    await _plan(client, world["admin"], _body(world, start=-5, end=5))
    planned = await _plan(client, world["admin"], _body(world, "bravo", start=6, end=30))
    assert planned["state"] == "upcoming"

    res = await client.get(f"/api/seafarers/{world['anna']}/assignments", headers=world["admin"])
    assert res.status_code == 200
    assert [(a["vessel_name"], a["state"]) for a in res.json()] == [
        ("Bravo", "upcoming"),
        ("Alpha", "under_way"),
    ]
    seafarer = (await client.get(f"/api/seafarers/{world['anna']}", headers=world["admin"])).json()
    assert (seafarer["current_vessel_id"], seafarer["current_vessel_name"]) == (
        world["alpha"],
        "Alpha",
    )


async def test_a_seafarer_with_no_assignment_under_way_is_ashore(client, world):
    await _plan(client, world["admin"], _body(world, start=1, end=30))
    seafarer = (await client.get(f"/api/seafarers/{world['anna']}", headers=world["admin"])).json()
    assert seafarer["current_vessel_id"] is None
    assert seafarer["current_vessel_name"] is None


async def test_a_position_other_than_the_held_one_gets_a_notice(client, world, owner_db):
    planned = await _plan(client, world["admin"], _body(world, position_id=world["cook"]))
    assert planned["position_differs"] is True
    held = await owner_db.fetchval("SELECT position_id FROM public.seafarer WHERE id = $1", world["anna"])
    assert held == world["master"]


async def test_an_overlapping_assignment_is_refused(client, world):
    await _plan(client, world["admin"], _body(world, start=10, end=40))
    res = await client.post(
        "/api/assignments", json=_body(world, "bravo", start=40, end=60), headers=world["admin"]
    )
    assert res.status_code == 409
    assert "overlap" in res.json()["detail"]
    await _plan(client, world["admin"], _body(world, "bravo", start=41, end=60))


async def test_the_end_cannot_be_before_the_start(client, world):
    res = await client.post(
        "/api/assignments", json=_body(world, start=10, end=9), headers=world["admin"]
    )
    assert res.status_code == 422


async def test_only_an_active_vessel_and_a_current_position_can_be_picked(client, world, crew, owner_db):
    retired = await crew.position("Purser", retired=True)
    laid_up = await crew.vessel("Laid Up", active=False)
    for body in (
        _body(world, position_id=retired),
        {**_body(world), "vessel_id": laid_up},
        _body(world, position_id=999999),
    ):
        res = await client.post("/api/assignments", json=body, headers=world["admin"])
        assert res.status_code == 422, body


async def test_an_edit_may_keep_a_vessel_deactivated_since(client, world, owner_db):
    planned = await _plan(client, world["admin"], _body(world))
    await owner_db.execute("UPDATE public.vessel SET active = false WHERE id = $1", world["alpha"])
    res = await client.put(
        f"/api/assignments/{planned['id']}",
        json=_edit_body(_body(world, end=50)),
        headers=world["admin"],
    )
    assert res.status_code == 200, res.text


async def test_an_inactive_seafarer_gets_no_new_assignment(client, world, owner_db):
    await owner_db.execute(
        "UPDATE public.seafarer SET inactive_since = now(), inactive_reason = 'Left' WHERE id = $1",
        world["anna"],
    )
    res = await client.post("/api/assignments", json=_body(world), headers=world["admin"])
    assert res.status_code == 409


async def test_an_edit_records_only_the_changed_fields(client, world, owner_db):
    planned = await _plan(client, world["officer_a"], _body(world))
    res = await client.put(
        f"/api/assignments/{planned['id']}",
        json=_edit_body(_body(world, end=45)),
        headers=world["officer_a"],
    )
    assert res.status_code == 200
    assert res.json()["end_date"] == day(45)

    [record] = await _records(owner_db, "assignment_edited", planned["id"])
    assert record["seafarer_id"] == world["anna"]
    assert record["before"] == f'{{"end_date": "{day(40)}"}}'
    assert record["after"] == f'{{"end_date": "{day(45)}"}}'

    same = await client.put(
        f"/api/assignments/{planned['id']}",
        json=_edit_body(_body(world, end=45)),
        headers=world["officer_a"],
    )
    assert same.status_code == 200
    assert len(await _records(owner_db, "assignment_edited", planned["id"])) == 1


async def test_the_seafarer_cannot_be_changed(client, world, crew):
    planned = await _plan(client, world["admin"], _body(world))
    other = await crew.seafarer(world["master"], "Ivan")
    res = await client.put(
        f"/api/assignments/{planned['id']}",
        json={**_edit_body(_body(world)), "seafarer_id": other},
        headers=world["admin"],
    )
    assert res.status_code == 422


async def test_an_edit_overlapping_another_assignment_is_refused(client, world):
    await _plan(client, world["admin"], _body(world, start=10, end=20))
    later = await _plan(client, world["admin"], _body(world, start=30, end=40))
    res = await client.put(
        f"/api/assignments/{later['id']}",
        json=_edit_body(_body(world, start=15, end=40)),
        headers=world["admin"],
    )
    assert res.status_code == 409


async def test_cancelling_needs_a_reason_and_keeps_the_assignment(client, world, owner_db):
    planned = await _plan(client, world["officer_a"], _body(world))
    path = f"/api/assignments/{planned['id']}/cancel"
    assert (await client.post(path, json={"reason": "  "}, headers=world["officer_a"])).status_code == 422

    res = await client.post(path, json={"reason": " Plans changed "}, headers=world["officer_a"])
    assert res.status_code == 200
    assert res.json()["state"] == "cancelled"
    assert res.json()["cancel_reason"] == "Plans changed"
    assert (await client.post(path, json={"reason": "Again"}, headers=world["officer_a"])).status_code == 409

    [record] = await _records(owner_db, "assignment_cancelled", planned["id"])
    assert record["reason"] == "Plans changed"
    assert record["seafarer_id"] == world["anna"]

    # A cancelled Assignment blocks nothing and can't be edited.
    await _plan(client, world["officer_a"], _body(world))
    res = await client.put(
        f"/api/assignments/{planned['id']}", json=_edit_body(_body(world)), headers=world["admin"]
    )
    assert res.status_code == 409


async def test_a_finished_assignment_is_read_only(client, world):
    finished = await _plan(client, world["admin"], _body(world, start=-30, end=-1))
    assert finished["state"] == "finished"
    edit = await client.put(
        f"/api/assignments/{finished['id']}",
        json=_edit_body(_body(world, start=-30, end=-2)),
        headers=world["admin"],
    )
    assert edit.status_code == 409
    cancel = await client.post(
        f"/api/assignments/{finished['id']}/cancel", json={"reason": "x"}, headers=world["admin"]
    )
    assert cancel.status_code == 409


async def test_set_inactive_is_refused_while_an_assignment_is_upcoming_or_under_way(client, world):
    planned = await _plan(client, world["admin"], _body(world, start=-1, end=1))
    path = f"/api/seafarers/{world['anna']}/set-inactive"
    res = await client.post(path, json={"reason": "Left"}, headers=world["admin"])
    assert res.status_code == 409
    assert "Assignment" in res.json()["detail"]

    await client.post(
        f"/api/assignments/{planned['id']}/cancel", json={"reason": "Off"}, headers=world["admin"]
    )
    await _plan(client, world["admin"], _body(world, start=-10, end=-2))
    assert (await client.post(path, json={"reason": "Left"}, headers=world["admin"])).status_code == 200


# --- Officer rights ------------------------------------------------------------------------


async def _refused(owner_db, actor_id, method: str, path: str, reason: str) -> int:
    return await owner_db.fetchval(
        """
        SELECT count(*) FROM public.audit_log
         WHERE action = 'access_refused' AND actor_id = $1 AND target_id = $2 AND reason = $3
        """,
        actor_id, f"{method} {path}", reason,
    )


async def test_an_officer_plans_only_onto_their_own_vessels(client, world, owner_db):
    res = await client.post("/api/assignments", json=_body(world, "bravo"), headers=world["officer_a"])
    assert res.status_code == 403
    assert await _refused(
        owner_db, world["ids"]["officer_a"], "POST", "/api/assignments", "not_responsible"
    ) == 1
    assert await owner_db.fetchval("SELECT count(*) FROM public.assignment") == 0


async def test_editing_needs_both_the_old_and_the_new_vessel(client, world, make_account, crew):
    planned = await _plan(client, world["officer_a"], _body(world))
    path = f"/api/assignments/{planned['id']}"
    move = _edit_body(_body(world, "bravo"))

    assert (await client.put(path, json=move, headers=world["officer_a"])).status_code == 403
    # The seafarer is on Alpha, outside Bravo's officer's Scope.
    assert (await client.put(path, json=move, headers=world["officer_b"])).status_code == 404

    both = await make_account(role="crewing_officer")
    await crew.link(both, world["alpha"], world["bravo"])
    res = await client.put(path, json=move, headers=auth_header(both))
    assert res.status_code == 200
    assert res.json()["vessel_name"] == "Bravo"


async def test_cancelling_needs_the_assignments_vessel(client, world):
    planned = await _plan(client, world["officer_a"], _body(world))
    # Bravo's officer still sees the seafarer once an administrator books
    # their next Assignment onto Bravo.
    await _plan(client, world["admin"], _body(world, "bravo", start=50, end=60))
    path = f"/api/assignments/{planned['id']}/cancel"
    res = await client.post(path, json={"reason": "x"}, headers=world["officer_b"])
    assert res.status_code == 403
    # Cancelling takes the seafarer out of Alpha's officer's Scope; the answer
    # to the cancel itself still comes back.
    res = await client.post(path, json={"reason": "x"}, headers=world["officer_a"])
    assert res.status_code == 200
    assert res.json()["state"] == "cancelled"
    assert world["anna"] not in await _visible(client, world["officer_a"])


async def test_administrators_are_unrestricted(client, world):
    planned = await _plan(client, world["admin"], _body(world, "alpha"))
    res = await client.put(
        f"/api/assignments/{planned['id']}", json=_edit_body(_body(world, "bravo")), headers=world["admin"]
    )
    assert res.status_code == 200


# --- Scope ---------------------------------------------------------------------------------


async def test_booking_onto_vessel_b_removes_the_seafarer_from_as_officer(client, world):
    assert world["anna"] in await _visible(client, world["officer_a"])
    assert world["anna"] in await _visible(client, world["officer_b"])

    await _plan(client, world["officer_b"], _body(world, "bravo"))

    assert world["anna"] not in await _visible(client, world["officer_a"])
    assert world["anna"] in await _visible(client, world["officer_b"])


async def test_a_finished_or_cancelled_assignment_returns_the_seafarer_to_the_pool(client, world):
    await _plan(client, world["admin"], _body(world, "bravo", start=-20, end=-1))
    planned = await _plan(client, world["admin"], _body(world, "bravo"))
    assert world["anna"] not in await _visible(client, world["officer_a"])

    await client.post(
        f"/api/assignments/{planned['id']}/cancel", json={"reason": "x"}, headers=world["admin"]
    )
    assert world["anna"] in await _visible(client, world["officer_a"])


async def test_a_deactivated_officer_sees_nobody(client, world, make_account, crew, owner_db):
    officer = await make_account(role="crewing_officer")
    await crew.link(officer, world["alpha"])
    await owner_db.execute("UPDATE public.users SET status = 'deactivated' WHERE id = $1", officer)
    res = await client.get("/api/seafarers", headers=auth_header(officer))
    assert res.status_code == 403


SEAFARER_ENDPOINTS = [
    ("GET", "/api/seafarers/{sid}", None),
    ("PUT", "/api/seafarers/{sid}", "seafarer"),
    ("POST", "/api/seafarers/{sid}/set-inactive", {"reason": "x"}),
    ("POST", "/api/seafarers/{sid}/reactivate", None),
    ("GET", "/api/seafarers/{sid}/assignments", None),
    ("GET", "/api/assignments/{aid}", None),
    ("PUT", "/api/assignments/{aid}", "assignment"),
    ("POST", "/api/assignments/{aid}/cancel", {"reason": "x"}),
    ("POST", "/api/assignments", "new_assignment"),
]


@pytest.mark.parametrize("method, path, body", SEAFARER_ENDPOINTS)
async def test_an_out_of_scope_record_is_404_and_recorded(client, world, owner_db, method, path, body):
    planned = await _plan(client, world["officer_b"], _body(world, "bravo"))
    bodies = {
        "seafarer": {"first_name": "X", "last_name": "Y", "position_id": world["master"]},
        "assignment": _edit_body(_body(world)),
        "new_assignment": _body(world, start=100, end=120),
    }
    res = await client.request(
        method,
        path.format(sid=world["anna"], aid=planned["id"]),
        json=bodies.get(body, body) if isinstance(body, str) else body,
        headers=world["officer_a"],
    )
    assert res.status_code == 404
    assert res.json() == {"detail": "Not found"}

    refused = await owner_db.fetch(
        """
        SELECT * FROM public.audit_log
         WHERE action = 'access_refused' AND reason = 'out_of_scope' AND seafarer_id = $1
        """,
        world["anna"],
    )
    assert len(refused) == 1
    assert refused[0]["outcome"] == "refused"


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/api/seafarers/999999"),
        ("GET", "/api/seafarers/999999/assignments"),
        ("GET", "/api/assignments/999999"),
        ("POST", "/api/assignments/999999/cancel"),
    ],
)
async def test_a_missing_record_is_404_and_not_recorded(client, world, owner_db, method, path):
    before = await owner_db.fetchval("SELECT count(*) FROM public.audit_log")
    res = await client.request(method, path, json={"reason": "x"}, headers=world["admin"])
    assert res.status_code == 404
    assert await owner_db.fetchval("SELECT count(*) FROM public.audit_log") == before


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/api/seafarers/{sid}/assignments"),
        ("GET", "/api/assignments/{aid}"),
        ("POST", "/api/assignments"),
        ("PUT", "/api/assignments/{aid}"),
        ("POST", "/api/assignments/{aid}/cancel"),
        ("GET", "/api/vessels/{vid}/crew"),
    ],
)
async def test_a_manager_gets_403_and_is_recorded(client, world, owner_db, method, path):
    planned = await _plan(client, world["admin"], _body(world))
    target = path.format(sid=world["anna"], aid=planned["id"], vid=world["alpha"])
    res = await client.request(
        method, target, json={**_body(world), "reason": "x"}, headers=world["manager"]
    )
    assert res.status_code == 403
    assert await _refused(owner_db, world["ids"]["manager"], method, target, "wrong_role") == 1
    row = await owner_db.fetchrow("SELECT * FROM public.assignment WHERE id = $1", planned["id"])
    assert row["cancelled_at"] is None
    assert await owner_db.fetchval("SELECT count(*) FROM public.assignment") == 1


# --- The vessel's crew --------------------------------------------------------------------


async def test_the_vessel_crew_lists_under_way_and_upcoming(client, world, crew):
    ivan = await crew.seafarer(world["master"], "Ivan")
    olga = await crew.seafarer(world["master"], "Olga")
    await _plan(client, world["admin"], _body(world, start=-3, end=3))
    await _plan(client, world["admin"], {**_body(world, start=5, end=9), "seafarer_id": ivan})
    await _plan(client, world["admin"], {**_body(world, start=-9, end=-1), "seafarer_id": olga})
    cancelled = await _plan(client, world["admin"], {**_body(world, start=1, end=2), "seafarer_id": olga})
    await client.post(
        f"/api/assignments/{cancelled['id']}/cancel", json={"reason": "x"}, headers=world["admin"]
    )

    res = await client.get(f"/api/vessels/{world['alpha']}/crew", headers=world["officer_a"])
    assert res.status_code == 200
    assert [(a["seafarer_first_name"], a["state"]) for a in res.json()] == [
        ("Anna", "under_way"),
        ("Ivan", "upcoming"),
    ]
    res = await client.get(f"/api/vessels/{world['alpha']}/crew", headers=world["admin"])
    assert [a["seafarer_first_name"] for a in res.json()] == ["Anna", "Ivan"]


async def test_another_vessels_crew_is_404_and_recorded(client, world, owner_db):
    await _plan(client, world["admin"], _body(world, start=-3, end=3))
    res = await client.get(f"/api/vessels/{world['alpha']}/crew", headers=world["officer_b"])
    assert res.status_code == 404
    assert res.json() == {"detail": "Not found"}
    refused = await owner_db.fetch(
        """
        SELECT * FROM public.audit_log
         WHERE action = 'access_refused' AND reason = 'out_of_scope'
           AND target_type = 'vessel' AND target_id = $1 AND actor_id = $2
        """,
        str(world["alpha"]), world["ids"]["officer_b"],
    )
    assert len(refused) == 1
    assert refused[0]["outcome"] == "refused"


async def test_an_empty_vessel_in_scope_has_an_empty_crew(client, world, owner_db):
    officer_b = world["ids"]["officer_b"]
    before = await owner_db.fetchval(
        "SELECT count(*) FROM public.audit_log WHERE actor_id = $1", officer_b
    )
    res = await client.get(f"/api/vessels/{world['bravo']}/crew", headers=world["officer_b"])
    assert res.status_code == 200
    assert res.json() == []
    assert await owner_db.fetchval(
        "SELECT count(*) FROM public.audit_log WHERE actor_id = $1", officer_b
    ) == before


async def test_an_unknown_vessel_has_no_crew(client, world):
    res = await client.get("/api/vessels/999999/crew", headers=world["admin"])
    assert res.status_code == 404


async def test_the_audit_dates_round_trip(client, world, owner_db):
    """Dates in the records are ISO strings, so searches can compare them."""
    planned = await _plan(client, world["admin"], _body(world))
    [record] = await _records(owner_db, "assignment_created", planned["id"])
    assert f'"start_date": "{day(10)}"' in record["after"]
    assert date.fromisoformat(planned["start_date"]) == TODAY + timedelta(days=10)
