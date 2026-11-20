"""The Endorsement cap through the HTTP API (FR-14, O1/T11).

An Endorsement's Effective Expiry is the earlier of its own and its
certificate's Current Version expiry; without a certificate it counts as
expired. The documents, the readiness view and the dashboard use it; Alerts
stay on the Endorsement's own date. Plain reads: no Audit Record.
"""

from datetime import timedelta

import pytest

from app.services import daily_check
from tests.conftest import auth_header
from tests.integration.test_alerts_api import app_db  # noqa: F401 (a fixture)
from tests.integration.test_documents_api import TODAY, _uploaded, day
from tests.integration.test_reviews_api import _reviewed


@pytest.fixture
async def world(crew, make_account, documents_cleanup, storage, settings_reset, owner_db):
    master = await crew.position("Master")
    alpha = await crew.vessel("Alpha")
    officer = await make_account(role="crewing_officer")
    await crew.link(officer, alpha)
    coc = await owner_db.fetchval(
        "INSERT INTO public.document_type (name, expires) VALUES ('CoC', true) RETURNING id"
    )
    endorsement = await owner_db.fetchval(
        """
        INSERT INTO public.document_type (name, expires, depends_on_id)
        VALUES ('Flag endorsement', true, $1) RETURNING id
        """,
        coc,
    )
    for type_id in (coc, endorsement):
        await owner_db.execute(
            "INSERT INTO public.position_requirement (position_id, document_type_id) VALUES ($1, $2)",
            master, type_id,
        )
    anna = await crew.seafarer(master, "Anna")
    assignment = await owner_db.fetchval(
        """
        INSERT INTO public.assignment (seafarer_id, vessel_id, position_id, start_date, end_date)
        VALUES ($1, $2, $3, $4::text::date, $5::text::date) RETURNING id
        """,
        anna, alpha, master, day(10), day(100),
    )
    # The largest Alert Step is 30 days.
    await owner_db.execute("UPDATE public.settings SET alert_steps = '{30,7,0}'")
    return {
        "coc": coc,
        "endorsement": endorsement,
        "anna": anna,
        "assignment": assignment,
        "officer": auth_header(officer),
        "admin": auth_header(await make_account(role="administrator")),
    }


async def _documents(client, w) -> dict[str, dict]:
    res = await client.get(f"/api/seafarers/{w['anna']}/documents", headers=w["officer"])
    assert res.status_code == 200, res.text
    return {d["document_type_name"]: d for d in res.json()}


async def test_the_certificate_caps_the_endorsement_everywhere(client, world):
    w = world
    await _uploaded(client, w["officer"], w["anna"], w["coc"], expiry_date=day(5))
    doc = await _uploaded(client, w["officer"], w["anna"], w["endorsement"], expiry_date=day(365))

    summary = (await _documents(client, w))["Flag endorsement"]
    assert summary["current_version"]["expiry_date"] == day(365)
    assert summary["effective_expiry"] == day(5)
    assert summary["capped_by"] == "CoC"
    assert summary["certificate_missing"] is False
    assert summary["expiry_status"] == "expiring_soon"

    detail = (await client.get(f"/api/documents/{doc['id']}", headers=w["officer"])).json()
    assert (detail["effective_expiry"], detail["capped_by"]) == (day(5), "CoC")
    assert detail["expiry_status"] == "expiring_soon"

    view = (
        await client.get(f"/api/assignments/{w['assignment']}/readiness", headers=w["officer"])
    ).json()
    entry = next(e for e in view["buckets"]["before_joining"] if e["name"] == "Flag endorsement")
    assert entry["coverage"] == "runs_out_before_start"
    assert entry["expiry_date"] == day(365)
    assert entry["effective_expiry"] == day(5)
    assert entry["suggestion"] == f"Renew CoC before joining (endorsement capped at {day(5)})"

    res = await client.get("/api/dashboard", params={"queue": "expiring_soon"}, headers=w["officer"])
    board = res.json()
    [group] = board["groups"]
    by_type = {e["document_type_name"]: e for e in group["entries"]}
    assert by_type["Flag endorsement"]["effective_expiry"] == day(5)
    assert by_type["Flag endorsement"]["capped_by"] == "CoC"


async def test_without_a_certificate_the_endorsement_counts_as_expired(client, world):
    w = world
    await _uploaded(client, w["officer"], w["anna"], w["endorsement"], expiry_date=day(365))

    summary = (await _documents(client, w))["Flag endorsement"]
    assert summary["expiry_status"] == "expired"
    assert summary["certificate_missing"] is True
    assert summary["effective_expiry"] is None

    view = (
        await client.get(f"/api/assignments/{w['assignment']}/readiness", headers=w["officer"])
    ).json()
    entry = next(e for e in view["buckets"]["before_joining"] if e["name"] == "Flag endorsement")
    assert entry["coverage"] == "runs_out_before_start"
    assert entry["certificate_missing"] is True
    assert entry["suggestion"] == "Obtain CoC before joining (certificate missing)"

    res = await client.get("/api/dashboard", params={"queue": "expired"}, headers=w["officer"])
    board = res.json()
    [group] = board["groups"]
    [entry] = group["entries"]
    assert entry["document_type_name"] == "Flag endorsement"
    assert entry["certificate_missing"] is True

    totals = (await client.get("/api/dashboard/totals", headers=w["admin"])).json()
    assert totals["totals"]["expired"] == 1


async def test_a_rejected_certificate_version_falls_back_to_the_one_before(client, world):
    w = world
    cert = await _uploaded(client, w["officer"], w["anna"], w["coc"], expiry_date=day(200))
    renewal = await _uploaded(client, w["officer"], w["anna"], w["coc"], expiry_date=day(50))
    await _uploaded(client, w["officer"], w["anna"], w["endorsement"], expiry_date=day(365))
    # Awaiting review, the renewal counts.
    assert (await _documents(client, w))["Flag endorsement"]["effective_expiry"] == day(50)

    newest = renewal["versions"][0]["id"]
    assert newest != cert["versions"][0]["id"]
    await _reviewed(client, w["admin"], newest, decision="reject", comment="Wrong scan")
    assert (await _documents(client, w))["Flag endorsement"]["effective_expiry"] == day(200)


async def test_alerts_stay_on_the_endorsements_own_date(client, world, app_db, owner_db):
    w = world
    cert = await _uploaded(client, w["officer"], w["anna"], w["coc"], expiry_date=day(5))
    endorsement = await _uploaded(
        client, w["officer"], w["anna"], w["endorsement"], expiry_date=day(40)
    )
    await daily_check.raise_alerts(app_db, TODAY)
    rows = await owner_db.fetch("SELECT document_id, step, expiry_date FROM public.alert")
    # Capped at day 5, but its own day 40 hasn't reached the 30-day step yet.
    assert {r["document_id"] for r in rows} == {cert["id"]}

    await daily_check.raise_alerts(app_db, TODAY + timedelta(days=10))
    rows = await owner_db.fetch(
        "SELECT step, expiry_date FROM public.alert WHERE document_id = $1", endorsement["id"]
    )
    assert [(r["step"], r["expiry_date"].isoformat()) for r in rows] == [(30, day(40))]
