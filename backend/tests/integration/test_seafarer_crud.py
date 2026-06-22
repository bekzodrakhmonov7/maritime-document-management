import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_seafarers(async_client: AsyncClient, admin_token: str) -> None:
    response = await async_client.get(
        "/seafarers", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    # Verify JOIN works
    assert "vessel_name" in data[0]


@pytest.mark.asyncio
async def test_create_and_get_seafarer(
    async_client: AsyncClient, admin_token: str, crewing_officer_token: str
) -> None:
    import time
    imo = f"{int(time.time() * 1000) % 10000000:07d}"

    vessel_resp = await async_client.post(
        "/vessels",
        json={"vessel_name": "Seafarer Test Vessel", "imo_number": imo},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert vessel_resp.status_code == 201
    vessel_id = vessel_resp.json()["vessel_id"]

    seafarer_resp = await async_client.post(
        "/seafarers",
        json={
            "vessel_id": vessel_id,
            "first_name": "Alice",
            "last_name": "Smith",
            "rank": "Chief Engineer",
        },
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    assert seafarer_resp.status_code == 201
    seafarer = seafarer_resp.json()
    assert seafarer["first_name"] == "Alice"
    seafarer_id = seafarer["seafarer_id"]

    get_resp = await async_client.get(
        f"/seafarers/{seafarer_id}",
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["first_name"] == "Alice"
    assert data["vessel_name"] == "Seafarer Test Vessel"

    # Cleanup
    await async_client.delete(
        f"/seafarers/{seafarer_id}",
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    await async_client.delete(
        f"/vessels/{vessel_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )


@pytest.mark.asyncio
async def test_update_seafarer(
    async_client: AsyncClient, admin_token: str, crewing_officer_token: str
) -> None:
    import time
    imo = f"{int(time.time() * 1000) % 10000000:07d}"

    vessel_resp = await async_client.post(
        "/vessels",
        json={"vessel_name": "Update Test", "imo_number": imo},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    vessel_id = vessel_resp.json()["vessel_id"]

    seafarer_resp = await async_client.post(
        "/seafarers",
        json={
            "vessel_id": vessel_id,
            "first_name": "Old",
            "last_name": "Name",
            "rank": "Deckhand",
        },
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    seafarer_id = seafarer_resp.json()["seafarer_id"]

    patch_resp = await async_client.patch(
        f"/seafarers/{seafarer_id}",
        json={"first_name": "New", "rank": "Captain"},
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["first_name"] == "New"
    assert data["rank"] == "Captain"
    assert data["last_name"] == "Name"

    # Cleanup
    await async_client.delete(
        f"/seafarers/{seafarer_id}",
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    await async_client.delete(
        f"/vessels/{vessel_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )


@pytest.mark.asyncio
async def test_delete_seafarer(
    async_client: AsyncClient, admin_token: str, crewing_officer_token: str
) -> None:
    import time
    imo = f"{int(time.time() * 1000) % 10000000:07d}"

    vessel_resp = await async_client.post(
        "/vessels",
        json={"vessel_name": "Delete Test", "imo_number": imo},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    vessel_id = vessel_resp.json()["vessel_id"]

    seafarer_resp = await async_client.post(
        "/seafarers",
        json={
            "vessel_id": vessel_id,
            "first_name": "Delete",
            "last_name": "Me",
            "rank": "Cook",
        },
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    seafarer_id = seafarer_resp.json()["seafarer_id"]

    del_resp = await async_client.delete(
        f"/seafarers/{seafarer_id}",
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    assert del_resp.status_code == 204

    get_resp = await async_client.get(
        f"/seafarers/{seafarer_id}",
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    assert get_resp.status_code == 404

    # Cleanup vessel
    await async_client.delete(
        f"/vessels/{vessel_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )


@pytest.mark.asyncio
async def test_filter_seafarers_by_vessel(
    async_client: AsyncClient, admin_token: str, crewing_officer_token: str
) -> None:
    import time
    imo = f"{int(time.time() * 1000) % 10000000:07d}"

    vessel_resp = await async_client.post(
        "/vessels",
        json={"vessel_name": "Filter Vessel", "imo_number": imo},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    vessel_id = vessel_resp.json()["vessel_id"]

    # Create two seafarers on this vessel
    for i in range(2):
        await async_client.post(
            "/seafarers",
            json={
                "vessel_id": vessel_id,
                "first_name": f"Crew{i}",
                "last_name": "Test",
                "rank": "Officer",
            },
            headers={"Authorization": f"Bearer {crewing_officer_token}"},
        )

    resp = await async_client.get(
        "/seafarers",
        params={"vessel_id": vessel_id},
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    for s in data:
        assert s["vessel_id"] == vessel_id

    # Cleanup: list and delete all seafarers on vessel, then vessel
    list_resp = await async_client.get(
        "/seafarers",
        params={"vessel_id": vessel_id},
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    for s in list_resp.json():
        await async_client.delete(
            f"/seafarers/{s['seafarer_id']}",
            headers={"Authorization": f"Bearer {crewing_officer_token}"},
        )
    await async_client.delete(
        f"/vessels/{vessel_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )


@pytest.mark.asyncio
async def test_filter_seafarers_by_rank(
    async_client: AsyncClient, admin_token: str, crewing_officer_token: str
) -> None:
    import time
    imo = f"{int(time.time() * 1000) % 10000000:07d}"

    vessel_resp = await async_client.post(
        "/vessels",
        json={"vessel_name": "Rank Vessel", "imo_number": imo},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    vessel_id = vessel_resp.json()["vessel_id"]

    await async_client.post(
        "/seafarers",
        json={
            "vessel_id": vessel_id,
            "first_name": "RankA",
            "last_name": "Test",
            "rank": "UniqueRankA",
        },
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    await async_client.post(
        "/seafarers",
        json={
            "vessel_id": vessel_id,
            "first_name": "RankB",
            "last_name": "Test",
            "rank": "UniqueRankB",
        },
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )

    resp = await async_client.get(
        "/seafarers",
        params={"rank": "UniqueRankA"},
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["rank"] == "UniqueRankA"

    # Cleanup
    list_resp = await async_client.get(
        "/seafarers",
        params={"vessel_id": vessel_id},
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    for s in list_resp.json():
        await async_client.delete(
            f"/seafarers/{s['seafarer_id']}",
            headers={"Authorization": f"Bearer {crewing_officer_token}"},
        )
    await async_client.delete(
        f"/vessels/{vessel_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )


@pytest.mark.asyncio
async def test_seafarer_cursor_pagination(
    async_client: AsyncClient, admin_token: str, crewing_officer_token: str
) -> None:
    import time
    imo = f"{int(time.time() * 1000) % 10000000:07d}"

    vessel_resp = await async_client.post(
        "/vessels",
        json={"vessel_name": "Pagination Vessel", "imo_number": imo},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    vessel_id = vessel_resp.json()["vessel_id"]

    created_ids = []
    for i in range(5):
        r = await async_client.post(
            "/seafarers",
            json={
                "vessel_id": vessel_id,
                "first_name": f"Page{i}",
                "last_name": "Test",
                "rank": "Mate",
            },
            headers={"Authorization": f"Bearer {crewing_officer_token}"},
        )
        created_ids.append(r.json()["seafarer_id"])

    # First page (limit=2)
    resp1 = await async_client.get(
        "/seafarers",
        params={"vessel_id": vessel_id, "limit": 2},
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    assert resp1.status_code == 200
    page1 = resp1.json()
    assert len(page1) == 2

    # Second page using cursor
    cursor = page1[-1]["seafarer_id"]
    resp2 = await async_client.get(
        "/seafarers",
        params={"vessel_id": vessel_id, "limit": 2, "cursor": cursor},
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    assert resp2.status_code == 200
    page2 = resp2.json()
    assert len(page2) == 2
    assert page2[0]["seafarer_id"] > cursor

    # Third page
    cursor2 = page2[-1]["seafarer_id"]
    resp3 = await async_client.get(
        "/seafarers",
        params={"vessel_id": vessel_id, "limit": 2, "cursor": cursor2},
        headers={"Authorization": f"Bearer {crewing_officer_token}"},
    )
    assert resp3.status_code == 200
    page3 = resp3.json()
    assert len(page3) == 1

    # Cleanup
    for sid in created_ids:
        await async_client.delete(
            f"/seafarers/{sid}",
            headers={"Authorization": f"Bearer {crewing_officer_token}"},
        )
    await async_client.delete(
        f"/vessels/{vessel_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )


@pytest.mark.asyncio
async def test_seafarer_endpoints_require_auth(async_client: AsyncClient) -> None:
    resp = await async_client.get("/seafarers")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_seafarer_write_requires_crewing_officer(
    async_client: AsyncClient, no_role_token: str
) -> None:
    resp = await async_client.post(
        "/seafarers",
        json={
            "vessel_id": 1,
            "first_name": "X",
            "last_name": "Y",
            "rank": "Z",
        },
        headers={"Authorization": f"Bearer {no_role_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_seafarer_not_found(
    async_client: AsyncClient, admin_token: str
) -> None:
    resp = await async_client.get(
        "/seafarers/999999", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 404
