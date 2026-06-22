import pytest
from httpx import AsyncClient
from io import BytesIO

from tests.conftest import make_token


@pytest.mark.asyncio
async def test_upload_pdf_success(client: AsyncClient, test_user, test_seafarer, test_doc_type):
    token = make_token(test_user)
    response = await client.post(
        "/documents",
        data={
            "doc_type_id": test_doc_type,
            "seafarer_id": test_seafarer,
            "document_number": "DOC001",
            "issue_date": "2024-01-01",
            "expiry_date": "2025-01-01",
        },
        files={"file": ("test.pdf", BytesIO(b"%PDF-1.4 fake pdf content"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["document_number"] == "DOC001"
    assert data["status"] == "pending"
    assert data["file_path"] is not None


@pytest.mark.asyncio
async def test_upload_txt_rejected(client: AsyncClient, test_user, test_seafarer, test_doc_type):
    token = make_token(test_user)
    response = await client.post(
        "/documents",
        data={
            "doc_type_id": test_doc_type,
            "seafarer_id": test_seafarer,
            "document_number": "DOC002",
            "issue_date": "2024-01-01",
            "expiry_date": "2025-01-01",
        },
        files={"file": ("test.txt", BytesIO(b"not a pdf"), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_upload_oversize_rejected(client: AsyncClient, test_user, test_seafarer, test_doc_type):
    token = make_token(test_user)
    big_file = BytesIO(b"x" * (11 * 1024 * 1024))
    response = await client.post(
        "/documents",
        data={
            "doc_type_id": test_doc_type,
            "seafarer_id": test_seafarer,
            "document_number": "DOC003",
            "issue_date": "2024-01-01",
            "expiry_date": "2025-01-01",
        },
        files={"file": ("big.pdf", big_file, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_upload_bad_dates_rejected(client: AsyncClient, test_user, test_seafarer, test_doc_type):
    token = make_token(test_user)
    response = await client.post(
        "/documents",
        data={
            "doc_type_id": test_doc_type,
            "seafarer_id": test_seafarer,
            "document_number": "DOC004",
            "issue_date": "2025-01-01",
            "expiry_date": "2024-01-01",
        },
        files={"file": ("test.pdf", BytesIO(b"%PDF-1.4"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
