import pytest
from datetime import date
from httpx import AsyncClient
from uuid import uuid4

from tests.conftest import make_token


@pytest.mark.asyncio
async def test_missing_mandatory_documents_aggregation(
    client: AsyncClient, db_conn, test_user
) -> None:
    token = make_token(test_user)

    # Count existing mandatory doc types before seeding
    existing_mandatory = await db_conn.fetchval(
        "SELECT COUNT(*) FROM public.document_type WHERE is_mandatory = true"
    )

    # Seed vessels
    v1_id = await db_conn.fetchval(
        "INSERT INTO public.vessel (vessel_name, imo_number) VALUES ($1, $2) RETURNING vessel_id",
        "Vessel A", "1000001"
    )
    v2_id = await db_conn.fetchval(
        "INSERT INTO public.vessel (vessel_name, imo_number) VALUES ($1, $2) RETURNING vessel_id",
        "Vessel B", "1000002"
    )

    # Seed mandatory document types
    uid = uuid4().hex[:8]
    passport_type = await db_conn.fetchval(
        "INSERT INTO public.document_type (type_name, is_mandatory) VALUES ($1, $2) RETURNING doc_type_id",
        f"Passport-{uid}", True
    )
    medical_type = await db_conn.fetchval(
        "INSERT INTO public.document_type (type_name, is_mandatory) VALUES ($1, $2) RETURNING doc_type_id",
        f"Medical-{uid}", True
    )
    # Non-mandatory type (should not appear in reports)
    await db_conn.fetchval(
        "INSERT INTO public.document_type (type_name, is_mandatory) VALUES ($1, $2) RETURNING doc_type_id",
        f"Optional Cert-{uid}", False
    )

    # Seed seafarers
    s1 = await db_conn.fetchval(
        "INSERT INTO public.seafarer (vessel_id, first_name, last_name, rank) VALUES ($1, $2, $3, $4) RETURNING seafarer_id",
        v1_id, "Alice", "Smith", "Captain"
    )
    s2 = await db_conn.fetchval(
        "INSERT INTO public.seafarer (vessel_id, first_name, last_name, rank) VALUES ($1, $2, $3, $4) RETURNING seafarer_id",
        v1_id, "Bob", "Jones", "Engineer"
    )
    s3 = await db_conn.fetchval(
        "INSERT INTO public.seafarer (vessel_id, first_name, last_name, rank) VALUES ($1, $2, $3, $4) RETURNING seafarer_id",
        v1_id, "Charlie", "Brown", "Mate"
    )
    s4 = await db_conn.fetchval(
        "INSERT INTO public.seafarer (vessel_id, first_name, last_name, rank) VALUES ($1, $2, $3, $4) RETURNING seafarer_id",
        v2_id, "Diana", "Prince", "Officer"
    )
    s5 = await db_conn.fetchval(
        "INSERT INTO public.seafarer (vessel_id, first_name, last_name, rank) VALUES ($1, $2, $3, $4) RETURNING seafarer_id",
        v2_id, "Eve", "Davis", "Cook"
    )

    # Seed documents for existing mandatory types so they don't pollute our counts
    existing_type_rows = await db_conn.fetch(
        "SELECT doc_type_id FROM public.document_type WHERE is_mandatory = true AND doc_type_id NOT IN ($1, $2)",
        passport_type, medical_type
    )
    existing_type_ids = [r["doc_type_id"] for r in existing_type_rows]

    for seafarer_id in [s1, s2, s3, s4, s5]:
        for dt_id in existing_type_ids:
            await db_conn.execute(
                """INSERT INTO public.document (seafarer_id, doc_type_id, document_number, issue_date, expiry_date, status, file_path)
                   VALUES ($1, $2, $3, $4, $5, 'verified', '/fake')""",
                seafarer_id, dt_id, "EXISTING", date(2024, 1, 1), date(2026, 1, 1)
            )

    # Seed documents for our new types
    # S1: verified Passport, verified Medical
    await db_conn.execute(
        """INSERT INTO public.document (seafarer_id, doc_type_id, document_number, issue_date, expiry_date, status, file_path)
           VALUES ($1, $2, $3, $4, $5, 'verified', '/fake')""",
        s1, passport_type, "P001", date(2024, 1, 1), date(2026, 1, 1)
    )
    await db_conn.execute(
        """INSERT INTO public.document (seafarer_id, doc_type_id, document_number, issue_date, expiry_date, status, file_path)
           VALUES ($1, $2, $3, $4, $5, 'verified', '/fake')""",
        s1, medical_type, "M001", date(2024, 1, 1), date(2026, 1, 1)
    )

    # S2: verified Passport only
    await db_conn.execute(
        """INSERT INTO public.document (seafarer_id, doc_type_id, document_number, issue_date, expiry_date, status, file_path)
           VALUES ($1, $2, $3, $4, $5, 'verified', '/fake')""",
        s2, passport_type, "P002", date(2024, 1, 1), date(2026, 1, 1)
    )

    # S3: expired Passport only
    await db_conn.execute(
        """INSERT INTO public.document (seafarer_id, doc_type_id, document_number, issue_date, expiry_date, status, file_path)
           VALUES ($1, $2, $3, $4, $5, 'expired', '/fake')""",
        s3, passport_type, "P003", date(2023, 1, 1), date(2024, 1, 1)
    )

    # S4: expiring_soon Passport only
    await db_conn.execute(
        """INSERT INTO public.document (seafarer_id, doc_type_id, document_number, issue_date, expiry_date, status, file_path)
           VALUES ($1, $2, $3, $4, $5, 'expiring_soon', '/fake')""",
        s4, passport_type, "P004", date(2024, 1, 1), date(2025, 1, 1)
    )

    # S5: no documents for new types

    # Test missing mandatory documents endpoint
    resp = await client.get("/reports/missing-mandatory", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()

    # Verify specific rows exist (existing db data may also be present)
    combos = {(r["seafarer_id"], r["doc_type_id"]) for r in data}
    assert (s2, medical_type) in combos
    assert (s3, passport_type) in combos
    assert (s3, medical_type) in combos
    assert (s4, passport_type) in combos
    assert (s4, medical_type) in combos
    assert (s5, passport_type) in combos
    assert (s5, medical_type) in combos
    # S1 should not be missing the specific doc types we created
    assert (s1, passport_type) not in combos
    assert (s1, medical_type) not in combos

    # Test fleet summary endpoint
    resp = await client.get("/reports/fleet-summary", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    summary = resp.json()

    vessels = {v["vessel_name"]: v for v in summary["vessels"]}
    assert "Vessel A" in vessels
    assert "Vessel B" in vessels

    # Vessel A: S1(2 valid new), S2(1 valid new + 1 missing), S3(1 expired + 1 missing)
    # Plus existing_mandatory * 3 valid from the seeded existing-type docs
    assert vessels["Vessel A"]["valid_count"] == existing_mandatory * 3 + 3
    assert vessels["Vessel A"]["expiring_soon_count"] == 0
    assert vessels["Vessel A"]["expired_count"] == 1
    assert vessels["Vessel A"]["missing_count"] == 2

    # Vessel B: S4(1 expiring_soon + 1 missing), S5(2 missing)
    # Plus existing_mandatory * 2 valid from the seeded existing-type docs
    assert vessels["Vessel B"]["valid_count"] == existing_mandatory * 2 + 0
    assert vessels["Vessel B"]["expiring_soon_count"] == 1
    assert vessels["Vessel B"]["expired_count"] == 0
    assert vessels["Vessel B"]["missing_count"] == 3

    # Fleet totals include existing vessels, so just verify they are >= our expected values
    assert summary["total_valid"] >= existing_mandatory * 3 + 3
    assert summary["total_expiring_soon"] >= 1
    assert summary["total_expired"] >= 1
    assert summary["total_missing"] >= 5


@pytest.mark.asyncio
async def test_reports_require_auth(client: AsyncClient) -> None:
    resp = await client.get("/reports/missing-mandatory")
    assert resp.status_code == 401

    resp = await client.get("/reports/fleet-summary")
    assert resp.status_code == 401

    resp = await client.get("/reports/export.csv")
    assert resp.status_code == 401

    resp = await client.get("/reports/export.pdf")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_reports_require_admin_or_crewing_officer(
    client: AsyncClient, no_role_token: str
) -> None:
    resp = await client.get(
        "/reports/missing-mandatory",
        headers={"Authorization": f"Bearer {no_role_token}"}
    )
    assert resp.status_code == 403

    resp = await client.get(
        "/reports/fleet-summary",
        headers={"Authorization": f"Bearer {no_role_token}"}
    )
    assert resp.status_code == 403

    resp = await client.get(
        "/reports/export.csv",
        headers={"Authorization": f"Bearer {no_role_token}"}
    )
    assert resp.status_code == 403

    resp = await client.get(
        "/reports/export.pdf",
        headers={"Authorization": f"Bearer {no_role_token}"}
    )
    assert resp.status_code == 403
