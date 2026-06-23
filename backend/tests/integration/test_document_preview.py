import pytest
from httpx import AsyncClient
from io import BytesIO

from tests.conftest import make_token


PDF_BYTES = b"%PDF-1.4 fake pdf content for preview test"


async def _upload_document(
    client: AsyncClient, token: str, seafarer_id: int, doc_type_id: int
) -> int:
    response = await client.post(
        "/documents",
        data={
            "doc_type_id": doc_type_id,
            "seafarer_id": seafarer_id,
            "document_number": "DOCPREV001",
            "issue_date": "2024-01-01",
            "expiry_date": "2025-01-01",
        },
        files={"file": ("test.pdf", BytesIO(PDF_BYTES), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return response.json()["document_id"]


@pytest.mark.asyncio
async def test_preview_pdf_returns_inline_bytes(
    client: AsyncClient, test_user, test_seafarer, test_doc_type
):
    token = make_token(test_user)
    doc_id = await _upload_document(client, token, test_seafarer, test_doc_type)

    response = await client.get(
        f"/documents/{doc_id}/preview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert "inline" in response.headers["content-disposition"].lower()
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content == PDF_BYTES


@pytest.mark.asyncio
async def test_preview_requires_auth(
    client: AsyncClient, test_user, test_seafarer, test_doc_type
):
    token = make_token(test_user)
    doc_id = await _upload_document(client, token, test_seafarer, test_doc_type)

    response = await client.get(f"/documents/{doc_id}/preview")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_preview_forbidden_for_wrong_role(
    client: AsyncClient,
    test_user,
    test_seafarer,
    test_doc_type,
    no_role_token: str,
):
    admin_token = make_token(test_user)
    doc_id = await _upload_document(client, admin_token, test_seafarer, test_doc_type)

    response = await client.get(
        f"/documents/{doc_id}/preview",
        headers={"Authorization": f"Bearer {no_role_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_preview_allowed_for_crewing_officer(
    client: AsyncClient,
    test_user,
    test_seafarer,
    test_doc_type,
    crewing_officer_token: str,
):
    admin_token = make_token(test_user)
    doc_id = await _upload_document(client, admin_token, test_seafarer, test_doc_type)

    response = await client.get(
        f"/documents/{doc_id}/preview",
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    assert response.status_code == 200
    assert response.content == PDF_BYTES


@pytest.mark.asyncio
async def test_preview_not_found(client: AsyncClient, test_user):
    token = make_token(test_user)
    response = await client.get(
        "/documents/999999/preview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_verify_forbidden_for_wrong_role(
    client: AsyncClient,
    test_user,
    test_seafarer,
    test_doc_type,
    no_role_token: str,
):
    admin_token = make_token(test_user)
    doc_id = await _upload_document(client, admin_token, test_seafarer, test_doc_type)

    response = await client.patch(
        f"/documents/{doc_id}/verify",
        json={"status": "verified"},
        headers={"Authorization": f"Bearer {no_role_token}"},
    )
    assert response.status_code == 403
