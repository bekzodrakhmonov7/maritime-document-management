"""Status Reports through the HTTP API (FR-21, T12, T5, T7).

Administrators download any report, crewing officers only within Scope (404
outside, recorded), managers none (403). Every generated report, PDF or CSV,
writes one *report generated* Audit Record. Reports are as of today and hold
no document numbers or file links.
"""

import csv
import io

import pytest

from tests.integration.test_documents_api import _records, _uploaded, day
from tests.integration.test_readiness_api import _plan, _planned_as_owner, _readiness, world  # noqa: F401


async def _report(client, headers, kind: str, target_id: int, fmt: str):
    path = f"/api/{'assignments' if kind == 'assignment' else 'vessels'}/{target_id}/report"
    return await client.get(path, params={"format": fmt}, headers=headers)


def _rows(res) -> list[dict]:
    return list(csv.DictReader(io.StringIO(res.text)))


async def _second_seafarer(crew, owner_db, w, name: str, start: int, end: int, vessel="alpha") -> int:
    seafarer = await crew.seafarer(w["master"], name)
    return await owner_db.fetchval(
        """
        INSERT INTO public.assignment (seafarer_id, vessel_id, position_id, start_date, end_date)
        VALUES ($1, $2, $3, $4::text::date, $5::text::date) RETURNING id
        """,
        seafarer, w[vessel], w["master"], day(start), day(end),
    )


# --- The assignment report -------------------------------------------------------------------


async def test_the_assignment_csv_is_the_readiness_view_flattened(client, world):
    await _uploaded(
        client, world["officer_a"], world["anna"], world["passport"], document_number="SECRET-77"
    )
    planned = await _plan(client, world, start=10, end=100)

    res = await _report(client, world["officer_a"], "assignment", planned["id"], "csv")

    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("text/csv")
    assert f'filename="status-report-assignment-{planned["id"]}-' in res.headers["content-disposition"]
    rows = _rows(res)
    view = (await _readiness(client, world["officer_a"], planned["id"])).json()
    in_view = {e["name"] for b in view["buckets"].values() for e in b}
    assert sorted(r["document_type"] for r in rows) == sorted(in_view)
    assert {r["seafarer"] for r in rows} == {"Anna Petrova"}
    assert {(r["vessel"], r["state"], r["position"]) for r in rows} == {("Alpha", "upcoming", "Master")}
    assert "SECRET-77" not in res.text and "/documents/" not in res.text


async def test_the_assignment_pdf_downloads(client, world):
    planned = await _plan(client, world, start=10, end=100)
    res = await _report(client, world["admin"], "assignment", planned["id"], "pdf")
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF-")


@pytest.mark.parametrize("fmt", ["pdf", "csv"])
async def test_each_generated_report_is_audited(client, world, owner_db, fmt):
    planned = await _plan(client, world, start=10, end=100)
    res = await _report(client, world["officer_a"], "assignment", planned["id"], fmt)
    assert res.status_code == 200

    [record] = await _records(
        owner_db, "report_generated", target_type="assignment", target_id=str(planned["id"])
    )
    assert record["actor_id"] == world["ids"]["officer_a"]
    assert record["actor_role"] == "crewing_officer"
    assert record["outcome"] == "succeeded"
    assert record["seafarer_id"] == world["anna"]
    assert f'"format": "{fmt}"' in record["after"]


async def test_an_officer_outside_scope_gets_404_and_it_is_recorded(client, world, owner_db):
    planned = await _plan(client, world, start=10, end=100)
    res = await _report(client, world["officer_b"], "assignment", planned["id"], "csv")
    assert res.status_code == 404
    [refused] = await _records(
        owner_db, "access_refused", reason="out_of_scope", target_type="assignment",
        target_id=str(planned["id"]), actor_id=world["ids"]["officer_b"],
    )
    assert refused["seafarer_id"] == world["anna"]
    assert await _records(
        owner_db, "report_generated", target_type="assignment", target_id=str(planned["id"])
    ) == []


async def test_a_finished_or_cancelled_assignment_has_no_report(client, world, owner_db):
    finished = await _planned_as_owner(owner_db, world, start=-60, end=-1)
    assert (await _report(client, world["admin"], "assignment", finished, "csv")).status_code == 404
    planned = await _plan(client, world, start=10, end=100)
    await client.post(
        f"/api/assignments/{planned['id']}/cancel", json={"reason": "Plans changed"},
        headers=world["admin"],
    )
    assert (await _report(client, world["admin"], "assignment", planned["id"], "pdf")).status_code == 404


async def test_a_manager_gets_403_for_both_reports(client, world, owner_db):
    planned = await _plan(client, world, start=10, end=100)
    for kind, target in (("assignment", planned["id"]), ("vessel", world["alpha"])):
        res = await _report(client, world["manager"], kind, target, "pdf")
        assert res.status_code == 403
    refused = await _records(
        owner_db, "access_refused", reason="wrong_role", actor_id=world["ids"]["manager"]
    )
    assert len(refused) == 2


async def test_an_unknown_format_is_refused(client, world):
    planned = await _plan(client, world, start=10, end=100)
    res = await _report(client, world["admin"], "assignment", planned["id"], "xlsx")
    assert res.status_code == 422


# --- The vessel report ---------------------------------------------------------------------


async def test_the_vessel_report_covers_under_way_and_soon_starting_assignments(
    client, world, crew, owner_db
):
    under_way = await _planned_as_owner(owner_db, world, start=-5, end=30)
    soon = await _second_seafarer(crew, owner_db, world, "Boris", start=20, end=120)
    await _second_seafarer(crew, owner_db, world, "Clara", start=400, end=500)  # beyond the horizon
    await _second_seafarer(crew, owner_db, world, "Dmitri", start=-90, end=-10)  # finished
    cancelled = await _second_seafarer(crew, owner_db, world, "Elena", start=5, end=50)
    await owner_db.execute(
        "UPDATE public.assignment SET cancelled_at = now(), cancel_reason = 'x' WHERE id = $1",
        cancelled,
    )
    await _second_seafarer(crew, owner_db, world, "Fedor", start=5, end=50, vessel="bravo")

    res = await _report(client, world["officer_a"], "vessel", world["alpha"], "csv")

    assert res.status_code == 200, res.text
    rows = _rows(res)
    assert [r["seafarer"].split()[0] for r in rows[::4]] == ["Anna", "Boris"]
    assert len(rows) == 8  # four required types each
    assert {r["vessel"] for r in rows} == {"Alpha"}
    assert [r["state"] for r in rows[::4]] == ["under way", "upcoming"]
    # The vessel CSV is the assignment rows concatenated.
    anna = _rows(await _report(client, world["officer_a"], "assignment", under_way, "csv"))
    boris = _rows(await _report(client, world["officer_a"], "assignment", soon, "csv"))
    strip = lambda rs: [{k: v for k, v in r.items() if k != "generated_at"} for r in rs]  # noqa: E731
    assert strip(rows) == strip(anna + boris)


async def test_the_vessel_pdf_downloads_and_is_audited(client, world, owner_db):
    await _planned_as_owner(owner_db, world, start=-5, end=30)
    res = await _report(client, world["admin"], "vessel", world["alpha"], "pdf")
    assert res.status_code == 200, res.text
    assert res.content.startswith(b"%PDF-")
    [record] = await _records(
        owner_db, "report_generated", target_type="vessel", target_id=str(world["alpha"])
    )
    assert '"format": "pdf"' in record["after"]
    assert '"assignments": 1' in record["after"]


async def test_the_vessel_csv_is_audited_even_with_nobody_aboard(client, world, owner_db):
    res = await _report(client, world["admin"], "vessel", world["bravo"], "csv")
    assert res.status_code == 200
    assert len(_rows(res)) == 0
    [record] = await _records(
        owner_db, "report_generated", target_type="vessel", target_id=str(world["bravo"])
    )
    assert '"format": "csv"' in record["after"]


async def test_an_officer_gets_404_for_a_vessel_they_are_not_responsible_for(client, world, owner_db):
    res = await _report(client, world["officer_b"], "vessel", world["alpha"], "csv")
    assert res.status_code == 404
    assert len(await _records(
        owner_db, "access_refused", reason="out_of_scope", target_type="vessel",
        target_id=str(world["alpha"]), actor_id=world["ids"]["officer_b"],
    )) == 1
    assert await _records(
        owner_db, "report_generated", target_type="vessel", target_id=str(world["alpha"])
    ) == []


async def test_an_unknown_vessel_is_a_plain_404(client, world):
    res = await _report(client, world["admin"], "vessel", 999_999_999, "csv")
    assert res.status_code == 404


# --- Where the vessel report is offered -------------------------------------------------------


async def test_an_officer_is_told_which_vessels_they_are_responsible_for(client, world):
    res = await client.get("/api/me/vessels", headers=world["officer_a"])
    assert res.status_code == 200
    assert res.json() == [world["alpha"]]
    assert (await client.get("/api/me/vessels", headers=world["officer_b"])).json() == [world["bravo"]]
    # Administrators may report on any vessel, so they need no list.
    assert (await client.get("/api/me/vessels", headers=world["admin"])).json() == []
