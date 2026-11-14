"""Database guards on requirements (FR-08, T2).

The matrix has one row per (Position, Document Type). An exception has exactly
one of a vessel or a flag, a reason, and is unique on (scope, Position-or-all,
type). Foreign keys RESTRICT, so a used Position or type is retired instead.
"""

import asyncpg
import pytest

pytestmark = pytest.mark.usefixtures("reference_cleanup")


@pytest.fixture
async def rows(owner_db) -> dict[str, int]:
    return {
        "vessel": await owner_db.fetchval(
            "INSERT INTO public.vessel (name, imo_number, flag) VALUES ('MV Guard', '9000001', 'MT') RETURNING id"
        ),
        "master": await owner_db.fetchval(
            "INSERT INTO public.position (name) VALUES ('Master') RETURNING id"
        ),
        "passport": await owner_db.fetchval(
            "INSERT INTO public.document_type (name) VALUES ('Passport') RETURNING id"
        ),
    }


async def _exception(owner_db, *, vessel_id=None, flag=None, position_id=None, type_id, effect="add", reason="Local rule"):
    return await owner_db.fetchval(
        """
        INSERT INTO public.requirement_exception
            (vessel_id, flag, position_id, document_type_id, effect, reason)
        VALUES ($1, $2, $3, $4, $5, $6) RETURNING id
        """,
        vessel_id, flag, position_id, type_id, effect, reason,
    )


async def test_a_matrix_cell_exists_once(owner_db, rows):
    insert = "INSERT INTO public.position_requirement (position_id, document_type_id) VALUES ($1, $2)"
    await owner_db.execute(insert, rows["master"], rows["passport"])
    with pytest.raises(asyncpg.UniqueViolationError):
        await owner_db.execute(insert, rows["master"], rows["passport"])


async def test_there_is_no_is_mandatory_flag(owner_db):
    assert await owner_db.fetchval(
        "SELECT count(*) FROM information_schema.columns WHERE column_name = 'is_mandatory'"
    ) == 0


@pytest.mark.parametrize("scope", [{}, {"vessel": True, "flag": "MT"}])
async def test_an_exception_has_exactly_one_of_vessel_or_flag(owner_db, rows, scope):
    with pytest.raises(asyncpg.CheckViolationError):
        await _exception(
            owner_db,
            vessel_id=rows["vessel"] if scope.get("vessel") else None,
            flag=scope.get("flag"),
            type_id=rows["passport"],
        )


@pytest.mark.parametrize("field, value", [("effect", "maybe"), ("reason", "  "), ("flag", "mt")])
async def test_an_exception_needs_an_effect_a_reason_and_a_two_letter_flag(owner_db, rows, field, value):
    values = {"flag": "MT", "type_id": rows["passport"], field: value}
    with pytest.raises(asyncpg.CheckViolationError):
        await _exception(owner_db, **values)


@pytest.mark.parametrize("scope", ["vessel", "flag"])
@pytest.mark.parametrize("for_one_position", [False, True])
async def test_an_exception_is_unique_on_scope_position_and_type(owner_db, rows, scope, for_one_position):
    values = {
        "vessel_id": rows["vessel"] if scope == "vessel" else None,
        "flag": "MT" if scope == "flag" else None,
        "position_id": rows["master"] if for_one_position else None,
        "type_id": rows["passport"],
    }
    await _exception(owner_db, **values)
    with pytest.raises(asyncpg.UniqueViolationError) as exc:
        await _exception(owner_db, **values, effect="remove")
    assert exc.value.constraint_name == "uq_requirement_exception"


async def test_the_same_type_may_have_exceptions_in_different_scopes(owner_db, rows):
    other_position = await owner_db.fetchval(
        "INSERT INTO public.position (name) VALUES ('Cook') RETURNING id"
    )
    type_id = rows["passport"]
    await _exception(owner_db, flag="MT", type_id=type_id)
    await _exception(owner_db, flag="GR", type_id=type_id)
    await _exception(owner_db, flag="MT", position_id=rows["master"], type_id=type_id)
    await _exception(owner_db, flag="MT", position_id=other_position, type_id=type_id)
    await _exception(owner_db, vessel_id=rows["vessel"], type_id=type_id)
    await _exception(owner_db, vessel_id=rows["vessel"], position_id=rows["master"], type_id=type_id)
    assert await owner_db.fetchval("SELECT count(*) FROM public.requirement_exception") == 6


async def test_a_used_position_or_type_cannot_be_deleted(owner_db, rows):
    await owner_db.execute(
        "INSERT INTO public.position_requirement (position_id, document_type_id) VALUES ($1, $2)",
        rows["master"], rows["passport"],
    )
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await owner_db.execute("DELETE FROM public.position WHERE id = $1", rows["master"])
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await owner_db.execute("DELETE FROM public.document_type WHERE id = $1", rows["passport"])
