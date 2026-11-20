"""Reviews and Verifications through the HTTP API (FR-11, FR-12; T1, T7, T8).

The app runs as app_backend against the real database; the private bucket is
the in-memory stand-in from conftest.
"""

import json

import pytest

from tests.conftest import auth_header
from tests.integration.test_documents_api import PDF, _jpeg, _records, _uploaded, day


@pytest.fixture
async def world(crew, make_account, documents_cleanup, storage, owner_db):
    master = await crew.position("Master")
    alpha = await crew.vessel("Alpha")
    bravo = await crew.vessel("Bravo")
    officer_a = await make_account(role="crewing_officer", full_name="Olena Officer")
    officer_a2 = await make_account(role="crewing_officer", full_name="Pavel Second")
    officer_b = await make_account(role="crewing_officer")
    manager = await make_account(role="manager")
    admin = await make_account(role="administrator", full_name="Ada Admin")
    await crew.link(officer_a, alpha)
    await crew.link(officer_a2, alpha)
    await crew.link(officer_b, bravo)
    passport = await owner_db.fetchval(
        "INSERT INTO public.document_type (name, expires) VALUES ('Passport', true) RETURNING id"
    )
    return {
        "ids": {"officer_a": officer_a, "officer_a2": officer_a2, "manager": manager, "admin": admin},
        "master": master,
        "bravo": bravo,
        "anna": await crew.seafarer(master, "Anna"),
        "passport": passport,
        "admin": auth_header(admin),
        "manager": auth_header(manager),
        "officer_a": auth_header(officer_a),
        "officer_a2": auth_header(officer_a2),
        "officer_b": auth_header(officer_b),
    }


async def _passport(client, w, headers=None, **fields) -> dict:
    return await _uploaded(client, headers or w["officer_a"], w["anna"], w["passport"], **fields)


async def _review(client, headers, version_id, decision="accept", comment="Checked against the scan"):
    return await client.post(
        f"/api/versions/{version_id}/reviews",
        json={"decision": decision, "comment": comment},
        headers=headers,
    )


async def _reviewed(client, headers, version_id, decision="accept", comment="Checked") -> dict:
    res = await _review(client, headers, version_id, decision, comment)
    assert res.status_code == 201, res.text
    return res.json()


def _verification_form(**fields) -> dict:
    return {
        "checked_on": day(-1),
        "source": "E-mail to the flag registry",
        "result": "confirmed",
        "reference": "REG-2026-17",
        **fields,
    }


async def _verify(client, headers, version_id, *, proof=None, filename="letter.pdf", **fields):
    files = {"file": (filename, proof, "application/octet-stream")} if proof is not None else None
    return await client.post(
        f"/api/versions/{version_id}/verifications",
        data=_verification_form(**fields),
        files=files,
        headers=headers,
    )


async def _verified(client, headers, version_id, **kw) -> dict:
    res = await _verify(client, headers, version_id, **kw)
    assert res.status_code == 201, res.text
    return res.json()


def _version(doc: dict, number: int) -> dict:
    return next(v for v in doc["versions"] if v["number"] == number)


# --- Reviews -----------------------------------------------------------------------------


async def test_a_second_officer_accepts_a_version(client, world, owner_db):
    doc = await _passport(client, world)
    assert doc["current_version"]["review_state"] == "not_reviewed"
    version_id = doc["versions"][0]["id"]

    doc = await _reviewed(client, world["officer_a2"], version_id, "accept", "Matches the original")
    version = doc["versions"][0]
    assert version["review_state"] == "accepted"
    assert doc["current_version"]["review_state"] == "accepted"
    [review] = version["reviews"]
    assert review["decision"] == "accept"
    assert review["comment"] == "Matches the original"
    assert review["reviewed_by_name"] == "Pavel Second"
    assert doc["verified"] is False  # Reviewed is never Verified

    [record] = await _records(owner_db, "version_reviewed", target_id=str(version_id))
    assert record["target_type"] == "version"
    assert record["seafarer_id"] == world["anna"]
    assert record["actor_id"] == world["ids"]["officer_a2"]
    after = json.loads(record["after"])
    assert after["decision"] == "accept" and after["comment"] == "Matches the original"
    assert after["review_id"] == review["id"]
    assert json.loads(record["before"]) == {"review_state": "not_reviewed"}


async def test_the_uploader_is_refused_through_the_api(client, world, owner_db):
    doc = await _passport(client, world)
    version_id = doc["versions"][0]["id"]
    res = await _review(client, world["officer_a"], version_id)
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "own_version"
    assert await owner_db.fetchval("SELECT count(*) FROM public.review") == 0
    [refused] = await _records(owner_db, "access_refused", actor_id=world["ids"]["officer_a"])
    assert refused["reason"] == "own_version"
    assert await _records(owner_db, "version_reviewed", target_id=str(version_id)) == []


async def test_an_administrator_who_uploaded_cannot_review_either(client, world):
    doc = await _passport(client, world, world["admin"])
    res = await _review(client, world["admin"], doc["versions"][0]["id"])
    assert res.status_code == 403


@pytest.mark.parametrize(
    "body", [{"decision": "accept", "comment": "  "}, {"decision": "approve", "comment": "ok"}, {"decision": "reject"}]
)
async def test_a_review_needs_a_decision_and_a_comment(client, world, body):
    doc = await _passport(client, world)
    res = await client.post(
        f"/api/versions/{doc['versions'][0]['id']}/reviews", json=body, headers=world["admin"]
    )
    assert res.status_code == 422


async def test_a_later_review_overturns_an_earlier_one_and_both_are_kept(client, world):
    doc = await _passport(client, world)
    version_id = doc["versions"][0]["id"]
    await _reviewed(client, world["officer_a2"], version_id, "reject", "Blurred")
    doc = await _reviewed(client, world["admin"], version_id, "accept", "Readable on the original")

    version = doc["versions"][0]
    assert version["review_state"] == "accepted"
    assert version["is_current"] is True
    assert [r["decision"] for r in version["reviews"]] == ["accept", "reject"]  # newest first


async def test_rejecting_the_newest_version_falls_back_to_the_previous_one(client, world):
    await _passport(client, world, expiry_date=day(30))
    renewed = await _passport(client, world, document_number="P-200", issue_date=day(-1), expiry_date=day(3000))
    assert renewed["current_version"]["document_number"] == "P-200"

    doc = await _reviewed(client, world["officer_a2"], _version(renewed, 2)["id"], "reject", "Wrong person")
    assert doc["current_version"]["document_number"] == "P-100"
    assert doc["current_version"]["review_state"] == "not_reviewed"
    assert doc["expiry_status"] == "expiring_soon"
    assert _version(doc, 1)["is_current"] is True
    assert _version(doc, 2)["review_state"] == "rejected"

    res = await client.get(f"/api/seafarers/{world['anna']}/documents", headers=world["officer_a"])
    [row] = res.json()
    assert row["current_version"]["document_number"] == "P-100"
    assert row["expiry_status"] == "expiring_soon"


async def test_every_version_rejected_means_no_current_version(client, world):
    doc = await _passport(client, world)
    doc = await _reviewed(client, world["officer_a2"], doc["versions"][0]["id"], "reject", "Forged")
    assert doc["current_version"] is None
    assert doc["expiry_status"] is None
    assert doc["verified"] is False

    res = await client.get(f"/api/seafarers/{world['anna']}/documents", headers=world["officer_a"])
    assert res.json()[0]["current_version"] is None


async def test_a_details_only_version_needs_a_current_version(client, world):
    doc = await _passport(client, world)
    await _reviewed(client, world["officer_a2"], doc["versions"][0]["id"], "reject", "Forged")
    res = await client.post(
        f"/api/documents/{doc['id']}/versions",
        json={"document_number": "P-9", "issuing_authority": "M", "issue_date": day(-5), "expiry_date": day(50)},
        headers=world["officer_a"],
    )
    assert res.status_code == 409


# --- Verifications -----------------------------------------------------------------------


async def test_an_officer_records_a_confirmed_verification_and_the_document_is_verified(client, world, owner_db):
    doc = await _passport(client, world)
    version_id = doc["versions"][0]["id"]
    # No four-eyes rule: the uploader may record it.
    doc = await _verified(client, world["officer_a"], version_id)
    assert doc["verified"] is True
    [verification] = doc["versions"][0]["verifications"]
    assert verification["result"] == "confirmed"
    assert verification["source"] == "E-mail to the flag registry"
    assert verification["reference"] == "REG-2026-17"
    assert verification["checked_on"] == day(-1)
    assert verification["recorded_by_name"] == "Olena Officer"
    assert verification["proof_original_filename"] is None

    [record] = await _records(owner_db, "verification_recorded", target_id=str(version_id))
    assert record["target_type"] == "version"
    assert record["seafarer_id"] == world["anna"]
    after = json.loads(record["after"])
    assert after["verification_id"] == verification["id"]
    assert after["result"] == "confirmed" and after["reference"] == "REG-2026-17"


async def test_the_latest_verification_decides(client, world):
    doc = await _passport(client, world)
    version_id = doc["versions"][0]["id"]
    await _verified(client, world["officer_a"], version_id)
    doc = await _verified(client, world["officer_a"], version_id, result="not_confirmed", reference="REG-2")
    assert doc["verified"] is False
    assert [v["result"] for v in doc["versions"][0]["verifications"]] == ["not_confirmed", "confirmed"]


async def test_a_renewal_is_not_verified(client, world):
    doc = await _passport(client, world)
    await _verified(client, world["officer_a"], doc["versions"][0]["id"])
    renewed = await _passport(client, world, document_number="P-200", issue_date=day(-1), expiry_date=day(3000))
    assert renewed["verified"] is False
    res = await client.get(f"/api/seafarers/{world['anna']}/documents", headers=world["officer_a"])
    assert res.json()[0]["verified"] is False

    # Rejecting the renewal makes the verified Version current again.
    doc = await _reviewed(client, world["officer_a2"], _version(renewed, 2)["id"], "reject", "Wrong")
    assert doc["verified"] is True


async def test_a_verification_with_a_proof_file_is_stored_cleaned(client, world, storage, owner_db):
    doc = await _passport(client, world)
    doc = await _verified(client, world["officer_a"], doc["versions"][0]["id"], proof=_jpeg(), filename="reply.jpg")
    [verification] = doc["versions"][0]["verifications"]
    assert verification["proof_original_filename"] == "reply.jpg"
    assert verification["proof_content_type"] == "image/jpeg"

    path = await owner_db.fetchval(
        "SELECT proof_file_path FROM public.verification WHERE id = $1", verification["id"]
    )
    assert path.startswith("proofs/") and path.endswith(".jpg")
    content, content_type = storage.objects[path]
    assert content_type == "image/jpeg" and b"TRAILER" not in content


@pytest.mark.parametrize(
    "fields",
    [
        {"result": "maybe"},
        {"source": " "},
        {"reference": ""},
        {"checked_on": day(1)},  # not in the future
        {"checked_on": "not a date"},
    ],
)
async def test_a_verification_needs_its_details(client, world, storage, owner_db, fields):
    doc = await _passport(client, world)
    res = await _verify(client, world["officer_a"], doc["versions"][0]["id"], proof=PDF, **fields)
    assert res.status_code == 422, res.text
    assert await owner_db.fetchval("SELECT count(*) FROM public.verification") == 0
    assert len(storage.objects) == 1  # only the Version's file


async def test_a_proof_file_failing_a_safety_check_is_refused_and_recorded(client, world, storage, owner_db):
    doc = await _passport(client, world)
    version_id = doc["versions"][0]["id"]
    res = await _verify(client, world["officer_a"], version_id, proof=b"GIF89a nope", filename="r.gif")
    assert res.status_code == 415
    assert res.json()["detail"]["code"] == "unsupported_type"

    [record] = await _records(owner_db, "upload_rejected", target_type="version", target_id=str(version_id))
    assert record["target_type"] == "version"
    assert record["outcome"] == "refused"
    assert record["reason"] == "unsupported_type"
    assert record["seafarer_id"] == world["anna"]
    after = json.loads(record["after"])
    assert after == {"purpose": "verification_proof", "size_bytes": 11, "filename": "r.gif"}
    assert await owner_db.fetchval("SELECT count(*) FROM public.verification") == 0
    assert len(storage.objects) == 1


async def test_a_proof_file_over_the_size_setting_is_413(client, world, storage, owner_db, settings_reset):
    doc = await _passport(client, world)
    await owner_db.execute("UPDATE public.settings SET max_file_size_mb = 1")
    res = await _verify(
        client, world["officer_a"], doc["versions"][0]["id"], proof=b"%PDF-" + b"0" * (1024 * 1024)
    )
    assert res.status_code == 413
    assert await owner_db.fetchval("SELECT count(*) FROM public.verification") == 0


async def test_a_failed_transaction_deletes_the_stored_proof_file(client, world, storage, owner_db):
    doc = await _passport(client, world)
    await owner_db.execute(
        """
        CREATE FUNCTION pg_temp.fail() RETURNS trigger LANGUAGE plpgsql
        AS $$ BEGIN RAISE EXCEPTION 'simulated failure'; END; $$;
        CREATE TRIGGER test_fail_verification_insert BEFORE INSERT ON public.verification
            FOR EACH ROW EXECUTE FUNCTION pg_temp.fail();
        """
    )
    try:
        with pytest.raises(Exception):
            await _verify(client, world["officer_a"], doc["versions"][0]["id"], proof=PDF)
    finally:
        await owner_db.execute("DROP TRIGGER test_fail_verification_insert ON public.verification")
    assert len(storage.objects) == 1


# --- Proof file URL ----------------------------------------------------------------------


async def test_a_signed_url_for_the_proof_file_is_issued_and_recorded(client, world, storage, owner_db):
    doc = await _passport(client, world)
    doc = await _verified(client, world["officer_a"], doc["versions"][0]["id"], proof=PDF, filename="reply.pdf")
    verification_id = doc["versions"][0]["verifications"][0]["id"]

    res = await client.post(f"/api/verifications/{verification_id}/proof-url", headers=world["officer_a2"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["filename"] == "reply.pdf"
    assert body["content_type"] == "application/pdf"
    [(path, ttl, download)] = storage.signed
    assert path.startswith("proofs/") and download == "reply.pdf" and ttl == body["expires_in"]

    [record] = await _records(
        owner_db, "file_url_issued", target_type="verification", target_id=str(verification_id)
    )
    assert record["target_type"] == "verification"
    assert record["seafarer_id"] == world["anna"]


async def test_a_verification_without_a_proof_file_has_no_url(client, world, storage):
    doc = await _passport(client, world)
    doc = await _verified(client, world["officer_a"], doc["versions"][0]["id"])
    verification_id = doc["versions"][0]["verifications"][0]["id"]
    res = await client.post(f"/api/verifications/{verification_id}/proof-url", headers=world["officer_a"])
    assert res.status_code == 404
    assert storage.signed == []


# --- 403, 404 and the records ----------------------------------------------------------


async def _endpoints(client, w):
    doc = await _passport(client, w)
    version_id = doc["versions"][0]["id"]
    doc = await _verified(client, w["officer_a"], version_id, proof=PDF)
    verification_id = doc["versions"][0]["verifications"][0]["id"]
    return [
        (f"/api/versions/{version_id}/reviews", {"json": {"decision": "accept", "comment": "ok"}}),
        (f"/api/versions/{version_id}/verifications", {"data": _verification_form()}),
        (f"/api/verifications/{verification_id}/proof-url", {}),
    ]


async def test_managers_get_403_on_every_endpoint_and_it_is_recorded(client, world, owner_db):
    for path, kwargs in await _endpoints(client, world):
        res = await client.post(path, headers=world["manager"], **kwargs)
        assert res.status_code == 403, path
        assert await owner_db.fetchval(
            """
            SELECT count(*) FROM public.audit_log
             WHERE action = 'access_refused' AND actor_id = $1 AND target_id = $2
            """,
            world["ids"]["manager"], f"POST {path}",
        ) == 1, path


async def test_out_of_scope_is_404_on_every_endpoint_and_it_is_recorded(client, world, owner_db, storage):
    endpoints = await _endpoints(client, world)
    # Booked onto Bravo: out of Alpha's officers' Scope.
    res = await client.post(
        "/api/assignments",
        json={
            "seafarer_id": world["anna"], "vessel_id": world["bravo"], "position_id": world["master"],
            "start_date": day(5), "end_date": day(50),
        },
        headers=world["officer_b"],
    )
    assert res.status_code == 201

    for path, kwargs in endpoints:
        res = await client.post(path, headers=world["officer_a2"], **kwargs)
        assert res.status_code == 404, path
        assert res.json() == {"detail": "Not found"}

    refused = await _records(owner_db, "access_refused", seafarer_id=world["anna"], reason="out_of_scope")
    assert len(refused) == 3
    assert await owner_db.fetchval("SELECT count(*) FROM public.review") == 0
    assert await owner_db.fetchval("SELECT count(*) FROM public.verification") == 1
    assert storage.signed == []

    # Bravo's officer may review it.
    res = await _review(client, world["officer_b"], int(endpoints[0][0].split("/")[3]))
    assert res.status_code == 201


@pytest.mark.parametrize(
    "path, kwargs",
    [
        ("/api/versions/999999/reviews", {"json": {"decision": "accept", "comment": "ok"}}),
        ("/api/versions/999999/verifications", {"data": _verification_form()}),
        ("/api/verifications/999999/proof-url", {}),
    ],
)
async def test_a_missing_record_is_a_plain_404(client, world, owner_db, path, kwargs):
    res = await client.post(path, headers=world["admin"], **kwargs)
    assert res.status_code == 404
    assert await owner_db.fetchval(
        "SELECT count(*) FROM public.audit_log WHERE action = 'access_refused' AND actor_id = $1",
        world["ids"]["admin"],
    ) == 0
