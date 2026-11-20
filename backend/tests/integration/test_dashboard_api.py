"""The dashboard and the managers' fleet totals through the HTTP API (FR-20; T5, T10).

The app runs as app_backend against the real database. Both are plain reads:
no Audit Record, except refused access.
"""

import pytest

from tests.conftest import auth_header
from tests.integration.test_documents_api import _uploaded, day
from tests.integration.test_reviews_api import _reviewed


@pytest.fixture
async def world(crew, make_account, documents_cleanup, storage, settings_reset, owner_db):
    master = await crew.position("Master")
    cook = await crew.position("Cook")
    alpha = await crew.vessel("Alpha")
    bravo = await crew.vessel("Bravo")
    officer_a = await make_account(role="crewing_officer")
    officer_a2 = await make_account(role="crewing_officer")
    manager = await make_account(role="manager")
    await crew.link(officer_a, alpha)
    await crew.link(officer_a2, alpha)

    async def doc_type(name: str) -> int:
        return await owner_db.fetchval(
            "INSERT INTO public.document_type (name, expires) VALUES ($1, true) RETURNING id", name
        )

    passport, medical = await doc_type("Passport"), await doc_type("Medical")
    for position in (master, cook):
        for type_id in (passport, medical):
            await owner_db.execute(
                "INSERT INTO public.position_requirement (position_id, document_type_id) VALUES ($1, $2)",
                position, type_id,
            )
    anna = await crew.seafarer(master, "Anna")    # On board Alpha
    boris = await crew.seafarer(cook, "Boris")    # On board Bravo: outside officer A's Scope
    clara = await crew.seafarer(master, "Clara")  # Unassigned Pool
    w = {
        "master": master, "cook": cook, "alpha": alpha, "bravo": bravo,
        "passport": passport, "medical": medical,
        "anna": anna, "boris": boris, "clara": clara,
        "ids": {"manager": manager},
        "admin": auth_header(await make_account(role="administrator")),
        "manager": auth_header(manager),
        "officer_a": auth_header(officer_a),
        "officer_a2": auth_header(officer_a2),
    }
    await _assign(owner_db, w, anna, alpha, master, start=-10, end=100)
    await _assign(owner_db, w, boris, bravo, cook, start=-10, end=100)
    return w


async def _assign(owner_db, w, seafarer, vessel, position, start: int, end: int) -> int:
    return await owner_db.fetchval(
        """
        INSERT INTO public.assignment (seafarer_id, vessel_id, position_id, start_date, end_date)
        VALUES ($1, $2, $3, $4::text::date, $5::text::date) RETURNING id
        """,
        seafarer, vessel, position, day(start), day(end),
    )


async def _dashboard(client, headers, **params):
    res = await client.get("/api/dashboard", params=params, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _names(board, queue) -> list[str]:
    return [g["seafarer"]["first_name"] for g in board["queues"][queue]]


async def test_administrators_see_the_whole_fleet(client, world):
    board = await _dashboard(client, world["admin"])
    assert _names(board, "missing") == ["Anna", "Boris", "Clara"]
    assert board["counts"]["missing"] == 6
    [anna] = [g for g in board["queues"]["missing"] if g["seafarer"]["first_name"] == "Anna"]
    assert anna["seafarer"]["current_vessel_name"] == "Alpha"
    assert [e["document_type_name"] for e in anna["entries"]] == ["Medical", "Passport"]
    assert {e["action"] for e in anna["entries"]} == {"upload"}


async def test_an_officers_counts_are_limited_to_their_scope(client, world):
    await _uploaded(client, world["admin"], world["boris"], world["passport"],
                    issue_date=day(-800), expiry_date=day(-1))
    await _uploaded(client, world["admin"], world["anna"], world["passport"],
                    issue_date=day(-800), expiry_date=day(-1))
    board = await _dashboard(client, world["officer_a"])
    # Anna (Alpha) and Clara (the Pool); Boris is on Bravo.
    assert _names(board, "missing") == ["Anna", "Clara"]
    assert board["counts"]["missing"] == 3
    assert _names(board, "expired") == ["Anna"]
    assert board["counts"]["expired"] == 1
    assert board["counts"]["waiting_for_review"] == 1


async def test_waiting_for_review_overlaps_the_expiry_queues(client, world):
    doc = await _uploaded(client, world["officer_a"], world["anna"], world["passport"],
                          issue_date=day(-800), expiry_date=day(-1))
    board = await _dashboard(client, world["admin"])
    assert board["counts"]["expired"] == 1
    assert board["counts"]["waiting_for_review"] == 1
    [waiting] = board["queues"]["waiting_for_review"][0]["entries"]
    assert waiting["document_id"] == doc["id"]
    assert waiting["action"] == "review"

    await _reviewed(client, world["officer_a2"], doc["versions"][0]["id"])
    board = await _dashboard(client, world["admin"])
    assert board["counts"] == {**board["counts"], "expired": 1, "waiting_for_review": 0}


async def test_counts_follow_the_filters(client, world):
    await _uploaded(client, world["admin"], world["clara"], world["passport"])
    assert (await _dashboard(client, world["admin"], name="clara"))["counts"]["missing"] == 1
    board = await _dashboard(client, world["admin"], vessel_id=[world["alpha"], world["bravo"]])
    assert _names(board, "missing") == ["Anna", "Boris"]
    board = await _dashboard(client, world["admin"], ashore="true")
    assert _names(board, "missing") == ["Clara"]
    assert board["counts"]["in_order"] == 1
    board = await _dashboard(client, world["admin"], position_id=world["cook"])
    assert _names(board, "missing") == ["Boris"]
    board = await _dashboard(client, world["admin"], document_type_id=world["medical"])
    assert board["counts"]["missing"] == 3
    assert board["counts"]["in_order"] == 0


async def test_expiry_not_stated_has_its_own_queue_and_totals_column(client, world):
    await _uploaded(client, world["admin"], world["anna"], world["passport"],
                    expiry_date=None, expiry_not_stated="true")
    board = await _dashboard(client, world["admin"])
    assert board["counts"]["expiry_not_stated"] == 1
    assert board["counts"]["waiting_for_review"] == 1
    assert board["counts"]["in_order"] == 0
    [entry] = board["queues"]["expiry_not_stated"][0]["entries"]
    assert entry["action"] == "open"

    res = await client.get("/api/dashboard/totals", headers=world["manager"])
    assert res.status_code == 200
    assert res.json()["totals"]["expiry_not_stated"] == 1
    assert res.json()["totals"]["no_expiry_date"] == 0


async def test_inactive_seafarers_only_with_show_inactive(client, world, owner_db):
    await owner_db.execute(
        "UPDATE public.seafarer SET inactive_since = now(), inactive_reason = 'Left' WHERE id = $1",
        world["clara"],
    )
    assert "Clara" not in _names(await _dashboard(client, world["admin"]), "missing")
    board = await _dashboard(client, world["admin"], show_inactive="true")
    assert "Clara" in _names(board, "missing")


async def test_starting_soon_lists_upcoming_assignments_within_the_horizon(client, world, owner_db):
    await owner_db.execute("UPDATE public.settings SET planning_horizon_days = 30")
    soon = await _assign(owner_db, world, world["clara"], world["alpha"], world["master"], 30, 60)
    await _assign(owner_db, world, world["clara"], world["alpha"], world["master"], 61, 90)
    # A cancelled one within the horizon (cancelled rows may overlap).
    await owner_db.execute(
        """
        INSERT INTO public.assignment (seafarer_id, vessel_id, position_id, start_date, end_date,
                                       cancelled_at, cancel_reason)
        VALUES ($1, $2, $3, $4::text::date, $5::text::date, now(), 'Plans changed')
        """,
        world["clara"], world["bravo"], world["master"], day(5), day(20),
    )
    board = await _dashboard(client, world["officer_a"])
    [entry] = board["queues"]["starting_soon"]
    assert entry["assignment_id"] == soon
    assert entry["vessel_name"] == "Alpha"
    assert entry["counters"] == {
        "before_joining": 2, "renewable_at_sea": 0, "expiry_not_stated": 0, "not_reviewed": 0
    }
    assert board["counts"]["starting_soon"] == 1


async def test_reading_the_dashboard_writes_no_record(client, world, owner_db):
    before = await owner_db.fetchval("SELECT count(*) FROM public.audit_log")
    await _dashboard(client, world["admin"])
    await client.get("/api/dashboard/totals", headers=world["manager"])
    assert await owner_db.fetchval("SELECT count(*) FROM public.audit_log") == before


async def test_a_manager_calling_the_dashboard_gets_403_and_is_recorded(client, world, owner_db):
    res = await client.get("/api/dashboard", headers=world["manager"])
    assert res.status_code == 403
    refused = await owner_db.fetch(
        """
        SELECT * FROM public.audit_log
         WHERE action = 'access_refused' AND actor_id = $1 AND reason = 'wrong_role'
           AND target_id = 'GET /api/dashboard'
        """,
        world["ids"]["manager"],
    )
    assert len(refused) == 1


# --- Fleet totals ----------------------------------------------------------------------


async def test_the_manager_response_contains_no_names(client, world):
    await _uploaded(client, world["admin"], world["anna"], world["passport"],
                    issue_date=day(-800), expiry_date=day(-1))
    res = await client.get("/api/dashboard/totals", headers=world["manager"])
    assert res.status_code == 200
    body = res.json()
    assert body["totals"] == {
        "missing": 5, "expired": 1, "expiring_soon": 0, "unexpired": 0,
        "expiry_not_stated": 0, "no_expiry_date": 0,
    }
    assert body["breakdown"] == "vessel"
    assert [r["name"] for r in body["rows"]] == ["Alpha", "Bravo", "Ashore / Unassigned"]
    text = res.text
    for name in ("Anna", "Boris", "Clara", "Petrova"):
        assert name not in text
    assert "waiting_for_review" not in text and "starting_soon" not in text


async def test_the_breakdown_switches(client, world):
    res = await client.get(
        "/api/dashboard/totals", params={"breakdown": "document_type"}, headers=world["admin"]
    )
    assert res.status_code == 200
    assert [(r["name"], r["counts"]["missing"]) for r in res.json()["rows"]] == [
        ("Medical", 3), ("Passport", 3),
    ]
    res = await client.get(
        "/api/dashboard/totals", params={"breakdown": "position"}, headers=world["admin"]
    )
    assert [(r["name"], r["counts"]["missing"]) for r in res.json()["rows"]] == [
        ("Cook", 2), ("Master", 4),
    ]
    res = await client.get(
        "/api/dashboard/totals", params={"breakdown": "flag"}, headers=world["admin"]
    )
    assert res.status_code == 422


async def test_an_officer_gets_403_for_the_totals(client, world):
    res = await client.get("/api/dashboard/totals", headers=world["officer_a"])
    assert res.status_code == 403
