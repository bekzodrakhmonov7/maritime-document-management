"""Documents, Versions and Safety Checks through the HTTP API (FR-09, FR-10, FR-13,
FR-15; T1, T2, T5, T7, T8).

The app runs as app_backend against the real database; the private bucket is
an in-memory stand-in (the `storage` fixture), since the Storage API isn't
available in tests.
"""

import io
from datetime import timedelta

import asyncpg
import pikepdf
import pytest
from PIL import Image

from app.domain import today_in
from tests.conftest import auth_header

TODAY = today_in("UTC")


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def _pdf(pages: int = 1) -> bytes:
    pdf = pikepdf.new()
    for _ in range(pages):
        pdf.add_blank_page()
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (30, 20), (0, 90, 160)).save(buf, format="JPEG")
    return buf.getvalue() + b"TRAILER"


PDF = _pdf()


@pytest.fixture
async def world(crew, make_account, documents_cleanup, storage, owner_db):
    master = await crew.position("Master")
    alpha = await crew.vessel("Alpha")
    bravo = await crew.vessel("Bravo")
    officer_a = await make_account(role="crewing_officer", full_name="Olena Officer")
    officer_b = await make_account(role="crewing_officer")
    manager = await make_account(role="manager")
    admin = await make_account(role="administrator")
    await crew.link(officer_a, alpha)
    await crew.link(officer_b, bravo)

    async def doc_type(name: str, expires: bool = True, max_months: int | None = None, retired=False):
        return await owner_db.fetchval(
            """
            INSERT INTO public.document_type (name, expires, max_validity_months, retired)
            VALUES ($1, $2, $3, $4) RETURNING id
            """,
            name, expires, max_months, retired,
        )

    return {
        "ids": {"officer_a": officer_a, "manager": manager, "admin": admin},
        "master": master,
        "alpha": alpha,
        "bravo": bravo,
        "anna": await crew.seafarer(master, "Anna"),
        "passport": await doc_type("Passport", max_months=120),
        "medical": await doc_type("Medical"),
        "course": await doc_type("Safety course", expires=False),
        "old": await doc_type("Old licence", retired=True),
        "admin": auth_header(admin),
        "manager": auth_header(manager),
        "officer_a": auth_header(officer_a),
        "officer_b": auth_header(officer_b),
    }


def _details(**fields) -> dict:
    return {
        "document_number": "P-100",
        "issuing_authority": "Ministry",
        "issue_date": day(-365),
        "expiry_date": day(365),
        **fields,
    }


async def _upload(client, headers, seafarer_id, type_id, *, data=PDF, filename="passport.pdf", **fields):
    form = {k: v for k, v in _details(**fields).items() if v is not None}
    return await client.post(
        f"/api/seafarers/{seafarer_id}/documents",
        params={"document_type_id": type_id},
        data=form,
        files={"file": (filename, data, "application/octet-stream")},
        headers=headers,
    )


async def _uploaded(client, headers, seafarer_id, type_id, **kw) -> dict:
    res = await _upload(client, headers, seafarer_id, type_id, **kw)
    assert res.status_code == 201, res.text
    return res.json()


async def _records(owner_db, action: str, **where) -> list[dict]:
    conditions = ["action = $1"] + [f"{k} = ${i}" for i, k in enumerate(where, start=2)]
    rows = await owner_db.fetch(
        f"SELECT * FROM public.audit_log WHERE {' AND '.join(conditions)} ORDER BY id",
        action, *where.values(),
    )
    return [dict(r) for r in rows]


# --- Upload ------------------------------------------------------------------------------


async def test_an_officer_uploads_a_pdf_which_is_stored_cleaned(client, world, storage, owner_db):
    doc = await _uploaded(client, world["officer_a"], world["anna"], world["passport"])

    assert doc["document_type_name"] == "Passport"
    assert doc["version_count"] == 1
    assert doc["expiry_status"] == "unexpired"
    [version] = doc["versions"]
    assert version["is_current"] is True
    assert version["original_filename"] == "passport.pdf"
    assert version["content_type"] == "application/pdf"
    assert version["uploaded_by_name"] == "Olena Officer"

    path = await owner_db.fetchval("SELECT file_path FROM public.version WHERE id = $1", version["id"])
    assert path.endswith(".pdf") and "passport" not in path
    content, content_type = storage.objects[path]
    assert content_type == "application/pdf"
    assert len(pikepdf.open(io.BytesIO(content)).pages) == 1

    [record] = await _records(owner_db, "version_uploaded", target_id=str(version["id"]))
    assert record["target_type"] == "version"
    assert record["seafarer_id"] == world["anna"]
    assert record["outcome"] == "succeeded"
    assert '"document_number": "P-100"' in record["after"]


async def test_a_jpeg_is_stored_re_encoded_with_the_detected_type(client, world, storage, owner_db):
    doc = await _uploaded(
        client, world["officer_a"], world["anna"], world["medical"], data=_jpeg(), filename="scan"
    )
    [version] = doc["versions"]
    assert version["content_type"] == "image/jpeg"
    assert version["original_filename"] == "scan"
    path = await owner_db.fetchval("SELECT file_path FROM public.version WHERE id = $1", version["id"])
    content, content_type = storage.objects[path]
    assert path.endswith(".jpg") and content_type == "image/jpeg"
    assert b"TRAILER" not in content


async def test_a_renewal_is_a_new_version_of_the_same_document(client, world, owner_db):
    first = await _uploaded(client, world["officer_a"], world["anna"], world["passport"])
    renewed = await _uploaded(
        client, world["officer_a"], world["anna"], world["passport"],
        document_number="P-200", issue_date=day(-1), expiry_date=day(3000),
    )
    assert renewed["id"] == first["id"]
    assert [v["number"] for v in renewed["versions"]] == [2, 1]
    assert [v["is_current"] for v in renewed["versions"]] == [True, False]
    assert renewed["current_version"]["document_number"] == "P-200"
    assert await owner_db.fetchval("SELECT count(*) FROM public.document") == 1


async def test_a_details_only_version_reuses_the_stored_file(client, world, storage, owner_db):
    doc = await _uploaded(client, world["officer_a"], world["anna"], world["passport"])
    res = await client.post(
        f"/api/documents/{doc['id']}/versions",
        json=_details(document_number="P-101"),
        headers=world["officer_a"],
    )
    assert res.status_code == 201, res.text
    corrected = res.json()
    newest, oldest = corrected["versions"]
    assert newest["document_number"] == "P-101" and newest["is_current"]
    assert newest["file_from_version_number"] == 1
    assert newest["original_filename"] == oldest["original_filename"]

    paths = await owner_db.fetch("SELECT DISTINCT file_path FROM public.version")
    assert len(paths) == 1 and len(storage.objects) == 1

    [record] = await _records(owner_db, "version_uploaded", target_id=str(newest["id"]))
    assert f'"file_from_version_id": {oldest["id"]}' in record["after"]


async def test_a_details_only_version_must_change_something(client, world):
    doc = await _uploaded(client, world["officer_a"], world["anna"], world["passport"])
    res = await client.post(
        f"/api/documents/{doc['id']}/versions", json=_details(), headers=world["officer_a"]
    )
    assert res.status_code == 409


async def test_the_seafarer_documents_table_shows_each_current_document(client, world):
    await _uploaded(client, world["officer_a"], world["anna"], world["passport"], expiry_date=day(10))
    await _uploaded(client, world["officer_a"], world["anna"], world["course"], expiry_date=None)
    res = await client.get(f"/api/seafarers/{world['anna']}/documents", headers=world["officer_a"])
    assert res.status_code == 200
    rows = {d["document_type_name"]: d for d in res.json()}
    assert rows["Passport"]["expiry_status"] == "expiring_soon"
    assert rows["Passport"]["current_version"]["expiry_date"] == day(10)
    assert rows["Safety course"]["expiry_status"] == "no_expiry_date"


async def test_an_expiring_type_takes_no_date_only_with_the_expiry_not_stated_tick(
    client, world, owner_db
):
    res = await _upload(client, world["officer_a"], world["anna"], world["passport"], expiry_date=None)
    assert res.status_code == 422
    assert "Expiry not stated on the document" in res.text

    doc = await _uploaded(
        client, world["officer_a"], world["anna"], world["passport"],
        expiry_date=None, expiry_not_stated="true",
    )
    assert doc["expiry_status"] == "expiry_not_stated"
    assert doc["versions"][0]["expiry_date"] is None
    # The tick only guards the form: nothing about it is stored (ADR-0006).
    assert "expiry_not_stated" not in doc["versions"][0]
    [record] = await _records(owner_db, "version_uploaded", seafarer_id=world["anna"])
    assert "expiry_not_stated" not in record["after"]


async def test_the_tick_with_a_date_or_on_a_type_that_doesnt_expire_is_refused(client, world):
    res = await _upload(
        client, world["officer_a"], world["anna"], world["passport"], expiry_not_stated="true"
    )
    assert res.status_code == 422
    res = await _upload(
        client, world["officer_a"], world["anna"], world["course"],
        expiry_date=None, expiry_not_stated="true",
    )
    assert res.status_code == 422


async def test_switching_a_type_to_expires_flags_its_undated_documents_and_back(
    client, world, owner_db
):
    doc = await _uploaded(client, world["officer_a"], world["anna"], world["course"], expiry_date=None)
    assert doc["expiry_status"] == "no_expiry_date"

    await owner_db.execute("UPDATE public.document_type SET expires = true WHERE id = $1", world["course"])
    res = await client.get(f"/api/documents/{doc['id']}", headers=world["officer_a"])
    assert res.json()["expiry_status"] == "expiry_not_stated"

    await owner_db.execute("UPDATE public.document_type SET expires = false WHERE id = $1", world["course"])
    res = await client.get(f"/api/seafarers/{world['anna']}/documents", headers=world["officer_a"])
    assert res.json()[0]["expiry_status"] == "no_expiry_date"


async def test_expiry_status_follows_the_largest_alert_step_on_the_next_request(
    client, world, owner_db, settings_reset
):
    doc = await _uploaded(client, world["officer_a"], world["anna"], world["passport"], expiry_date=day(60))
    assert doc["expiry_status"] == "expiring_soon"  # default steps 90/60/30/0

    await owner_db.execute("UPDATE public.settings SET alert_steps = '{30,0}'")
    res = await client.get(f"/api/documents/{doc['id']}", headers=world["officer_a"])
    assert res.json()["expiry_status"] == "unexpired"

    await owner_db.execute("UPDATE public.settings SET alert_steps = '{60,0}'")
    res = await client.get(f"/api/seafarers/{world['anna']}/documents", headers=world["officer_a"])
    assert res.json()[0]["expiry_status"] == "expiring_soon"


async def test_expired_from_the_day_after_the_expiry_date(client, world):
    doc = await _uploaded(
        client, world["officer_a"], world["anna"], world["passport"],
        issue_date=day(-400), expiry_date=day(-1),
    )
    assert doc["expiry_status"] == "expired"


# --- Refused details ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "type_key, fields, status",
    [
        ("passport", {"expiry_date": None}, 422),  # expiring type needs one
        ("course", {}, 422),  # non-expiring type takes none
        ("passport", {"issue_date": day(-10), "expiry_date": day(-10 + 3653 + 2)}, 422),  # > 120 months
        ("medical", {"issue_date": day(0), "expiry_date": day(0)}, 422),  # expiry <= issue
        ("old", {}, 422),  # retired type
    ],
)
async def test_details_breaking_the_type_rules_are_refused(client, world, storage, owner_db, type_key, fields, status):
    res = await _upload(client, world["officer_a"], world["anna"], world[type_key], **fields)
    assert res.status_code == status, res.text
    assert storage.objects == {}
    assert await owner_db.fetchval("SELECT count(*) FROM public.document") == 0


async def test_the_same_rules_apply_to_a_details_only_version(client, world):
    doc = await _uploaded(client, world["officer_a"], world["anna"], world["passport"])
    res = await client.post(
        f"/api/documents/{doc['id']}/versions",
        json=_details(expiry_date=None),
        headers=world["officer_a"],
    )
    assert res.status_code == 422


async def test_an_inactive_seafarer_gets_no_new_version(client, world, storage, owner_db):
    doc = await _uploaded(client, world["officer_a"], world["anna"], world["passport"])
    await owner_db.execute(
        "UPDATE public.seafarer SET inactive_since = now(), inactive_reason = 'Left' WHERE id = $1",
        world["anna"],
    )
    res = await _upload(client, world["officer_a"], world["anna"], world["medical"])
    assert res.status_code == 409
    res = await client.post(
        f"/api/documents/{doc['id']}/versions", json=_details(document_number="X"), headers=world["officer_a"]
    )
    assert res.status_code == 409
    assert len(storage.objects) == 1


async def test_an_unknown_document_type_is_refused(client, world):
    res = await _upload(client, world["officer_a"], world["anna"], 999999)
    assert res.status_code == 422


# --- Safety Checks -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "data, filename, status, code",
    [
        (b"GIF89a not accepted", "photo.gif", 415, "unsupported_type"),
        (PDF, "photo.png", 415, "type_mismatch"),
        (b"%PDF-1.7 broken", "cert.pdf", 422, "corrupt"),
        (_pdf(51), "big.pdf", 422, "too_many_pages"),
    ],
)
async def test_a_failed_safety_check_is_refused_and_recorded(
    client, world, storage, owner_db, data, filename, status, code
):
    res = await _upload(client, world["officer_a"], world["anna"], world["passport"], data=data, filename=filename)
    assert res.status_code == status
    detail = res.json()["detail"]
    assert detail["code"] == code
    assert detail["message"].endswith(".")

    [record] = await _records(owner_db, "upload_rejected", seafarer_id=world["anna"])
    assert record["outcome"] == "refused"
    assert record["reason"] == code
    assert record["actor_id"] == world["ids"]["officer_a"]
    assert f'"document_type_id": {world["passport"]}' in record["after"]
    assert f'"size_bytes": {len(data)}' in record["after"]
    assert f'"filename": "{filename}"' in record["after"]
    assert storage.objects == {}
    assert await owner_db.fetchval("SELECT count(*) FROM public.document") == 0


async def test_a_file_over_the_size_setting_is_413(client, world, storage, owner_db, settings_reset):
    await owner_db.execute("UPDATE public.settings SET max_file_size_mb = 1")
    data = b"%PDF-" + b"0" * (1024 * 1024)
    res = await _upload(client, world["officer_a"], world["anna"], world["passport"], data=data)
    assert res.status_code == 413
    assert res.json()["detail"]["code"] == "too_large"
    [record] = await _records(owner_db, "upload_rejected", seafarer_id=world["anna"])
    assert record["reason"] == "too_large"
    assert storage.objects == {}


async def test_a_body_far_over_the_limit_is_refused_from_its_content_length(
    client, world, storage, owner_db, settings_reset
):
    await owner_db.execute("UPDATE public.settings SET max_file_size_mb = 1")
    res = await _upload(
        client, world["officer_a"], world["anna"], world["passport"], data=b"0" * (3 * 1024 * 1024)
    )
    assert res.status_code == 413
    [record] = await _records(owner_db, "upload_rejected", seafarer_id=world["anna"])
    assert record["reason"] == "too_large"


async def test_a_failed_database_transaction_deletes_the_stored_file(client, world, storage, owner_db):
    await owner_db.execute(
        """
        CREATE FUNCTION pg_temp.fail() RETURNS trigger LANGUAGE plpgsql
        AS $$ BEGIN RAISE EXCEPTION 'simulated failure'; END; $$;
        CREATE TRIGGER test_fail_version_insert BEFORE INSERT ON public.version
            FOR EACH ROW EXECUTE FUNCTION pg_temp.fail();
        """
    )
    try:
        with pytest.raises(asyncpg.RaiseError):
            await _upload(client, world["officer_a"], world["anna"], world["passport"])
    finally:
        await owner_db.execute("DROP TRIGGER test_fail_version_insert ON public.version")
    assert storage.objects == {}
    assert await owner_db.fetchval("SELECT count(*) FROM public.document") == 0
    assert await _records(owner_db, "version_uploaded", seafarer_id=world["anna"]) == []


# --- Files -------------------------------------------------------------------------------


async def test_a_signed_url_is_issued_per_version_and_recorded(client, world, storage, owner_db):
    doc = await _uploaded(client, world["officer_a"], world["anna"], world["passport"], filename="Pass port.PDF")
    version_id = doc["versions"][0]["id"]
    res = await client.post(f"/api/versions/{version_id}/file-url", headers=world["officer_a"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["url"].startswith("https://storage.test/")
    assert body["filename"] == "Pass port.PDF"
    assert body["content_type"] == "application/pdf"
    assert 0 < body["expires_in"] <= 300
    [(path, ttl, download)] = storage.signed
    assert download == "Pass port.PDF" and ttl == body["expires_in"]

    [record] = await _records(owner_db, "file_url_issued", target_id=str(version_id))
    assert record["target_type"] == "version"
    assert record["seafarer_id"] == world["anna"]


async def test_the_download_name_gets_the_detected_extension_when_it_has_none(client, world, storage):
    doc = await _uploaded(client, world["officer_a"], world["anna"], world["medical"], data=_jpeg(), filename="scan")
    res = await client.post(f"/api/versions/{doc['versions'][0]['id']}/file-url", headers=world["officer_a"])
    assert res.json()["filename"] == "scan.jpg"


# --- Immutability ----------------------------------------------------------------------


async def test_versions_cannot_be_updated_or_deleted(client, world, owner_db):
    doc = await _uploaded(client, world["officer_a"], world["anna"], world["passport"])
    version_id = doc["versions"][0]["id"]
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await owner_db.execute("UPDATE public.version SET document_number = 'X' WHERE id = $1", version_id)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await owner_db.execute("DELETE FROM public.version WHERE id = $1", version_id)

    app_conn = await asyncpg.connect(__import__("os").environ["DATABASE_URL"])
    try:
        for statement in (
            "UPDATE public.version SET document_number = 'X'",
            "DELETE FROM public.version",
            "DELETE FROM public.document",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await app_conn.execute(statement)
    finally:
        await app_conn.close()


async def test_one_document_per_seafarer_and_type(world, owner_db):
    await owner_db.execute(
        "INSERT INTO public.document (seafarer_id, document_type_id) VALUES ($1, $2)",
        world["anna"], world["passport"],
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await owner_db.execute(
            "INSERT INTO public.document (seafarer_id, document_type_id) VALUES ($1, $2)",
            world["anna"], world["passport"],
        )


# --- 403, 404 and the records ----------------------------------------------------------


def _endpoints(w, doc_id: int, version_id: int):
    sid = w["anna"]
    return [
        ("GET", f"/api/seafarers/{sid}/documents", {}),
        ("POST", f"/api/seafarers/{sid}/documents", "upload"),
        ("GET", f"/api/documents/{doc_id}", {}),
        ("POST", f"/api/documents/{doc_id}/versions", {"json": _details(document_number="Z")}),
        ("POST", f"/api/versions/{version_id}/file-url", {}),
    ]


async def _call(client, w, method, path, kwargs, headers):
    if kwargs == "upload":
        return await client.post(
            path,
            params={"document_type_id": w["medical"]},
            data=_details(),
            files={"file": ("m.pdf", PDF, "application/pdf")},
            headers=headers,
        )
    return await client.request(method, path, headers=headers, **kwargs)


async def test_managers_get_403_on_every_endpoint_and_it_is_recorded(client, world, owner_db):
    doc = await _uploaded(client, world["officer_a"], world["anna"], world["passport"])
    for method, path, kwargs in _endpoints(world, doc["id"], doc["versions"][0]["id"]):
        res = await _call(client, world, method, path, kwargs, world["manager"])
        assert res.status_code == 403, path
        assert await owner_db.fetchval(
            """
            SELECT count(*) FROM public.audit_log
             WHERE action = 'access_refused' AND actor_id = $1 AND target_id = $2
            """,
            world["ids"]["manager"], f"{method} {path}",
        ) == 1, path


async def test_out_of_scope_is_404_on_every_endpoint_and_it_is_recorded(client, world, owner_db, storage):
    doc = await _uploaded(client, world["officer_a"], world["anna"], world["passport"])
    # Booked onto Bravo: out of Alpha's officer's Scope.
    res = await client.post(
        "/api/assignments",
        json={
            "seafarer_id": world["anna"], "vessel_id": world["bravo"], "position_id": world["master"],
            "start_date": day(5), "end_date": day(50),
        },
        headers=world["officer_b"],
    )
    assert res.status_code == 201
    stored = dict(storage.objects)

    for method, path, kwargs in _endpoints(world, doc["id"], doc["versions"][0]["id"]):
        res = await _call(client, world, method, path, kwargs, world["officer_a"])
        assert res.status_code == 404, path
        assert res.json() == {"detail": "Not found"}

    refused = await _records(owner_db, "access_refused", seafarer_id=world["anna"], reason="out_of_scope")
    assert len(refused) == 5
    assert storage.objects == stored and storage.signed == []

    # Bravo's officer sees the whole record.
    res = await client.get(f"/api/documents/{doc['id']}", headers=world["officer_b"])
    assert res.status_code == 200


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/api/seafarers/999999/documents"),
        ("GET", "/api/documents/999999"),
        ("POST", "/api/documents/999999/versions"),
        ("POST", "/api/versions/999999/file-url"),
    ],
)
async def test_a_missing_record_is_a_plain_404(client, world, owner_db, method, path):
    kwargs = {"json": _details()} if path.endswith("/versions") else {}
    res = await client.request(method, path, headers=world["admin"], **kwargs)
    assert res.status_code == 404
    assert await owner_db.fetchval(
        "SELECT count(*) FROM public.audit_log WHERE action = 'access_refused' AND actor_id = $1",
        world["ids"]["admin"],
    ) == 0


async def test_administrators_see_and_act_on_everyone(client, world):
    doc = await _uploaded(client, world["admin"], world["anna"], world["passport"])
    res = await client.post(f"/api/versions/{doc['versions'][0]['id']}/file-url", headers=world["admin"])
    assert res.status_code == 200


async def test_a_chunked_body_without_a_length_is_cut_off_at_the_limit(
    client, world, storage, owner_db, settings_reset
):
    await owner_db.execute("UPDATE public.settings SET max_file_size_mb = 1")
    boundary = "b0undary"
    head = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"x.pdf\"\r\n"
        "Content-Type: application/pdf\r\n\r\n%PDF-"
    ).encode()
    sent = []

    async def body():
        yield head
        for _ in range(40):  # 40 x 128 KiB = 5 MiB, never all sent
            sent.append(1)
            yield b"0" * (128 * 1024)

    res = await client.post(
        f"/api/seafarers/{world['anna']}/documents",
        params={"document_type_id": world["passport"]},
        content=body(),
        headers={**world["officer_a"], "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert res.status_code == 413
    assert len(sent) < 40
    [record] = await _records(owner_db, "upload_rejected", seafarer_id=world["anna"])
    assert record["reason"] == "too_large"
    assert storage.objects == {}


async def test_a_document_type_in_use_cannot_be_deleted(client, world):
    await _uploaded(client, world["officer_a"], world["anna"], world["medical"])
    res = await client.delete(f"/api/document-types/{world['medical']}", headers=world["admin"])
    assert res.status_code == 409
