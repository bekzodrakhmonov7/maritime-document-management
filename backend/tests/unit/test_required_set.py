"""The required set for a (Position, Vessel or none) pair (FR-08, T2).

Matrix rows for the Position, then flag exceptions, then vessel exceptions.
Vessel beats flag, a Position-specific exception beats an all-positions one,
retired types are never required, and dependencies are never followed.
"""

from app.domain import RequirementException, VesselRef, required_set

MASTER, COOK = 1, 2
PASSPORT, MEDICAL, COC, FLAG_ENDORSEMENT, VISA = 10, 11, 12, 13, 14
MALTA_SHIP = VesselRef(id=100, flag="MT")
GREEK_SHIP = VesselRef(id=200, flag="GR")

MATRIX = [
    (MASTER, PASSPORT),
    (MASTER, MEDICAL),
    (MASTER, COC),
    (MASTER, FLAG_ENDORSEMENT),
    (COOK, PASSPORT),
    (COOK, MEDICAL),
]


def flag_rule(effect, type_id, flag="MT", position_id=None):
    return RequirementException(
        document_type_id=type_id, effect=effect, flag=flag, position_id=position_id
    )


def vessel_rule(effect, type_id, vessel_id=MALTA_SHIP.id, position_id=None):
    return RequirementException(
        document_type_id=type_id, effect=effect, vessel_id=vessel_id, position_id=position_id
    )


def test_no_vessel_means_the_matrix_only():
    exceptions = [flag_rule("add", VISA), vessel_rule("remove", PASSPORT)]
    assert required_set(MASTER, None, MATRIX, exceptions, set()) == {
        PASSPORT, MEDICAL, COC, FLAG_ENDORSEMENT
    }
    assert required_set(COOK, None, MATRIX, exceptions, set()) == {PASSPORT, MEDICAL}


def test_a_position_with_no_matrix_rows_needs_nothing():
    assert required_set(999, MALTA_SHIP, MATRIX, [], set()) == set()


def test_a_flag_exception_adds_and_removes_for_vessels_of_that_flag_only():
    exceptions = [flag_rule("add", VISA), flag_rule("remove", MEDICAL)]
    assert required_set(COOK, MALTA_SHIP, MATRIX, exceptions, set()) == {PASSPORT, VISA}
    assert required_set(COOK, GREEK_SHIP, MATRIX, exceptions, set()) == {PASSPORT, MEDICAL}


def test_a_vessel_exception_applies_to_that_vessel_only():
    exceptions = [vessel_rule("add", VISA)]
    assert required_set(COOK, MALTA_SHIP, MATRIX, exceptions, set()) == {PASSPORT, MEDICAL, VISA}
    assert required_set(COOK, VesselRef(id=101, flag="MT"), MATRIX, exceptions, set()) == {
        PASSPORT, MEDICAL
    }


def test_a_vessel_exception_beats_a_flag_exception():
    exceptions = [
        flag_rule("add", VISA),
        vessel_rule("remove", VISA),
        flag_rule("remove", MEDICAL),
        vessel_rule("add", MEDICAL),
    ]
    assert required_set(COOK, MALTA_SHIP, MATRIX, exceptions, set()) == {PASSPORT, MEDICAL}


def test_an_all_positions_vessel_exception_beats_a_position_specific_flag_one():
    exceptions = [flag_rule("add", VISA, position_id=COOK), vessel_rule("remove", VISA)]
    assert required_set(COOK, MALTA_SHIP, MATRIX, exceptions, set()) == {PASSPORT, MEDICAL}


def test_a_position_specific_exception_beats_an_all_positions_one():
    # In either order: the most specific rule wins, not the last one.
    for exceptions in (
        [flag_rule("add", VISA), flag_rule("remove", VISA, position_id=COOK)],
        [flag_rule("remove", VISA, position_id=COOK), flag_rule("add", VISA)],
    ):
        assert required_set(COOK, MALTA_SHIP, MATRIX, exceptions, set()) == {PASSPORT, MEDICAL}
        assert VISA in required_set(MASTER, MALTA_SHIP, MATRIX, exceptions, set())

    for exceptions in (
        [vessel_rule("remove", PASSPORT), vessel_rule("add", PASSPORT, position_id=COOK)],
        [vessel_rule("add", PASSPORT, position_id=COOK), vessel_rule("remove", PASSPORT)],
    ):
        assert PASSPORT in required_set(COOK, MALTA_SHIP, MATRIX, exceptions, set())
        assert PASSPORT not in required_set(MASTER, MALTA_SHIP, MATRIX, exceptions, set())


def test_an_exception_for_another_position_does_not_apply():
    exceptions = [vessel_rule("add", VISA, position_id=MASTER)]
    assert VISA not in required_set(COOK, MALTA_SHIP, MATRIX, exceptions, set())


def test_retired_types_are_never_required():
    exceptions = [flag_rule("add", VISA)]
    retired = {MEDICAL, VISA}
    assert required_set(COOK, None, MATRIX, exceptions, retired) == {PASSPORT}
    assert required_set(COOK, MALTA_SHIP, MATRIX, exceptions, retired) == {PASSPORT}


def test_a_no_op_add_or_remove_has_no_effect():
    exceptions = [flag_rule("add", PASSPORT), vessel_rule("remove", VISA)]
    assert required_set(COOK, MALTA_SHIP, MATRIX, exceptions, set()) == {PASSPORT, MEDICAL}


def test_dependencies_are_not_followed():
    # Removing the certificate leaves its Endorsement required, and adding an
    # Endorsement doesn't bring its certificate in.
    exceptions = [vessel_rule("remove", COC, position_id=MASTER)]
    assert required_set(MASTER, MALTA_SHIP, MATRIX, exceptions, set()) == {
        PASSPORT, MEDICAL, FLAG_ENDORSEMENT
    }
    exceptions = [vessel_rule("add", FLAG_ENDORSEMENT, position_id=COOK)]
    assert required_set(COOK, MALTA_SHIP, MATRIX, exceptions, set()) == {
        PASSPORT, MEDICAL, FLAG_ENDORSEMENT
    }
