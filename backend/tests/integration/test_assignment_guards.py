"""Database guards for Assignments and Responsible Officers (T3, T5).

- One seafarer's non-cancelled Assignments never overlap; back-to-back (the
  next starts the day after) is allowed, and a cancelled one blocks nothing.
- Only crewing officers can be Responsible Officers, and a role change away
  from crewing officer can't leave links behind.
"""

from datetime import date

import asyncpg
import pytest

pytestmark = pytest.mark.usefixtures("reference_cleanup")


@pytest.fixture
async def rows(owner_db) -> dict:
    position = await owner_db.fetchval(
        "INSERT INTO public.position (name) VALUES ('Master') RETURNING id"
    )
    vessel = await owner_db.fetchval(
        "INSERT INTO public.vessel (name, imo_number, flag) VALUES ('Alpha', '1234567', 'MT') RETURNING id"
    )
    seafarer = await owner_db.fetchval(
        """
        INSERT INTO public.seafarer (first_name, last_name, position_id)
        VALUES ('Anna', 'Petrova', $1) RETURNING id
        """,
        position,
    )
    return {"position": position, "vessel": vessel, "seafarer": seafarer}


async def _assign(owner_db, rows, start: date, end: date, cancelled: bool = False) -> int:
    return await owner_db.fetchval(
        """
        INSERT INTO public.assignment
            (seafarer_id, vessel_id, position_id, start_date, end_date, cancelled_at, cancel_reason)
        VALUES ($1, $2, $3, $4, $5,
                CASE WHEN $6 THEN now() END, CASE WHEN $6 THEN 'Plans changed' END)
        RETURNING id
        """,
        rows["seafarer"], rows["vessel"], rows["position"], start, end, cancelled,
    )


async def test_overlapping_assignments_are_refused(owner_db, rows):
    await _assign(owner_db, rows, date(2027, 1, 1), date(2027, 3, 31))
    with pytest.raises(asyncpg.ExclusionViolationError):
        await _assign(owner_db, rows, date(2027, 3, 31), date(2027, 6, 30))
    with pytest.raises(asyncpg.ExclusionViolationError):
        await _assign(owner_db, rows, date(2027, 2, 1), date(2027, 2, 2))


async def test_back_to_back_assignments_are_allowed(owner_db, rows):
    await _assign(owner_db, rows, date(2027, 1, 1), date(2027, 3, 31))
    await _assign(owner_db, rows, date(2027, 4, 1), date(2027, 6, 30))
    await _assign(owner_db, rows, date(2026, 12, 31), date(2026, 12, 31))


async def test_a_cancelled_assignment_blocks_nothing(owner_db, rows):
    await _assign(owner_db, rows, date(2027, 1, 1), date(2027, 3, 31), cancelled=True)
    await _assign(owner_db, rows, date(2027, 1, 1), date(2027, 3, 31))


async def test_the_end_is_not_before_the_start(owner_db, rows):
    with pytest.raises(asyncpg.CheckViolationError):
        await _assign(owner_db, rows, date(2027, 1, 2), date(2027, 1, 1))


async def test_a_cancellation_needs_a_reason(owner_db, rows):
    assignment = await _assign(owner_db, rows, date(2027, 1, 1), date(2027, 1, 31))
    with pytest.raises(asyncpg.CheckViolationError):
        await owner_db.execute(
            "UPDATE public.assignment SET cancelled_at = now() WHERE id = $1", assignment
        )


async def test_app_backend_cannot_delete_assignments(owner_db):
    assert not await owner_db.fetchval(
        "SELECT has_table_privilege('app_backend', 'public.assignment', 'DELETE')"
    )


@pytest.mark.parametrize("role", ["administrator", "manager"])
async def test_only_a_crewing_officer_can_be_a_responsible_officer(owner_db, make_account, rows, role):
    account = await make_account(role=role)
    with pytest.raises(asyncpg.CheckViolationError):
        await owner_db.execute(
            "INSERT INTO public.responsible_officer (user_id, vessel_id) VALUES ($1, $2)",
            account, rows["vessel"],
        )


async def test_a_role_change_cannot_leave_links_behind(owner_db, make_account, rows):
    officer = await make_account(role="crewing_officer")
    await owner_db.execute(
        "INSERT INTO public.responsible_officer (user_id, vessel_id) VALUES ($1, $2)",
        officer, rows["vessel"],
    )
    with pytest.raises(asyncpg.CheckViolationError):
        await owner_db.execute("UPDATE public.users SET role = 'manager' WHERE id = $1", officer)
    # Deactivating keeps the links.
    await owner_db.execute("UPDATE public.users SET status = 'deactivated' WHERE id = $1", officer)
