"""Every endpoint checks the caller and refuses by default (SR-04, SR-05, SR-07).

The matrix walks every route-method pair of the API, except the health check,
the sign-in proxy before a Session exists (`/api/auth/*` but logout) and the
daily check (its own secret), and calls it as: no token, a forged token, a
manager and a pending Account. A password-only (aal1) Session on the same
routes: `test_session_refusals.py::test_a_password_only_session_is_refused_on_every_protected_endpoint`.

A new endpoint fails `test_the_matrix_lists_every_route` until it gets a row here.
"""

import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest

from app.config import settings
from app.main import create_app
from tests.conftest import auth_header, make_token
from tests.integration.test_documents_api import _uploaded, day
from tests.integration.test_session_refusals import _protected_routes
from tests.integration.test_sign_in_api import PASSWORD, fake_auth  # noqa: F401 (fixture)

ALL_STAFF = "all staff"  # Managers get the answer below; pending Accounts 403.
ANY_ACCOUNT = "any account"  # Pending Accounts get in as well.

# (method, path): what a manager gets. Everything not marked is refused (403).
MATRIX: dict[tuple[str, str], tuple[str, int] | None] = {
    ("POST", "/api/auth/logout"): (ANY_ACCOUNT, 204),
    ("GET", "/api/me"): (ANY_ACCOUNT, 200),
    ("GET", "/api/me/vessels"): (ALL_STAFF, 200),
    ("GET", "/api/accounts"): None,
    ("GET", "/api/accounts/pending-count"): None,
    ("POST", "/api/accounts/{account_id}/approve"): None,
    ("POST", "/api/accounts/{account_id}/role"): None,
    ("POST", "/api/accounts/{account_id}/deactivate"): None,
    ("POST", "/api/accounts/{account_id}/reactivate"): None,
    ("POST", "/api/accounts/{account_id}/second-factor/reset"): None,
    ("GET", "/api/vessels"): None,
    ("POST", "/api/vessels"): None,
    ("GET", "/api/vessels/{vessel_id}"): None,
    ("PUT", "/api/vessels/{vessel_id}"): None,
    ("POST", "/api/vessels/{vessel_id}/deactivate"): None,
    ("POST", "/api/vessels/{vessel_id}/reactivate"): None,
    ("GET", "/api/vessels/{vessel_id}/crew"): None,
    ("GET", "/api/vessels/{vessel_id}/responsible-officers"): None,
    ("POST", "/api/vessels/{vessel_id}/responsible-officers"): None,
    ("DELETE", "/api/vessels/{vessel_id}/responsible-officers/{account_id}"): None,
    ("GET", "/api/positions"): (ALL_STAFF, 200),
    ("POST", "/api/positions"): None,
    ("DELETE", "/api/positions/{row_id}"): None,
    ("PUT", "/api/positions/{row_id}"): None,
    ("POST", "/api/positions/{row_id}/retire"): None,
    ("POST", "/api/positions/{row_id}/unretire"): None,
    ("GET", "/api/document-types"): (ALL_STAFF, 200),
    ("POST", "/api/document-types"): None,
    ("DELETE", "/api/document-types/{row_id}"): None,
    ("PUT", "/api/document-types/{row_id}"): None,
    ("POST", "/api/document-types/{row_id}/retire"): None,
    ("POST", "/api/document-types/{row_id}/unretire"): None,
    ("GET", "/api/requirements"): (ALL_STAFF, 200),
    ("GET", "/api/requirements/evaluate"): (ALL_STAFF, 422),  # No Position given.
    ("DELETE", "/api/requirements/{position_id}/{document_type_id}"): None,
    ("PUT", "/api/requirements/{position_id}/{document_type_id}"): None,
    ("POST", "/api/requirements/add-to-all-positions"): None,
    ("GET", "/api/requirement-exceptions"): (ALL_STAFF, 200),
    ("POST", "/api/requirement-exceptions"): None,
    ("DELETE", "/api/requirement-exceptions/{exception_id}"): None,
    ("PUT", "/api/requirement-exceptions/{exception_id}"): None,
    ("GET", "/api/seafarers"): None,
    ("POST", "/api/seafarers"): None,
    ("GET", "/api/seafarers/{seafarer_id}"): None,
    ("PUT", "/api/seafarers/{seafarer_id}"): None,
    ("POST", "/api/seafarers/{seafarer_id}/set-inactive"): None,
    ("POST", "/api/seafarers/{seafarer_id}/reactivate"): None,
    ("GET", "/api/seafarers/{seafarer_id}/assignments"): None,
    ("GET", "/api/assignments/{assignment_id}"): None,
    ("PUT", "/api/assignments/{assignment_id}"): None,
    ("GET", "/api/assignments/{assignment_id}/readiness"): None,
    ("POST", "/api/assignments"): None,
    ("POST", "/api/assignments/{assignment_id}/cancel"): None,
    ("GET", "/api/seafarers/{seafarer_id}/documents"): None,
    ("POST", "/api/seafarers/{seafarer_id}/documents"): None,
    ("GET", "/api/documents/{document_id}"): None,
    ("POST", "/api/documents/{document_id}/versions"): None,
    ("POST", "/api/versions/{version_id}/file-url"): None,
    ("POST", "/api/versions/{version_id}/reviews"): None,
    ("POST", "/api/versions/{version_id}/verifications"): None,
    ("POST", "/api/verifications/{verification_id}/proof-url"): None,
    ("GET", "/api/settings"): (ALL_STAFF, 200),
    ("PUT", "/api/settings"): None,
    ("GET", "/api/audit"): None,
    ("GET", "/api/audit/export.csv"): None,
    ("GET", "/api/alerts"): None,
    ("GET", "/api/alerts/count"): None,
    ("POST", "/api/admin/daily-check/run"): None,
    ("GET", "/api/dashboard"): None,
    ("GET", "/api/dashboard/totals"): (ALL_STAFF, 200),
    ("GET", "/api/assignments/{assignment_id}/report"): None,
    ("GET", "/api/vessels/{vessel_id}/report"): None,
}
ROUTES = sorted(MATRIX)
MANAGER_ALLOWED = [route for route in ROUTES if MATRIX[route] is not None]


def _matrix_routes(app) -> list[tuple[str, str]]:
    """Every route-method pair behind a Session (the aal1 sweep's list)."""
    return sorted(_protected_routes(app))


def test_the_matrix_lists_every_route():
    found = _matrix_routes(create_app())

    assert len(found) == len(MATRIX) == 72
    assert found == ROUTES


def _url(path: str) -> str:
    """Every parameter filled: a fresh UUID for Accounts, 1 for the integer ids."""
    return re.sub(
        r"\{(\w+)\}", lambda m: str(uuid4()) if m.group(1) == "account_id" else "1", path
    )


async def _records(owner_db, res) -> list[dict]:
    rows = await owner_db.fetch(
        "SELECT * FROM public.audit_log WHERE request_id = $1 ORDER BY id",
        res.headers["x-request-id"],
    )
    return [dict(r) for r in rows]


def _forged(sub) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(sub), "session_id": str(sub), "aud": "authenticated", "aal": "aal2",
        "role": "service_role", "iat": now, "exp": now + timedelta(hours=1),
    }
    return {"Authorization": f"Bearer {jwt.encode(claims, 'not-the-secret-' * 3, 'HS256')}"}


@pytest.mark.parametrize("method, path", ROUTES)
async def test_no_token_is_401_and_writes_nothing(client, owner_db, method, path):
    res = await client.request(method, _url(path))

    assert res.status_code == 401
    assert await _records(owner_db, res) == []


@pytest.mark.parametrize("method, path", ROUTES)
async def test_a_forged_token_is_401_and_recorded(client, owner_db, make_account, method, path):
    # A real administrator's id in a token signed with the wrong key.
    admin = await make_account(role="administrator")

    res = await client.request(method, _url(path), headers=_forged(admin))

    assert res.status_code == 401
    [rec] = await _records(owner_db, res)
    assert rec["action"] == "access_refused"
    assert rec["reason"] == "invalid_session"
    assert rec["actor_id"] is None and rec["actor_role"] is None


@pytest.mark.parametrize("method, path", ROUTES)
async def test_a_manager_gets_only_the_summary_endpoints(
    client, owner_db, make_account, method, path
):
    manager = await make_account(role="manager")

    res = await client.request(method, _url(path), headers=auth_header(manager))

    if MATRIX[(method, path)] is None:
        assert res.status_code == 403, res.text
        [rec] = await _records(owner_db, res)
        assert rec["action"] == "access_refused"
        assert rec["reason"] == "wrong_role"
        assert rec["actor_id"] == manager and rec["actor_role"] == "manager"
        assert rec["target_id"] == f"{method} {res.request.url.path}"
    else:
        assert res.status_code == MATRIX[(method, path)][1], res.text
        assert [r for r in await _records(owner_db, res) if r["outcome"] == "refused"] == []


@pytest.mark.parametrize("method, path", ROUTES)
async def test_a_pending_account_gets_only_its_own_account(
    client, owner_db, make_account, method, path
):
    pending = await make_account(status="pending")

    res = await client.request(method, _url(path), headers=auth_header(pending))

    allowed = MATRIX[(method, path)]
    if allowed is not None and allowed[0] == ANY_ACCOUNT:
        assert res.status_code == allowed[1], res.text
        assert [r for r in await _records(owner_db, res) if r["outcome"] == "refused"] == []
    else:
        assert res.status_code == 403, res.text
        [rec] = await _records(owner_db, res)
        assert rec["action"] == "access_refused"
        assert rec["reason"] == "account_pending"
        assert rec["actor_id"] == pending


# --- SR-04: role and state only from user_account ------------------------------------


async def test_the_role_claim_of_a_token_is_never_trusted(client, owner_db, make_account):
    manager = await make_account(role="manager")
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(manager), "session_id": str(manager), "aud": "authenticated", "aal": "aal2",
        "iat": now, "exp": now + timedelta(hours=1),
        "role": "administrator", "user_role": "administrator",
        "app_metadata": {"role": "administrator"}, "user_metadata": {"role": "administrator"},
    }
    token = jwt.encode(claims, settings.supabase_jwt_secret, "HS256")

    res = await client.get("/api/accounts", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 403
    me = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["role"] == "manager"


async def test_register_cannot_set_a_role_or_status(client, owner_db, fake_auth):
    # Straight to Supabase with `role` in the metadata:
    # test_database_guards.py::test_sign_up_ignores_a_role_in_the_metadata.
    email = f"{uuid4().hex[:12]}@example.com"

    res = await client.post("/api/auth/register", json={
        "email": email, "full_name": "Eve", "password": PASSWORD,
        "role": "administrator", "status": "active",
    })

    assert res.status_code == 200, res.text
    assert fake_auth.called("sign_up") == [("sign_up", email, PASSWORD, "Eve", "127.0.0.1")]
    row = await owner_db.fetchrow("SELECT status, role FROM public.users WHERE email = $1", email)
    assert (row["status"], row["role"]) == ("pending", None)


async def test_a_pending_account_with_an_administrator_token_stays_pending(
    client, make_account
):
    pending = await make_account(status="pending")

    res = await client.get("/api/accounts", headers={
        "Authorization": f"Bearer {make_token(pending)}",
    })

    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "account_pending"


# --- SR-07: managers never see a document number -----------------------------------------


@pytest.fixture
async def fleet(crew, make_account, documents_cleanup, storage, settings_reset, owner_db):
    master = await crew.position("Master")
    alpha = await crew.vessel("Alpha")
    admin = auth_header(await make_account(role="administrator"))
    manager = await make_account(role="manager")
    passport = await owner_db.fetchval(
        "INSERT INTO public.document_type (name, expires) VALUES ('Passport', true) RETURNING id"
    )
    medical = await owner_db.fetchval(
        "INSERT INTO public.document_type (name, expires) VALUES ('Medical', true) RETURNING id"
    )
    await owner_db.execute(
        "INSERT INTO public.position_requirement (position_id, document_type_id) "
        "VALUES ($1, $2), ($1, $3)",
        master, passport, medical,
    )
    anna = await crew.seafarer(master, "Anna")
    await owner_db.execute(
        """
        INSERT INTO public.assignment (seafarer_id, vessel_id, position_id, start_date, end_date)
        VALUES ($1, $2, $3, $4::text::date, $5::text::date)
        """,
        anna, alpha, master, day(-10), day(100),
    )
    return {
        "admin": admin, "manager": manager, "anna": anna, "master": master, "alpha": alpha,
        "passport": passport, "medical": medical, "numbers": ["PSR07-4711", "MED-SR07-0815"],
    }


async def test_no_manager_response_contains_a_document_number(client, fleet):
    for type_id, number in zip((fleet["passport"], fleet["medical"]), fleet["numbers"]):
        await _uploaded(
            client, fleet["admin"], fleet["anna"], type_id,
            document_number=number, issue_date=day(-800), expiry_date=day(10),
        )
    calls = [(m, p) for m, p in MANAGER_ALLOWED if m == "GET"]
    params = {"/api/requirements/evaluate": {"position": fleet["master"], "vessel": fleet["alpha"]}}

    for method, path in calls:
        res = await client.request(
            method, path, params=params.get(path), headers=auth_header(fleet["manager"])
        )
        assert res.status_code == 200, (path, res.text)
        for number in fleet["numbers"]:
            assert number not in res.text, path
    # The numbers are there to find: an administrator sees them.
    docs = await client.get(f"/api/seafarers/{fleet['anna']}/documents", headers=fleet["admin"])
    assert all(number in docs.text for number in fleet["numbers"])
