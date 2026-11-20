"""Malformed requests and forced errors answer in general terms (SR-16).

Out-of-range ids are a 422, not a database error; a 422 does not echo what
was sent; an unexpected error is a generic 500 and is logged with its
traceback and the request id.
"""

import logging
import re

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.supabase_auth import get_supabase_auth
from tests.conftest import auth_header


def _integer_id_routes() -> list[tuple[str, str, str]]:
    """(method, path, id name) for every integer `{..._id}` in the API."""
    found = []
    for path, operations in create_app().openapi()["paths"].items():
        for method, operation in operations.items():
            for param in operation.get("parameters", []):
                if (
                    param["in"] == "path"
                    and param["name"].endswith("_id")
                    and param["schema"].get("type") == "integer"
                ):
                    found.append((method.upper(), path, param["name"]))
    return found


ID_ROUTES = _integer_id_routes()


def test_the_api_has_integer_id_routes():
    assert len(ID_ROUTES) > 30


@pytest.mark.parametrize("value", ["0", "-1", "9223372036854775808", "99999999999999999999999"])
@pytest.mark.parametrize("method, path, name", ID_ROUTES)
async def test_an_out_of_range_id_is_a_422(client, make_account, method, path, name, value):
    admin = await make_account(role="administrator")
    url = re.sub(r"\{(\w+)\}", lambda m: value if m.group(1) == name else "1", path)

    res = await client.request(method, url, headers=auth_header(admin))

    assert res.status_code == 422
    assert any(e["loc"] == ["path", name] for e in res.json()["detail"])


@pytest.mark.parametrize(
    "method, url, name",
    [
        ("GET", "/api/audit?seafarer_id=99999999999999999999999", "seafarer_id"),
        ("POST", "/api/seafarers/1/documents?document_type_id=99999999999999999999999",
         "document_type_id"),
    ],
)
async def test_an_out_of_range_id_in_the_query_is_a_422(client, make_account, method, url, name):
    admin = await make_account(role="administrator")

    res = await client.request(method, url, headers=auth_header(admin))

    assert res.status_code == 422
    assert any(e["loc"] == ["query", name] for e in res.json()["detail"])


async def test_the_largest_id_is_accepted_and_simply_not_found(client, make_account):
    admin = await make_account(role="administrator")

    res = await client.get(f"/api/seafarers/{2**63 - 1}", headers=auth_header(admin))

    assert res.status_code == 404


async def test_a_422_does_not_echo_the_password(app, client):
    app.dependency_overrides[get_supabase_auth] = lambda: object()
    try:
        res = await client.post(
            "/api/auth/register",
            json={"email": "a@example.com", "full_name": "A", "password": "short1"},
        )
    finally:
        app.dependency_overrides.pop(get_supabase_auth, None)

    assert res.status_code == 422
    assert "short1" not in res.text
    [error] = res.json()["detail"]
    assert set(error) == {"loc", "msg", "type"}
    assert error["loc"] == ["body", "password"]


SECRET = "SELECT key FROM vault WHERE token = 'sk-live-123'"


async def test_a_forced_error_answers_generically_and_is_logged(app, caplog):
    async def boom():
        raise RuntimeError(SECRET)

    app.add_api_route("/api/test-only/boom", boom)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        with caplog.at_level(logging.ERROR):
            res = await c.get("/api/test-only/boom", headers={"X-Request-ID": "req-boom-1"})

    assert res.status_code == 500
    assert res.json() == {"detail": "Internal server error", "request_id": "req-boom-1"}
    assert res.headers["x-request-id"] == "req-boom-1"
    assert SECRET not in res.text
    assert "Traceback" in caplog.text
    assert SECRET in caplog.text
    assert "req-boom-1" in caplog.text
