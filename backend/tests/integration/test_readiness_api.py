"""Missing documents on the seafarer record and the readiness view through the
HTTP API (FR-17, FR-18, FR-19; T3, T4, T5).

The app runs as app_backend against the real database; the private bucket is
the in-memory stand-in from conftest. Both are plain reads: no Audit Record,
except refused access.
"""

import pytest

from tests.conftest import auth_header
from tests.integration.test_documents_api import _uploaded, day
from tests.integration.test_reviews_api import _reviewed


@pytest.fixture
async def world(crew, make_account, documents_cleanup, storage, owner_db):
    master = await crew.position("Master")
    chief_officer = await crew.position("Chief Officer")
    alpha = await crew.vessel("Alpha")
    bravo = await crew.vessel("Bravo")
    officer_a = await make_account(role="crewing_officer")
    officer_a2 = await make_account(role="crewing_officer")
    officer_b = await make_account(role="crewing_officer")
    manager = await make_account(role="manager")
    await crew.link(officer_a, alpha)
    await crew.link(officer_a2, alpha)
    await crew.link(officer_b, bravo)

    async def doc_type(name: str, renewable_at_sea: bool = False) -> int:
        return await owner_db.fetchval(
            """
            INSERT INTO public.document_type (name, expires, renewable_at_sea)
            VALUES ($1, true, $2) RETURNING id
            """,
            name, renewable_at_sea,
        )

    types = {
        "passport": await doc_type("Passport"),
        "medical": await doc_type("Medical", renewable_at_sea=True),
        "coc": await doc_type("CoC"),
        "visa": await doc_type("Visa"),
    }
    for type_id in types.values():
        for position in (master, chief_officer):
            await owner_db.execute(
                "INSERT INTO public.position_requirement (position_id, document_type_id) VALUES ($1, $2)",
                position, type_id,
            )
    # Alpha's Chief Officers don't need the visa.
    await owner_db.execute(
        """
        INSERT INTO public.requirement_exception (vessel_id, position_id, document_type_id, effect, reason)
        VALUES ($1, $2, $3, 'remove', 'Not for this trade')
        """,
        alpha, chief_officer, types["visa"],
    )
    return {
        **types,
        "ids": {"officer_a": officer_a, "officer_b": officer_b, "manager": manager},
        "master": master,
        "chief_officer": chief_officer,
        "alpha": alpha,
        "bravo": bravo,
        "anna": await crew.seafarer(master, "Anna"),
        "admin": auth_header(await make_account(role="administrator")),
        "manager": auth_header(manager),
        "officer_a": auth_header(officer_a),
        "officer_a2": auth_header(officer_a2),
        "officer_b": auth_header(officer_b),
    }


async def _plan(client, w, start: int, end: int, vessel="alpha", position="master") -> dict:
    res = await client.post(
        "/api/assignments",
        json={
            "seafarer_id": w["anna"],
            "vessel_id": w[vessel],
            "position_id": w[position],
            "start_date": day(start),
            "end_date": day(end),
        },
        headers=w["admin"],
    )
    assert res.status_code == 201, res.text
    return res.json()


async def _planned_as_owner(owner_db, w, start: int, end: int) -> int:
    """An Assignment in the past can't be planned through the API."""
    return await owner_db.fetchval(
        """
        INSERT INTO public.assignment (seafarer_id, vessel_id, position_id, start_date, end_date)
        VALUES ($1, $2, $3, $4::text::date, $5::text::date) RETURNING id
        """,
        w["anna"], w["alpha"], w["master"], day(start), day(end),
    )


async def _readiness(client, headers, assignment_id):
    return await client.get(f"/api/assignments/{assignment_id}/readiness", headers=headers)


def _names(view: dict, bucket: str) -> list[str]:
    return [e["name"] for e in view["buckets"][bucket]]


# --- Missing documents on the seafarer record ------------------------------------------------


async def test_the_seafarer_record_lists_its_missing_documents(client, world):
    await _uploaded(client, world["officer_a"], world["anna"], world["passport"])
    res = await client.get(f"/api/seafarers/{world['anna']}", headers=world["officer_a"])
    assert res.status_code == 200
    # Ashore: the held Position (Master) with no vessel, so no exceptions.
    assert [m["name"] for m in res.json()["missing_documents"]] == ["CoC", "Medical", "Visa"]


async def test_an_expired_document_is_not_missing(client, world):
    await _uploaded(
        client, world["officer_a"], world["anna"], world["passport"],
        issue_date=day(-800), expiry_date=day(-1),
    )
    res = await client.get(f"/api/seafarers/{world['anna']}", headers=world["admin"])
    assert "Passport" not in [m["name"] for m in res.json()["missing_documents"]]


async def test_a_document_whose_versions_are_all_rejected_is_missing(client, world):
    doc = await _uploaded(client, world["officer_a"], world["anna"], world["passport"])
    await _reviewed(client, world["officer_a2"], doc["versions"][0]["id"], "reject", "Unreadable")
    res = await client.get(f"/api/seafarers/{world['anna']}", headers=world["admin"])
    [passport] = [m for m in res.json()["missing_documents"] if m["name"] == "Passport"]
    assert passport["document_id"] == doc["id"]


async def test_under_way_the_assignments_pair_decides_missing_documents(client, world, owner_db):
    # Assigned as Chief Officer on Alpha, where the visa is removed.
    await _plan(client, world, start=0, end=30, position="chief_officer")
    res = await client.get(f"/api/seafarers/{world['anna']}", headers=world["admin"])
    assert [m["name"] for m in res.json()["missing_documents"]] == ["CoC", "Medical", "Passport"]


async def test_an_upcoming_assignment_does_not_feed_missing_documents(client, world):
    await _plan(client, world, start=5, end=30, position="chief_officer")
    res = await client.get(f"/api/seafarers/{world['anna']}", headers=world["admin"])
    assert "Visa" in [m["name"] for m in res.json()["missing_documents"]]


# --- The readiness view ------------------------------------------------------------------------


async def test_the_readiness_view_of_an_upcoming_assignment(client, world, owner_db):
    planned = await _plan(client, world, start=10, end=100, position="chief_officer")
    await _uploaded(
        client, world["officer_a"], world["anna"], world["passport"], expiry_date=day(5)
    )
    medical = await _uploaded(
        client, world["officer_a"], world["anna"], world["medical"], expiry_date=day(50)
    )
    await _reviewed(client, world["officer_a2"], medical["versions"][0]["id"])

    res = await _readiness(client, world["officer_a"], planned["id"])
    assert res.status_code == 200, res.text
    view = res.json()
    header = view["assignment"]
    assert header["seafarer_first_name"] == "Anna"
    assert header["vessel_name"] == "Alpha" and header["vessel_flag"] == "MT"
    assert header["position_name"] == "Chief Officer"
    assert header["start_date"] == day(10) and header["end_date"] == day(100)
    assert view["state"] == "upcoming"
    assert view["before_joining_label"] == "Before joining"
    assert view["position_notice"] == (
        "Assigned as Chief Officer; holds Master. Requirements below are for Chief Officer."
    )
    # The visa is removed for Alpha's Chief Officers.
    assert _names(view, "before_joining") == ["CoC", "Passport"]
    assert _names(view, "renewable_at_sea") == ["Medical"]
    assert _names(view, "not_reviewed") == ["Passport"]
    assert _names(view, "covers_all") == []
    [passport] = [e for e in view["buckets"]["before_joining"] if e["name"] == "Passport"]
    assert passport["coverage"] == "runs_out_before_start"
    assert passport["suggestion"] == f"Renew before joining (runs out {day(5)})"
    assert view["counters"] == {
        "before_joining": 2, "renewable_at_sea": 1, "expiry_not_stated": 0, "not_reviewed": 1
    }


async def test_a_document_with_no_stated_expiry_is_checked_by_hand(client, world):
    planned = await _plan(client, world, start=10, end=100)
    await _uploaded(
        client, world["officer_a"], world["anna"], world["passport"],
        issue_date=day(-400), expiry_date=None, expiry_not_stated="true",
    )
    view = (await _readiness(client, world["officer_a"], planned["id"])).json()
    assert _names(view, "expiry_not_stated") == ["Passport"]
    assert "Passport" in _names(view, "not_reviewed")
    assert _names(view, "covers_all") == []
    [passport] = view["buckets"]["expiry_not_stated"]
    assert passport["coverage"] == "expiry_not_stated"
    assert passport["suggestion"] == f"Issued {day(-400)}: expiry not stated, check manually"
    assert view["counters"]["expiry_not_stated"] == 1


async def test_an_under_way_assignment_gets_the_under_way_advice(client, world, owner_db):
    assignment_id = await _planned_as_owner(owner_db, world, start=-20, end=40)
    await _uploaded(
        client, world["officer_a"], world["anna"], world["medical"],
        issue_date=day(-300), expiry_date=day(-3),
    )
    view = (await _readiness(client, world["admin"], assignment_id)).json()
    assert view["state"] == "under_way"
    assert view["before_joining_label"] == "Act now"
    assert view["position_notice"] is None
    [medical] = [e for e in view["buckets"]["before_joining"] if e["name"] == "Medical"]
    assert medical["coverage"] == "runs_out_during"
    assert medical["suggestion"] == f"Expired {day(-3)} while on board, renew now"


async def test_reading_the_readiness_view_writes_no_record(client, world, owner_db):
    planned = await _plan(client, world, start=10, end=100)
    before = await owner_db.fetchval("SELECT count(*) FROM public.audit_log")
    assert (await _readiness(client, world["admin"], planned["id"])).status_code == 200
    assert await owner_db.fetchval("SELECT count(*) FROM public.audit_log") == before


async def test_a_finished_assignment_has_no_readiness_view(client, world, owner_db):
    assignment_id = await _planned_as_owner(owner_db, world, start=-30, end=-1)
    before = await owner_db.fetchval("SELECT count(*) FROM public.audit_log")
    res = await _readiness(client, world["admin"], assignment_id)
    assert res.status_code == 404
    assert await owner_db.fetchval("SELECT count(*) FROM public.audit_log") == before


async def test_a_cancelled_assignment_has_no_readiness_view(client, world):
    planned = await _plan(client, world, start=10, end=100)
    cancelled = await client.post(
        f"/api/assignments/{planned['id']}/cancel", json={"reason": "x"}, headers=world["admin"]
    )
    assert cancelled.status_code == 200
    assert (await _readiness(client, world["admin"], planned["id"])).status_code == 404


async def test_an_unknown_assignment_is_404(client, world):
    assert (await _readiness(client, world["admin"], 999999)).status_code == 404


async def test_out_of_scope_is_404_and_recorded(client, world, owner_db):
    planned = await _plan(client, world, start=10, end=100, vessel="bravo")
    res = await _readiness(client, world["officer_a"], planned["id"])
    assert res.status_code == 404
    assert res.json() == {"detail": "Not found"}
    refused = await owner_db.fetch(
        """
        SELECT * FROM public.audit_log
         WHERE action = 'access_refused' AND reason = 'out_of_scope'
           AND actor_id = $1 AND seafarer_id = $2
        """,
        world["ids"]["officer_a"], world["anna"],
    )
    assert len(refused) == 1
    assert refused[0]["target_type"] == "assignment"
    assert refused[0]["target_id"] == str(planned["id"])


async def test_a_manager_gets_403_and_is_recorded(client, world, owner_db):
    planned = await _plan(client, world, start=10, end=100)
    path = f"/api/assignments/{planned['id']}/readiness"
    res = await client.get(path, headers=world["manager"])
    assert res.status_code == 403
    refused = await owner_db.fetch(
        """
        SELECT * FROM public.audit_log
         WHERE action = 'access_refused' AND actor_id = $1 AND reason = 'wrong_role'
           AND target_id = $2
        """,
        world["ids"]["manager"], f"GET {path}",
    )
    assert len(refused) == 1


async def test_a_manager_gets_403_for_the_seafarer_record(client, world):
    res = await client.get(f"/api/seafarers/{world['anna']}", headers=world["manager"])
    assert res.status_code == 403
