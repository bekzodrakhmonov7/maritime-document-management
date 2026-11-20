"""Each refusal is an Audit Record with all its fields (SR-13).

Time, source address, user (where known), action, record and outcome for a
failed login, refused access and a rejected upload.
"""

from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header
from tests.integration.test_documents_api import _upload, world  # noqa: F401 (fixture)
from tests.integration.test_sign_in_api import (  # noqa: F401 (fixture)
    _unique_email,
    fake_auth,
    officer,
)


async def _record(owner_db, res) -> dict:
    [rec] = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE request_id = $1", res.headers["x-request-id"]
    )
    return dict(rec)


def _assert_time_and_address(rec) -> None:
    now = datetime.now(timezone.utc)
    assert now - timedelta(minutes=1) < rec["occurred_at"] <= now
    assert str(rec["ip"]) == "127.0.0.1"
    assert rec["outcome"] == "refused"


async def test_a_failed_login_names_the_account_its_address_and_the_reason(
    client, owner_db, officer
):
    email, user_id = officer

    res = await client.post("/api/auth/login", json={"email": email, "password": "not-it-1234"})

    assert res.status_code == 400
    rec = await _record(owner_db, res)
    _assert_time_and_address(rec)
    assert rec["action"] == "login_failed"
    assert (rec["actor_id"], rec["actor_email"], rec["actor_role"]) == (
        user_id, email, "crewing_officer",
    )
    assert (rec["target_type"], rec["target_id"]) == ("account", str(user_id))
    assert rec["reason"] == "invalid_credentials"


async def test_a_failed_login_for_an_unknown_email_keeps_the_typed_email(
    client, owner_db, fake_auth
):
    email = _unique_email()

    res = await client.post("/api/auth/login", json={"email": email, "password": "not-it-1234"})

    rec = await _record(owner_db, res)
    _assert_time_and_address(rec)
    assert rec["action"] == "login_failed"
    assert (rec["actor_id"], rec["actor_email"]) == (None, email)


async def test_refused_access_names_the_account_and_the_request(client, owner_db, make_account):
    manager = await make_account(role="manager")
    email = await owner_db.fetchval("SELECT email FROM public.users WHERE id = $1", manager)

    res = await client.get("/api/accounts", headers=auth_header(manager))

    assert res.status_code == 403
    rec = await _record(owner_db, res)
    _assert_time_and_address(rec)
    assert rec["action"] == "access_refused"
    assert (rec["actor_id"], rec["actor_email"], rec["actor_role"]) == (manager, email, "manager")
    assert (rec["target_type"], rec["target_id"]) == ("request", "GET /api/accounts")
    assert rec["reason"] == "wrong_role"


async def test_a_rejected_upload_names_the_uploader_the_seafarer_and_the_type(
    client, owner_db, world, storage
):
    res = await _upload(
        client, world["officer_a"], world["anna"], world["passport"],
        data=b"MZ not a pdf", filename="cert.pdf",
    )

    assert res.status_code == 415
    rec = await _record(owner_db, res)
    _assert_time_and_address(rec)
    assert rec["action"] == "upload_rejected"
    officer_id = world["ids"]["officer_a"]
    email = await owner_db.fetchval("SELECT email FROM public.users WHERE id = $1", officer_id)
    assert (rec["actor_id"], rec["actor_email"], rec["actor_role"]) == (
        officer_id, email, "crewing_officer",
    )
    assert (rec["target_type"], rec["target_id"]) == ("document_type", str(world["passport"]))
    assert rec["seafarer_id"] == world["anna"]
    assert rec["reason"] == res.json()["detail"]["code"]
