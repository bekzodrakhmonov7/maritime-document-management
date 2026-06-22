import pytest
from httpx import AsyncClient
from io import BytesIO

from tests.conftest import make_token


async def _upload_document(client: AsyncClient, token: str, seafarer_id: int, doc_type_id: int):
    response = await client.post(
        "/documents",
        data={
            "doc_type_id": doc_type_id,
            "seafarer_id": seafarer_id,
            "document_number": "DOCVER001",
            "issue_date": "2024-01-01",
            "expiry_date": "2025-01-01",
        },
        files={"file": ("test.pdf", BytesIO(b"%PDF-1.4 fake pdf content"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return response.json()["document_id"]


@pytest.mark.asyncio
async def test_pending_to_verified(client: AsyncClient, test_user, test_seafarer, test_doc_type):
    token = make_token(test_user)
    doc_id = await _upload_document(client, token, test_seafarer, test_doc_type)

    response = await client.patch(
        f"/documents/{doc_id}/verify",
        json={"status": "verified"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "verified"


@pytest.mark.asyncio
async def test_pending_to_rejected(client: AsyncClient, test_user, test_seafarer, test_doc_type):
    token = make_token(test_user)
    doc_id = await _upload_document(client, token, test_seafarer, test_doc_type)

    response = await client.patch(
        f"/documents/{doc_id}/verify",
        json={"status": "rejected"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"


@pytest.mark.asyncio
async def test_verified_to_pending_rejected(client: AsyncClient, test_user, test_seafarer, test_doc_type):
    token = make_token(test_user)
    doc_id = await _upload_document(client, token, test_seafarer, test_doc_type)

    # First verify
    verify_resp = await client.patch(
        f"/documents/{doc_id}/verify",
        json={"status": "verified"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert verify_resp.status_code == 200

    # Then try to revert to pending (should fail with 400)
    response = await client.patch(
        f"/documents/{doc_id}/verify",
        json={"status": "pending"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_signed_url_works(client: AsyncClient, test_user, test_seafarer, test_doc_type):
    token = make_token(test_user)
    doc_id = await _upload_document(client, token, test_seafarer, test_doc_type)

    response = await client.get(
        f"/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["signed_url"] is not None
    assert data["signed_url"].startswith("http")

    # Follow signed URL and ensure it resolves (use plain client, not ASGI transport)
    async with AsyncClient() as plain_client:
        signed_response = await plain_client.get(data["signed_url"])
        assert signed_response.status_code == 200
