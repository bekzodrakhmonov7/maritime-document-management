"""Fleet and document rules through the HTTP API (FR-05, FR-07, T2, T5, T7).

Vessels: administrators and officers read; administrators write.
Positions and Document Types: all staff read; administrators write.
Every write leaves an Audit Record with the changed fields.
"""

import pytest

from tests.conftest import auth_header

pytestmark = pytest.mark.usefixtures("reference_cleanup")

VESSEL = {"name": "MV Aurora", "imo_number": "9123456", "flag": "MT"}


async def _audit(owner_db, target_type: str, target_id) -> list[dict]:
    rows = await owner_db.fetch(
        """
        SELECT * FROM public.audit_log
         WHERE target_type = $1 AND target_id = $2
         ORDER BY id
        """,
        target_type,
        str(target_id),
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


async def _create(client, admin, path: str, body: dict) -> dict:
    res = await client.post(path, json=body, headers=admin)
    assert res.status_code == 201, res.text
    return res.json()


def _doc_type(name: str, **rules) -> dict:
    return {
        "name": name,
        "expires": True,
        "max_validity_months": None,
        "renewable_at_sea": False,
        "depends_on_id": None,
        **rules,
    }


# --- Vessels -------------------------------------------------------------------


async def test_admin_creates_a_flagged_vessel(client, admin, owner_db):
    vessel = await _create(client, admin, "/api/vessels", VESSEL)
    assert vessel["flag"] == "MT"
    assert vessel["active"] is True

    [record] = await _audit(owner_db, "vessel", vessel["id"])
    assert record["action"] == "vessel_created"
    assert '"flag": "MT"' in record["after"]


async def test_a_lowercase_flag_is_stored_in_capitals(client, admin):
    vessel = await _create(client, admin, "/api/vessels", {**VESSEL, "flag": "gr"})
    assert vessel["flag"] == "GR"


@pytest.mark.parametrize("flag", ["XX", "GRC", "", "1A"])
async def test_a_flag_must_be_an_assigned_iso_code(client, admin, flag):
    res = await client.post("/api/vessels", json={**VESSEL, "flag": flag}, headers=admin)
    assert res.status_code == 422


async def test_a_duplicate_imo_number_is_a_conflict(client, admin):
    await _create(client, admin, "/api/vessels", VESSEL)
    res = await client.post("/api/vessels", json={**VESSEL, "name": "Other"}, headers=admin)
    assert res.status_code == 409


async def test_officers_see_the_fleet_read_only(client, admin, officer):
    vessel = await _create(client, admin, "/api/vessels", VESSEL)

    listed = await client.get("/api/vessels", headers=officer)
    assert listed.status_code == 200
    assert [v["id"] for v in listed.json()] == [vessel["id"]]
    got = await client.get(f"/api/vessels/{vessel['id']}", headers=officer)
    assert got.status_code == 200
    assert got.json()["imo_number"] == VESSEL["imo_number"]


async def test_an_unknown_vessel_is_404(client, admin):
    assert (await client.get("/api/vessels/999999", headers=admin)).status_code == 404


@pytest.mark.parametrize("path", ["/api/vessels", "/api/vessels/1"])
async def test_a_manager_cannot_read_vessels(client, manager, path):
    res = await client.get(path, headers=manager)
    assert res.status_code == 403


@pytest.mark.parametrize(
    "method, path",
    [
        ("POST", "/api/vessels"),
        ("PUT", "/api/vessels/{id}"),
        ("POST", "/api/vessels/{id}/deactivate"),
        ("POST", "/api/vessels/{id}/reactivate"),
    ],
)
async def test_an_officer_cannot_change_vessels(client, admin, officer, owner_db, method, path):
    vessel = await _create(client, admin, "/api/vessels", VESSEL)
    res = await client.request(
        method, path.format(id=vessel["id"]), json={**VESSEL, "name": "Hijacked"}, headers=officer
    )
    assert res.status_code == 403
    row = await owner_db.fetchrow("SELECT name, active FROM public.vessel WHERE id = $1", vessel["id"])
    assert (row["name"], row["active"]) == ("MV Aurora", True)


async def test_editing_a_vessel_records_only_the_changed_fields(client, admin, owner_db):
    vessel = await _create(client, admin, "/api/vessels", VESSEL)
    res = await client.put(
        f"/api/vessels/{vessel['id']}", json={**VESSEL, "flag": "PA"}, headers=admin
    )
    assert res.status_code == 200
    assert res.json()["flag"] == "PA"

    record = (await _audit(owner_db, "vessel", vessel["id"]))[-1]
    assert record["action"] == "vessel_edited"
    assert record["before"] == '{"flag": "MT"}'
    assert record["after"] == '{"flag": "PA"}'


async def test_an_edit_that_changes_nothing_writes_no_record(client, admin, owner_db):
    vessel = await _create(client, admin, "/api/vessels", VESSEL)
    res = await client.put(f"/api/vessels/{vessel['id']}", json=VESSEL, headers=admin)
    assert res.status_code == 200
    assert [r["action"] for r in await _audit(owner_db, "vessel", vessel["id"])] == ["vessel_created"]


async def test_deactivate_and_reactivate_a_vessel(client, admin, owner_db):
    vessel = await _create(client, admin, "/api/vessels", VESSEL)

    res = await client.post(f"/api/vessels/{vessel['id']}/deactivate", headers=admin)
    assert res.status_code == 200
    assert res.json()["active"] is False
    again = await client.post(f"/api/vessels/{vessel['id']}/deactivate", headers=admin)
    assert again.status_code == 409

    res = await client.post(f"/api/vessels/{vessel['id']}/reactivate", headers=admin)
    assert res.json()["active"] is True

    actions = [r["action"] for r in await _audit(owner_db, "vessel", vessel["id"])]
    assert actions == ["vessel_created", "vessel_deactivated", "vessel_reactivated"]


# --- Positions -------------------------------------------------------------------


async def test_all_staff_can_list_positions(client, admin, officer, manager):
    position = await _create(client, admin, "/api/positions", {"name": "Master"})
    for headers in (admin, officer, manager):
        res = await client.get("/api/positions", headers=headers)
        assert res.status_code == 200
        assert [p["id"] for p in res.json()] == [position["id"]]


@pytest.mark.parametrize(
    "method, path",
    [
        ("POST", "/api/positions"),
        ("PUT", "/api/positions/{id}"),
        ("POST", "/api/positions/{id}/retire"),
        ("POST", "/api/positions/{id}/unretire"),
        ("DELETE", "/api/positions/{id}"),
    ],
)
async def test_an_officer_cannot_change_positions(client, admin, officer, method, path):
    position = await _create(client, admin, "/api/positions", {"name": "Master"})
    res = await client.request(
        method, path.format(id=position["id"]), json={"name": "Captain"}, headers=officer
    )
    assert res.status_code == 403


async def test_position_names_are_unique(client, admin):
    await _create(client, admin, "/api/positions", {"name": "Chief Engineer"})
    res = await client.post("/api/positions", json={"name": " chief engineer "}, headers=admin)
    assert res.status_code == 409


async def test_position_writes_are_audited(client, admin, owner_db):
    position = await _create(client, admin, "/api/positions", {"name": "Bosun"})
    pid = position["id"]

    assert (await client.put(f"/api/positions/{pid}", json={"name": "Boatswain"}, headers=admin)).status_code == 200
    retired = await client.post(f"/api/positions/{pid}/retire", headers=admin)
    assert retired.json()["retired"] is True
    assert (await client.post(f"/api/positions/{pid}/retire", headers=admin)).status_code == 409
    assert (await client.post(f"/api/positions/{pid}/unretire", headers=admin)).json()["retired"] is False
    assert (await client.delete(f"/api/positions/{pid}", headers=admin)).status_code == 204

    records = await _audit(owner_db, "position", pid)
    assert [r["action"] for r in records] == [
        "position_created",
        "position_edited",
        "position_retired",
        "position_unretired",
        "position_deleted",
    ]
    assert records[1]["before"] == '{"name": "Bosun"}'
    assert records[1]["after"] == '{"name": "Boatswain"}'
    assert await owner_db.fetchval("SELECT count(*) FROM public.position WHERE id = $1", pid) == 0


async def test_an_unknown_position_is_404(client, admin):
    assert (await client.delete("/api/positions/999999", headers=admin)).status_code == 404


# --- Document Types --------------------------------------------------------------


async def test_all_staff_can_list_document_types(client, admin, officer, manager):
    doc_type = await _create(client, admin, "/api/document-types", _doc_type("Passport"))
    for headers in (admin, officer, manager):
        res = await client.get("/api/document-types", headers=headers)
        assert res.status_code == 200
        assert [t["id"] for t in res.json()] == [doc_type["id"]]


@pytest.mark.parametrize(
    "method, path",
    [
        ("POST", "/api/document-types"),
        ("PUT", "/api/document-types/{id}"),
        ("POST", "/api/document-types/{id}/retire"),
        ("POST", "/api/document-types/{id}/unretire"),
        ("DELETE", "/api/document-types/{id}"),
    ],
)
async def test_an_officer_cannot_change_document_types(client, admin, officer, method, path):
    doc_type = await _create(client, admin, "/api/document-types", _doc_type("Passport"))
    res = await client.request(
        method, path.format(id=doc_type["id"]), json=_doc_type("Visa"), headers=officer
    )
    assert res.status_code == 403


async def test_admin_creates_an_endorsement(client, admin, owner_db):
    cert = await _create(
        client, admin, "/api/document-types", _doc_type("CoC", max_validity_months=60)
    )
    endorsement = await _create(
        client,
        admin,
        "/api/document-types",
        _doc_type("Flag endorsement", renewable_at_sea=True, depends_on_id=cert["id"]),
    )
    assert endorsement["depends_on_id"] == cert["id"]
    assert endorsement["renewable_at_sea"] is True
    assert cert["max_validity_months"] == 60

    [record] = await _audit(owner_db, "document_type", endorsement["id"])
    assert record["action"] == "document_type_created"


async def test_max_validity_is_refused_on_a_non_expiring_type(client, admin):
    res = await client.post(
        "/api/document-types",
        json=_doc_type("Seaman's book", expires=False, max_validity_months=12),
        headers=admin,
    )
    assert res.status_code == 422


async def test_an_edit_cannot_stop_a_type_expiring_while_it_has_a_max_validity(client, admin):
    doc_type = await _create(
        client, admin, "/api/document-types", _doc_type("Medical", max_validity_months=24)
    )
    res = await client.put(
        f"/api/document-types/{doc_type['id']}",
        json=_doc_type("Medical", expires=False, max_validity_months=24),
        headers=admin,
    )
    assert res.status_code == 422


async def test_an_endorsement_cannot_depend_on_an_endorsement(client, admin):
    cert = await _create(client, admin, "/api/document-types", _doc_type("CoC"))
    endorsement = await _create(
        client, admin, "/api/document-types", _doc_type("End", depends_on_id=cert["id"])
    )
    res = await client.post(
        "/api/document-types",
        json=_doc_type("End of end", depends_on_id=endorsement["id"]),
        headers=admin,
    )
    assert res.status_code == 422
    assert "one level" in res.json()["detail"]


async def test_an_endorsement_cannot_depend_on_a_non_expiring_type(client, admin):
    book = await _create(client, admin, "/api/document-types", _doc_type("Book", expires=False))
    res = await client.post(
        "/api/document-types", json=_doc_type("End", depends_on_id=book["id"]), headers=admin
    )
    assert res.status_code == 422
    assert "must expire" in res.json()["detail"]


async def test_a_type_cannot_depend_on_itself(client, admin):
    doc_type = await _create(client, admin, "/api/document-types", _doc_type("CoC"))
    res = await client.put(
        f"/api/document-types/{doc_type['id']}",
        json=_doc_type("CoC", depends_on_id=doc_type["id"]),
        headers=admin,
    )
    assert res.status_code == 422


async def test_an_endorsement_of_an_unknown_type_is_refused(client, admin):
    res = await client.post(
        "/api/document-types", json=_doc_type("End", depends_on_id=999999), headers=admin
    )
    assert res.status_code == 422


async def test_deleting_a_used_document_type_says_retire_instead(client, admin, owner_db):
    cert = await _create(client, admin, "/api/document-types", _doc_type("CoC"))
    await _create(client, admin, "/api/document-types", _doc_type("End", depends_on_id=cert["id"]))

    res = await client.delete(f"/api/document-types/{cert['id']}", headers=admin)
    assert res.status_code == 409
    assert "retire" in res.json()["detail"].lower()
    assert await owner_db.fetchval(
        "SELECT count(*) FROM public.document_type WHERE id = $1", cert["id"]
    ) == 1
    assert [r["action"] for r in await _audit(owner_db, "document_type", cert["id"])] == [
        "document_type_created"
    ]


async def test_document_type_writes_are_audited(client, admin, owner_db):
    doc_type = await _create(client, admin, "/api/document-types", _doc_type("Yellow fever"))
    tid = doc_type["id"]

    res = await client.put(
        f"/api/document-types/{tid}",
        json=_doc_type("Yellow fever", expires=False),
        headers=admin,
    )
    assert res.status_code == 200
    assert (await client.post(f"/api/document-types/{tid}/retire", headers=admin)).json()["retired"] is True
    assert (await client.post(f"/api/document-types/{tid}/unretire", headers=admin)).json()["retired"] is False
    assert (await client.delete(f"/api/document-types/{tid}", headers=admin)).status_code == 204

    records = await _audit(owner_db, "document_type", tid)
    assert [r["action"] for r in records] == [
        "document_type_created",
        "document_type_edited",
        "document_type_retired",
        "document_type_unretired",
        "document_type_deleted",
    ]
    assert records[1]["before"] == '{"expires": true}'
    assert records[1]["after"] == '{"expires": false}'
