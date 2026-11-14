"""Requirements through the HTTP API (FR-08, T2, T7).

Administrators edit the Position Requirement matrix and the exceptions; all
staff read them and evaluate the required set for a (Position, Vessel or none)
pair. Every change leaves an Audit Record; every refused write leaves a
refused-access record.
"""

import json

import pytest

from tests.conftest import auth_header

pytestmark = pytest.mark.usefixtures("reference_cleanup")


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
async def ref(owner_db) -> dict[str, int]:
    async def position(name):
        return await owner_db.fetchval("INSERT INTO public.position (name) VALUES ($1) RETURNING id", name)

    async def doc_type(name):
        return await owner_db.fetchval(
            "INSERT INTO public.document_type (name) VALUES ($1) RETURNING id", name
        )

    async def vessel(name, imo, flag):
        return await owner_db.fetchval(
            "INSERT INTO public.vessel (name, imo_number, flag) VALUES ($1, $2, $3) RETURNING id",
            name, imo, flag,
        )

    return {
        "master": await position("Master"),
        "cook": await position("Cook"),
        "passport": await doc_type("Passport"),
        "medical": await doc_type("Medical"),
        "visa": await doc_type("Visa"),
        "aurora": await vessel("MV Aurora", "9123456", "MT"),
        "borealis": await vessel("MV Borealis", "9123457", "MT"),
    }


async def _audit(owner_db, target_type: str, target_id) -> list[dict]:
    rows = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE target_type = $1 AND target_id = $2 ORDER BY id",
        target_type,
        str(target_id),
    )
    return [dict(r) for r in rows]


def _exception(ref, **fields) -> dict:
    return {
        "vessel_id": None,
        "flag": "MT",
        "position_id": None,
        "document_type_id": ref["visa"],
        "effect": "add",
        "reason": "Flag state rule",
        **fields,
    }


async def _create_exception(client, admin, body: dict) -> dict:
    res = await client.post("/api/requirement-exceptions", json=body, headers=admin)
    assert res.status_code == 201, res.text
    return res.json()


async def _set(client, admin, position_id, type_id):
    res = await client.put(f"/api/requirements/{position_id}/{type_id}", headers=admin)
    assert res.status_code == 204, res.text


async def _evaluate(client, headers, position_id, vessel_id=None) -> list[int]:
    params = {"position": position_id}
    if vessel_id is not None:
        params["vessel"] = vessel_id
    res = await client.get("/api/requirements/evaluate", params=params, headers=headers)
    assert res.status_code == 200, res.text
    return sorted(t["id"] for t in res.json()["required"])


# --- The matrix ------------------------------------------------------------------


async def test_admin_sets_and_clears_a_cell(client, admin, ref, owner_db):
    await _set(client, admin, ref["master"], ref["passport"])
    res = await client.get("/api/requirements", headers=admin)
    assert res.json() == [{"position_id": ref["master"], "document_type_id": ref["passport"]}]

    res = await client.delete(f"/api/requirements/{ref['master']}/{ref['passport']}", headers=admin)
    assert res.status_code == 204
    assert (await client.get("/api/requirements", headers=admin)).json() == []

    records = await _audit(owner_db, "position_requirement", f"{ref['master']}/{ref['passport']}")
    assert [r["action"] for r in records] == ["requirement_added", "requirement_removed"]
    pair = {"position_id": ref["master"], "document_type_id": ref["passport"]}
    assert json.loads(records[0]["after"]) == pair
    assert json.loads(records[1]["before"]) == pair


async def test_setting_a_set_cell_or_clearing_a_clear_one_changes_nothing(client, admin, ref, owner_db):
    await _set(client, admin, ref["master"], ref["passport"])
    await _set(client, admin, ref["master"], ref["passport"])
    res = await client.delete(f"/api/requirements/{ref['master']}/{ref['medical']}", headers=admin)
    assert res.status_code == 204

    assert len((await client.get("/api/requirements", headers=admin)).json()) == 1
    assert len(await _audit(owner_db, "position_requirement", f"{ref['master']}/{ref['passport']}")) == 1
    assert await _audit(owner_db, "position_requirement", f"{ref['master']}/{ref['medical']}") == []


async def test_a_retired_position_or_type_cannot_get_a_new_requirement(client, admin, ref, owner_db):
    await owner_db.execute("UPDATE public.document_type SET retired = true WHERE id = $1", ref["visa"])
    await owner_db.execute("UPDATE public.position SET retired = true WHERE id = $1", ref["cook"])
    res = await client.put(f"/api/requirements/{ref['master']}/{ref['visa']}", headers=admin)
    assert res.status_code == 422
    res = await client.put(f"/api/requirements/{ref['cook']}/{ref['passport']}", headers=admin)
    assert res.status_code == 422


async def test_an_unknown_position_or_type_is_404(client, admin, ref):
    assert (await client.put(f"/api/requirements/999999/{ref['visa']}", headers=admin)).status_code == 404
    assert (await client.put(f"/api/requirements/{ref['master']}/999999", headers=admin)).status_code == 404


async def test_add_to_all_positions_skips_retired_and_already_set(client, admin, ref, owner_db):
    retired = await owner_db.fetchval(
        "INSERT INTO public.position (name, retired) VALUES ('Purser', true) RETURNING id"
    )
    await _set(client, admin, ref["master"], ref["passport"])

    res = await client.post(
        "/api/requirements/add-to-all-positions",
        json={"document_type_id": ref["passport"]},
        headers=admin,
    )
    assert res.status_code == 200
    assert res.json() == {"added": [ref["cook"]]}
    matrix = (await client.get("/api/requirements", headers=admin)).json()
    assert sorted(c["position_id"] for c in matrix) == sorted([ref["master"], ref["cook"]])
    assert retired not in [c["position_id"] for c in matrix]

    [record] = await _audit(owner_db, "position_requirement", f"{ref['cook']}/{ref['passport']}")
    assert record["action"] == "requirement_added"


async def test_add_to_all_positions_refuses_a_retired_type(client, admin, ref, owner_db):
    await owner_db.execute("UPDATE public.document_type SET retired = true WHERE id = $1", ref["visa"])
    res = await client.post(
        "/api/requirements/add-to-all-positions", json={"document_type_id": ref["visa"]}, headers=admin
    )
    assert res.status_code == 422


async def test_deleting_a_position_with_requirements_says_retire_instead(client, admin, ref):
    await _set(client, admin, ref["cook"], ref["passport"])
    res = await client.delete(f"/api/positions/{ref['cook']}", headers=admin)
    assert res.status_code == 409
    assert "retire" in res.json()["detail"].lower()


# --- Exceptions ------------------------------------------------------------------


async def test_admin_creates_edits_and_deletes_an_exception(client, admin, ref, owner_db):
    created = await _create_exception(client, admin, _exception(ref, flag="mt"))
    assert created["flag"] == "MT"
    assert created["document_type_name"] == "Visa"
    eid = created["id"]

    res = await client.put(
        f"/api/requirement-exceptions/{eid}",
        json=_exception(ref, flag=None, vessel_id=ref["aurora"], reason="Charterer asks"),
        headers=admin,
    )
    assert res.status_code == 200, res.text
    assert res.json()["vessel_name"] == "MV Aurora"
    listed = (await client.get("/api/requirement-exceptions", headers=admin)).json()
    assert [e["id"] for e in listed] == [eid]

    assert (await client.delete(f"/api/requirement-exceptions/{eid}", headers=admin)).status_code == 204
    assert (await client.get("/api/requirement-exceptions", headers=admin)).json() == []

    records = await _audit(owner_db, "requirement_exception", eid)
    assert [r["action"] for r in records] == [
        "requirement_exception_created",
        "requirement_exception_edited",
        "requirement_exception_deleted",
    ]
    assert '"reason": "Flag state rule"' in records[0]["after"]
    assert json.loads(records[1]["before"]) == {
        "vessel_id": None, "flag": "MT", "reason": "Flag state rule"
    }
    assert json.loads(records[1]["after"]) == {
        "vessel_id": ref["aurora"], "flag": None, "reason": "Charterer asks"
    }
    assert '"effect": "add"' in records[2]["before"]


async def test_an_edit_that_changes_nothing_writes_no_record(client, admin, ref, owner_db):
    created = await _create_exception(client, admin, _exception(ref))
    res = await client.put(f"/api/requirement-exceptions/{created['id']}", json=_exception(ref), headers=admin)
    assert res.status_code == 200
    assert len(await _audit(owner_db, "requirement_exception", created["id"])) == 1


async def test_a_duplicate_exception_is_a_conflict(client, admin, ref):
    await _create_exception(client, admin, _exception(ref))
    res = await client.post(
        "/api/requirement-exceptions", json=_exception(ref, effect="remove"), headers=admin
    )
    assert res.status_code == 409
    # A Position-specific one for the same scope and type is a different rule.
    await _create_exception(client, admin, _exception(ref, position_id=ref["cook"], effect="remove"))


@pytest.mark.parametrize(
    "case", ["no scope", "both scopes", "unknown flag", "blank reason", "unknown effect"]
)
async def test_an_invalid_exception_is_refused(client, admin, ref, case):
    fields = {
        "no scope": {"flag": None},
        "both scopes": {"vessel_id": ref["aurora"]},
        "unknown flag": {"flag": "XX"},
        "blank reason": {"reason": "   "},
        "unknown effect": {"effect": "maybe"},
    }[case]
    res = await client.post("/api/requirement-exceptions", json=_exception(ref, **fields), headers=admin)
    assert res.status_code == 422


async def test_an_exception_cannot_pick_a_retired_type_position_or_an_inactive_vessel(client, admin, ref, owner_db):
    await owner_db.execute("UPDATE public.document_type SET retired = true WHERE id = $1", ref["medical"])
    await owner_db.execute("UPDATE public.position SET retired = true WHERE id = $1", ref["cook"])
    await owner_db.execute("UPDATE public.vessel SET active = false WHERE id = $1", ref["borealis"])
    for body in (
        _exception(ref, document_type_id=ref["medical"]),
        _exception(ref, position_id=ref["cook"]),
        _exception(ref, flag=None, vessel_id=ref["borealis"]),
        _exception(ref, flag=None, vessel_id=999999),
    ):
        res = await client.post("/api/requirement-exceptions", json=body, headers=admin)
        assert res.status_code == 422, body


async def test_an_edit_may_keep_a_type_retired_since(client, admin, ref, owner_db):
    created = await _create_exception(client, admin, _exception(ref))
    await owner_db.execute("UPDATE public.document_type SET retired = true WHERE id = $1", ref["visa"])
    res = await client.put(
        f"/api/requirement-exceptions/{created['id']}",
        json=_exception(ref, reason="Still the rule"),
        headers=admin,
    )
    assert res.status_code == 200


async def test_an_unknown_exception_is_404(client, admin, ref):
    assert (await client.put("/api/requirement-exceptions/999999", json=_exception(ref), headers=admin)).status_code == 404
    assert (await client.delete("/api/requirement-exceptions/999999", headers=admin)).status_code == 404


# --- The preview -----------------------------------------------------------------


async def test_evaluate_a_vessel_exception_beats_a_flag_exception(client, admin, ref):
    await _set(client, admin, ref["cook"], ref["passport"])
    await _set(client, admin, ref["cook"], ref["medical"])
    flag_rule = await _create_exception(client, admin, _exception(ref))
    vessel_rule = await _create_exception(
        client, admin,
        _exception(ref, flag=None, vessel_id=ref["aurora"], effect="remove", reason="Local trade only"),
    )

    assert await _evaluate(client, admin, ref["cook"]) == sorted([ref["passport"], ref["medical"]])
    assert await _evaluate(client, admin, ref["cook"], ref["borealis"]) == sorted(
        [ref["passport"], ref["medical"], ref["visa"]]
    )
    assert await _evaluate(client, admin, ref["cook"], ref["aurora"]) == sorted(
        [ref["passport"], ref["medical"]]
    )

    res = await client.get(
        "/api/requirements/evaluate",
        params={"position": ref["cook"], "vessel": ref["aurora"]},
        headers=admin,
    )
    body = res.json()
    assert [e["id"] for e in body["applied_exceptions"]] == [vessel_rule["id"]]
    assert body["vessel"]["flag"] == "MT"
    res = await client.get(
        "/api/requirements/evaluate",
        params={"position": ref["cook"], "vessel": ref["borealis"]},
        headers=admin,
    )
    visa = next(t for t in res.json()["required"] if t["id"] == ref["visa"])
    assert visa == {"id": ref["visa"], "name": "Visa", "exception_id": flag_rule["id"]}


async def test_evaluate_leaves_out_retired_types(client, admin, ref, owner_db):
    await _set(client, admin, ref["cook"], ref["passport"])
    await _set(client, admin, ref["cook"], ref["medical"])
    await owner_db.execute("UPDATE public.document_type SET retired = true WHERE id = $1", ref["medical"])
    assert await _evaluate(client, admin, ref["cook"]) == [ref["passport"]]


async def test_evaluate_an_unknown_position_or_vessel_is_404(client, admin, ref):
    res = await client.get("/api/requirements/evaluate", params={"position": 999999}, headers=admin)
    assert res.status_code == 404
    res = await client.get(
        "/api/requirements/evaluate", params={"position": ref["cook"], "vessel": 999999}, headers=admin
    )
    assert res.status_code == 404


# --- Who may do it ---------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/api/requirements", "/api/requirement-exceptions", "/api/requirements/evaluate?position={cook}"],
)
async def test_all_staff_can_read(client, admin, officer, manager, ref, path):
    for headers in (admin, officer, manager):
        res = await client.get(path.format(**ref), headers=headers)
        assert res.status_code == 200, res.text


@pytest.mark.parametrize("who", ["officer", "manager"])
@pytest.mark.parametrize(
    "method, path",
    [
        ("PUT", "/api/requirements/{master}/{passport}"),
        ("DELETE", "/api/requirements/{master}/{medical}"),
        ("POST", "/api/requirements/add-to-all-positions"),
        ("POST", "/api/requirement-exceptions"),
        ("PUT", "/api/requirement-exceptions/{exception}"),
        ("DELETE", "/api/requirement-exceptions/{exception}"),
    ],
)
async def test_only_administrators_write(
    client, admin, officer, manager, ref, owner_db, who, method, path
):
    await _set(client, admin, ref["master"], ref["medical"])
    exception = await _create_exception(client, admin, _exception(ref))
    headers = {"officer": officer, "manager": manager}[who]
    url = path.format(**ref, exception=exception["id"])

    res = await client.request(
        method,
        url,
        json={**_exception(ref, reason="Hijacked"), "document_type_id": ref["passport"]},
        headers=headers,
    )
    assert res.status_code == 403

    matrix = (await client.get("/api/requirements", headers=admin)).json()
    assert matrix == [{"position_id": ref["master"], "document_type_id": ref["medical"]}]
    [kept] = (await client.get("/api/requirement-exceptions", headers=admin)).json()
    assert kept["reason"] == "Flag state rule"
    refused = await owner_db.fetchval(
        """
        SELECT count(*) FROM public.audit_log
         WHERE action = 'access_refused' AND target_id = $1 AND reason = 'wrong_role'
           AND request_id = $2
        """,
        f"{method} {url}",
        res.headers["x-request-id"],
    )
    assert refused == 1
