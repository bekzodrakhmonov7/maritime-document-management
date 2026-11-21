"""Text containing a NUL byte is refused with the usual 422, never a 500 (F-02).

PostgreSQL cannot store `\\x00` in text, so before this every such field
reached the database and failed there. Nothing here writes rows: each request
is refused at validation, so no reference data is needed.
"""

import pytest

from tests.conftest import auth_header

NUL = "a\x00b"

# (method, path, query, json body, field the 422 names). The first four are
# the routes found in C12.
CASES = [
    ("GET", "/api/seafarers", {"search": NUL}, None, "search"),
    ("GET", "/api/audit", {"actor_email": NUL}, None, "actor_email"),
    ("POST", "/api/vessels", None, {"name": NUL, "imo_number": "1234567", "flag": "MT"}, "name"),
    (
        "POST",
        "/api/seafarers",
        None,
        {"first_name": NUL, "last_name": "Petrova", "position_id": 1},
        "first_name",
    ),
    # A sample of the other text fields and query parameters.
    ("GET", "/api/dashboard", {"name": NUL}, None, "name"),
    ("GET", "/api/audit", {"target_type": NUL}, None, "target_type"),
    ("GET", "/api/audit/export.csv", {"target_id": NUL}, None, "target_id"),
    ("POST", "/api/positions", None, {"name": NUL}, "name"),
    ("PUT", "/api/seafarers/1", None, {"first_name": "Anna", "last_name": NUL, "position_id": 1}, "last_name"),
    ("POST", "/api/seafarers/1/set-inactive", None, {"reason": NUL}, "reason"),
    ("POST", "/api/assignments/1/cancel", None, {"reason": NUL}, "reason"),
    ("POST", "/api/auth/login", None, {"email": NUL, "password": "x"}, "email"),
    ("POST", "/api/auth/login", None, {"email": "a@example.com", "password": NUL}, "password"),
    (
        "POST",
        "/api/auth/register",
        None,
        {"email": "a@example.com", "full_name": NUL, "password": "a long enough password"},
        "full_name",
    ),
]


@pytest.mark.parametrize(
    ("method", "path", "query", "body", "field"),
    CASES,
    ids=[f"{c[0]} {c[1]} {c[4]}" for c in CASES],
)
async def test_nul_byte_is_refused_with_422_naming_the_field(
    client, make_account, method, path, query, body, field
):
    headers = auth_header(await make_account(role="administrator"))
    response = await client.request(method, path, params=query, json=body, headers=headers)

    assert response.status_code == 422, response.text
    [error] = response.json()["detail"]
    assert error["loc"][-1] == field
    assert "NUL" in error["msg"]
