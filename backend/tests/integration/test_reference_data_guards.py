"""Database guards on the reference data (FR-05, FR-07, T2).

They hold whatever the API does: the depends-on rules (one level, no
self-reference, the certificate must expire), maximum validity only on an
expiring type, a two-letter flag, and RESTRICT foreign keys.
"""

import asyncpg
import pytest

from app.config import settings as app_settings


async def _type(owner_db, name, *, expires=True, depends_on=None, max_months=None) -> int:
    return await owner_db.fetchval(
        """
        INSERT INTO public.document_type (name, expires, depends_on_id, max_validity_months)
        VALUES ($1, $2, $3, $4) RETURNING id
        """,
        name,
        expires,
        depends_on,
        max_months,
    )


async def test_a_document_type_has_its_rules(owner_db, reference_cleanup):
    cert = await _type(owner_db, "Guard CoC", max_months=60)
    endorsement = await _type(owner_db, "Guard Endorsement", depends_on=cert)
    row = await owner_db.fetchrow("SELECT * FROM public.document_type WHERE id = $1", endorsement)
    assert row["expires"] is True
    assert row["max_validity_months"] is None
    assert row["renewable_at_sea"] is False
    assert row["depends_on_id"] == cert
    assert row["retired"] is False


async def test_max_validity_is_refused_on_a_non_expiring_type(owner_db, reference_cleanup):
    with pytest.raises(asyncpg.CheckViolationError):
        await _type(owner_db, "Guard Never", expires=False, max_months=12)


async def test_max_validity_must_be_positive(owner_db, reference_cleanup):
    with pytest.raises(asyncpg.CheckViolationError):
        await _type(owner_db, "Guard Zero", max_months=0)


async def test_a_type_cannot_depend_on_itself(owner_db, reference_cleanup):
    type_id = await _type(owner_db, "Guard Self")
    with pytest.raises(asyncpg.CheckViolationError):
        await owner_db.execute(
            "UPDATE public.document_type SET depends_on_id = id WHERE id = $1", type_id
        )


async def test_a_type_cannot_depend_on_an_endorsement(owner_db, reference_cleanup):
    cert = await _type(owner_db, "Guard Cert")
    endorsement = await _type(owner_db, "Guard End", depends_on=cert)
    with pytest.raises(asyncpg.CheckViolationError, match="one level"):
        await _type(owner_db, "Guard End of End", depends_on=endorsement)


async def test_a_certificate_cannot_become_an_endorsement(owner_db, reference_cleanup):
    other = await _type(owner_db, "Guard Other")
    cert = await _type(owner_db, "Guard Cert 2")
    await _type(owner_db, "Guard End 2", depends_on=cert)
    with pytest.raises(asyncpg.CheckViolationError, match="one level"):
        await owner_db.execute(
            "UPDATE public.document_type SET depends_on_id = $2 WHERE id = $1", cert, other
        )


async def test_the_certificate_must_expire(owner_db, reference_cleanup):
    never = await _type(owner_db, "Guard Never Expires", expires=False)
    with pytest.raises(asyncpg.CheckViolationError, match="must expire"):
        await _type(owner_db, "Guard End 3", depends_on=never)


async def test_a_certificate_cannot_stop_expiring(owner_db, reference_cleanup):
    cert = await _type(owner_db, "Guard Cert 4")
    await _type(owner_db, "Guard End 4", depends_on=cert)
    with pytest.raises(asyncpg.CheckViolationError, match="must expire"):
        await owner_db.execute(
            "UPDATE public.document_type SET expires = false WHERE id = $1", cert
        )


async def test_a_used_certificate_cannot_be_deleted(owner_db, reference_cleanup):
    cert = await _type(owner_db, "Guard Cert 5")
    await _type(owner_db, "Guard End 5", depends_on=cert)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await owner_db.execute("DELETE FROM public.document_type WHERE id = $1", cert)


async def test_document_type_and_position_names_are_unique(owner_db, reference_cleanup):
    await _type(owner_db, "Guard Passport")
    with pytest.raises(asyncpg.UniqueViolationError):
        await _type(owner_db, "guard passport")
    await owner_db.execute("INSERT INTO public.position (name) VALUES ('Guard Master')")
    with pytest.raises(asyncpg.UniqueViolationError):
        await owner_db.execute("INSERT INTO public.position (name) VALUES ('GUARD MASTER')")


@pytest.mark.parametrize("flag", ["gr", "GRC", "G", "", None])
async def test_a_vessel_needs_a_two_letter_flag(owner_db, reference_cleanup, flag):
    with pytest.raises((asyncpg.CheckViolationError, asyncpg.NotNullViolationError)):
        await owner_db.execute(
            "INSERT INTO public.vessel (name, imo_number, flag) VALUES ('Guard', '9000001', $1)",
            flag,
        )


async def test_a_vessel_is_active_by_default_and_imo_is_unique(owner_db, reference_cleanup):
    active = await owner_db.fetchval(
        "INSERT INTO public.vessel (name, imo_number, flag) VALUES ('A', '9000002', 'GR') RETURNING active"
    )
    assert active is True
    with pytest.raises(asyncpg.UniqueViolationError):
        await owner_db.execute(
            "INSERT INTO public.vessel (name, imo_number, flag) VALUES ('B', '9000002', 'MT')"
        )
    with pytest.raises(asyncpg.CheckViolationError):
        await owner_db.execute(
            "INSERT INTO public.vessel (name, imo_number, flag) VALUES ('C', '12345', 'MT')"
        )


async def test_app_backend_cannot_delete_vessels(owner_db, reference_cleanup):
    vessel_id = await owner_db.fetchval(
        "INSERT INTO public.vessel (name, imo_number, flag) VALUES ('D', '9000003', 'PA') RETURNING id"
    )
    conn = await asyncpg.connect(app_settings.database_url)
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("DELETE FROM public.vessel WHERE id = $1", vessel_id)
    finally:
        await conn.close()
