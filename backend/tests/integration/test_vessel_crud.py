import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_vessels(async_client: AsyncClient, admin_token: str) -> None:
    response = await async_client.get(
        "/vessels", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2  # seeded vessels


@pytest.mark.asyncio
async def test_create_and_get_vessel(async_client: AsyncClient, admin_token: str) -> None:
    # Use a unique IMO based on timestamp
    import time
    imo = f"{int(time.time() * 1000) % 10000000:07d}"

    create_resp = await async_client.post(
        "/vessels",
        json={"vessel_name": "Test Vessel", "imo_number": imo},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_resp.status_code == 201
    vessel = create_resp.json()
    assert vessel["vessel_name"] == "Test Vessel"
    assert vessel["imo_number"] == imo
    vessel_id = vessel["vessel_id"]

    get_resp = await async_client.get(
        f"/vessels/{vessel_id}", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["imo_number"] == imo

    # Cleanup
    await async_client.delete(
        f"/vessels/{vessel_id}", headers={"Authorization": f"Bearer {admin_token}"}
    )


@pytest.mark.asyncio
async def test_update_vessel(async_client: AsyncClient, admin_token: str) -> None:
    import time
    imo = f"{int(time.time() * 1000) % 10000000:07d}"

    create_resp = await async_client.post(
        "/vessels",
        json={"vessel_name": "Old Name", "imo_number": imo},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    vessel_id = create_resp.json()["vessel_id"]

    patch_resp = await async_client.patch(
        f"/vessels/{vessel_id}",
        json={"vessel_name": "New Name"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["vessel_name"] == "New Name"

    # Cleanup
    await async_client.delete(
        f"/vessels/{vessel_id}", headers={"Authorization": f"Bearer {admin_token}"}
    )


@pytest.mark.asyncio
async def test_delete_vessel(async_client: AsyncClient, admin_token: str) -> None:
    import time
    imo = f"{int(time.time() * 1000) % 10000000:07d}"

    create_resp = await async_client.post(
        "/vessels",
        json={"vessel_name": "To Delete", "imo_number": imo},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    vessel_id = create_resp.json()["vessel_id"]

    del_resp = await async_client.delete(
        f"/vessels/{vessel_id}", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert del_resp.status_code == 204

    get_resp = await async_client.get(
        f"/vessels/{vessel_id}", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_create_duplicate_imo_returns_409(
    async_client: AsyncClient, admin_token: str
) -> None:
    import time
    imo = f"{int(time.time() * 1000) % 10000000:07d}"

    resp1 = await async_client.post(
        "/vessels",
        json={"vessel_name": "First", "imo_number": imo},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp1.status_code == 201
    vessel_id = resp1.json()["vessel_id"]

    resp2 = await async_client.post(
        "/vessels",
        json={"vessel_name": "Second", "imo_number": imo},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp2.status_code == 409

    # Cleanup
    await async_client.delete(
        f"/vessels/{vessel_id}", headers={"Authorization": f"Bearer {admin_token}"}
    )


@pytest.mark.asyncio
async def test_delete_vessel_with_seafarers_returns_409(
    async_client: AsyncClient, admin_token: str
) -> None:
    import time
    imo = f"{int(time.time() * 1000) % 10000000:07d}"

    # Create vessel
    vessel_resp = await async_client.post(
        "/vessels",
        json={"vessel_name": "Has Crew", "imo_number": imo},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    vessel_id = vessel_resp.json()["vessel_id"]

    # Create seafarer on vessel
    seafarer_resp = await async_client.post(
        "/seafarers",
        json={
            "vessel_id": vessel_id,
            "first_name": "John",
            "last_name": "Doe",
            "rank": "Captain",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert seafarer_resp.status_code == 201
    seafarer_id = seafarer_resp.json()["seafarer_id"]

    # Try to delete vessel
    del_resp = await async_client.delete(
        f"/vessels/{vessel_id}", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert del_resp.status_code == 409

    # Cleanup
    await async_client.delete(
        f"/seafarers/{seafarer_id}", headers={"Authorization": f"Bearer {admin_token}"}
    )
    await async_client.delete(
        f"/vessels/{vessel_id}", headers={"Authorization": f"Bearer {admin_token}"}
    )


@pytest.mark.asyncio
async def test_vessel_endpoints_require_auth(async_client: AsyncClient) -> None:
    resp = await async_client.get("/vessels")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_vessel_write_endpoints_require_admin(
    async_client: AsyncClient, crewing_officer_token: str
) -> None:
    resp = await async_client.post(
        "/vessels",
        json={"vessel_name": "X", "imo_number": "0000001"},
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_vessel_not_found(async_client: AsyncClient, admin_token: str) -> None:
    resp = await async_client.get(
        "/vessels/999999", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 404
