"""The dashboard's work queues and the managers' fleet totals (FR-20, T10), as
plain functions."""

from datetime import date, timedelta

import pytest

from app.domain import (
    DashboardFilters,
    DashboardSeafarer,
    DocumentLine,
    StartingSoon,
    dashboard,
    document_queues,
    fleet_totals,
    starts_soon,
)

TODAY = date(2027, 3, 1)
HORIZON = 90
MASTER, COOK = 1, 2
ALPHA, BRAVO = 100, 200
PASSPORT, MEDICAL = 10, 11

ANNA = DashboardSeafarer(
    id=1, first_name="Anna", last_name="Petrova", position_id=MASTER, position_name="Master",
    current_vessel_id=ALPHA, current_vessel_name="Alpha",
)
IVAN = DashboardSeafarer(
    id=2, first_name="Ivan", last_name="Orlov", position_id=COOK, position_name="Cook",
)
OLGA = DashboardSeafarer(
    id=3, first_name="Olga", last_name="Smirnova", position_id=MASTER, position_name="Master",
    inactive=True,
)


def _line(seafarer, type_id=PASSPORT, status="unexpired", review="accepted", **kw) -> DocumentLine:
    missing = status is None
    return DocumentLine(
        seafarer_id=seafarer.id,
        document_type_id=type_id,
        document_type_name={PASSPORT: "Passport", MEDICAL: "Medical"}[type_id],
        document_id=kw.get("document_id", None if missing else seafarer.id * 100 + type_id),
        expiry_date=kw.get("expiry_date"),
        expiry_status=status,
        review_state=None if missing else review,
    )


def _soon(seafarer, start_offset, vessel_id=ALPHA, cancelled=False, **kw) -> StartingSoon:
    start = TODAY + timedelta(days=start_offset)
    return StartingSoon(
        assignment_id=kw.get("assignment_id", start_offset),
        seafarer_id=seafarer.id,
        vessel_id=vessel_id,
        vessel_name={ALPHA: "Alpha", BRAVO: "Bravo"}[vessel_id],
        position_id=kw.get("position_id", seafarer.position_id),
        position_name="Master",
        start_date=start,
        end_date=start + timedelta(days=120),
        cancelled=cancelled,
        counters={"before_joining": 1, "renewable_at_sea": 0, "not_reviewed": 2},
    )


def _board(seafarers=(ANNA, IVAN, OLGA), lines=(), starting=(), **filters) -> dict:
    return dashboard(seafarers, lines, starting, DashboardFilters(**filters), TODAY, HORIZON)


def _names(board, queue) -> list[str]:
    return [g["seafarer"]["last_name"] for g in board["queues"][queue]]


# --- Queue membership ------------------------------------------------------------------


@pytest.mark.parametrize(
    "status, review, expected",
    [
        (None, None, ("missing",)),
        ("expired", "accepted", ("expired",)),
        ("expiring_soon", "accepted", ("expiring_soon",)),
        ("unexpired", "accepted", ("in_order",)),
        ("no_expiry_date", "accepted", ("in_order",)),
        ("expiry_not_stated", "accepted", ("expiry_not_stated",)),
        # Waiting for review overlaps the expiry queues.
        ("expired", "not_reviewed", ("expired", "waiting_for_review")),
        ("expiring_soon", "not_reviewed", ("expiring_soon", "waiting_for_review")),
        ("unexpired", "not_reviewed", ("in_order", "waiting_for_review")),
        ("expiry_not_stated", "not_reviewed", ("expiry_not_stated", "waiting_for_review")),
    ],
)
def test_each_document_lands_in_its_queues(status, review, expected):
    assert document_queues(_line(ANNA, status=status, review=review)) == expected


def test_an_expired_unreviewed_document_is_in_both_queues_and_both_counts():
    board = _board(lines=[_line(ANNA, status="expired", review="not_reviewed")])
    assert board["counts"]["expired"] == 1
    assert board["counts"]["waiting_for_review"] == 1
    [expired] = board["queues"]["expired"][0]["entries"]
    [waiting] = board["queues"]["waiting_for_review"][0]["entries"]
    assert expired["action"] == "upload"
    assert waiting["action"] == "review"


def test_action_hints():
    board = _board(lines=[
        _line(ANNA, PASSPORT, status=None),
        _line(ANNA, MEDICAL, status="unexpired"),
        _line(IVAN, MEDICAL, status="expiry_not_stated"),
    ])
    assert board["queues"]["missing"][0]["entries"][0]["action"] == "upload"
    assert board["queues"]["in_order"][0]["entries"][0]["action"] == "open"
    assert board["queues"]["expiry_not_stated"][0]["entries"][0]["action"] == "open"
    assert list(board["counts"]) == [
        "missing", "expired", "expiring_soon", "expiry_not_stated",
        "waiting_for_review", "starting_soon", "in_order",
    ]


def test_entries_are_grouped_by_seafarer_by_name():
    board = _board(lines=[
        _line(ANNA, PASSPORT, status="expired"),
        _line(IVAN, PASSPORT, status="expired"),
        _line(ANNA, MEDICAL, status="expired"),
    ])
    assert _names(board, "expired") == ["Orlov", "Petrova"]
    petrova = board["queues"]["expired"][1]
    assert petrova["seafarer"]["current_vessel_name"] == "Alpha"
    assert [e["document_type_name"] for e in petrova["entries"]] == ["Medical", "Passport"]
    assert board["counts"]["expired"] == 3


# --- Inactive seafarers ----------------------------------------------------------------


def test_inactive_seafarers_are_left_out_of_queues_and_counts():
    board = _board(lines=[_line(OLGA, status="expired"), _line(OLGA, MEDICAL, status=None)])
    assert board["queues"]["expired"] == []
    assert board["counts"]["expired"] == 0
    assert board["counts"]["missing"] == 0


def test_show_inactive_brings_them_back():
    board = _board(lines=[_line(OLGA, status="expired")], show_inactive=True)
    assert _names(board, "expired") == ["Smirnova"]
    assert board["queues"]["expired"][0]["seafarer"]["inactive"] is True


# --- Starting soon ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "offset, expected",
    [(-1, False), (0, False), (1, True), (HORIZON, True), (HORIZON + 1, False)],
)
def test_starting_soon_is_bounded_by_the_planning_horizon(offset, expected):
    # Starting today is under way, not upcoming.
    assert starts_soon(TODAY + timedelta(days=offset), TODAY, HORIZON) is expected


def test_starting_soon_lists_upcoming_assignments_within_the_horizon_by_start_date():
    board = _board(starting=[
        _soon(ANNA, 60),
        _soon(IVAN, 5),
        _soon(IVAN, HORIZON + 1),
        _soon(ANNA, 0),
        _soon(ANNA, 30, cancelled=True),
    ])
    assert [e["assignment_id"] for e in board["queues"]["starting_soon"]] == [5, 60]
    assert board["counts"]["starting_soon"] == 2
    first = board["queues"]["starting_soon"][0]
    assert first["seafarer"]["last_name"] == "Orlov"
    assert first["counters"] == {"before_joining": 1, "renewable_at_sea": 0, "not_reviewed": 2}


def test_starting_soon_filters_by_the_assignments_vessel_and_position():
    starting = [_soon(ANNA, 10, ALPHA, assignment_id=1), _soon(IVAN, 20, BRAVO, assignment_id=2)]
    board = _board(starting=starting, vessel_ids=frozenset({BRAVO}))
    assert [e["assignment_id"] for e in board["queues"]["starting_soon"]] == [2]
    board = _board(starting=starting, position_ids=frozenset({MASTER}))
    assert [e["assignment_id"] for e in board["queues"]["starting_soon"]] == [1]


def test_ashore_matches_a_joiner_who_is_ashore_today():
    starting = [_soon(ANNA, 10, BRAVO, assignment_id=1), _soon(IVAN, 20, BRAVO, assignment_id=2)]
    board = _board(starting=starting, ashore=True)
    # Anna is on board Alpha today; Ivan is ashore.
    assert [e["assignment_id"] for e in board["queues"]["starting_soon"]] == [2]


# --- Filters ---------------------------------------------------------------------------

LINES = [
    _line(ANNA, PASSPORT, status="expired"),
    _line(ANNA, MEDICAL, status="expired"),
    _line(IVAN, PASSPORT, status="expired"),
]


def test_the_name_filter_needs_every_word():
    assert _names(_board(lines=LINES, name="anna pet"), "expired") == ["Petrova"]
    assert _names(_board(lines=LINES, name="anna orlov"), "expired") == []


def test_tags_narrow_and_counts_follow():
    board = _board(lines=LINES, document_type_ids=frozenset({PASSPORT}))
    assert board["counts"]["expired"] == 2
    board = _board(lines=LINES, position_ids=frozenset({COOK}))
    assert _names(board, "expired") == ["Orlov"]
    board = _board(lines=LINES, vessel_ids=frozenset({ALPHA}))
    assert _names(board, "expired") == ["Petrova"]
    assert board["counts"]["expired"] == 2


def test_ashore_unassigned_is_a_vessel_value():
    assert _names(_board(lines=LINES, ashore=True), "expired") == ["Orlov"]
    board = _board(lines=LINES, ashore=True, vessel_ids=frozenset({ALPHA}))
    assert _names(board, "expired") == ["Orlov", "Petrova"]


def test_tags_of_different_kinds_combine():
    board = _board(
        lines=LINES, vessel_ids=frozenset({ALPHA}), document_type_ids=frozenset({MEDICAL})
    )
    assert board["counts"]["expired"] == 1


# --- Fleet totals ----------------------------------------------------------------------


def test_fleet_totals_per_expiry_status_plus_missing_without_names():
    lines = [
        _line(ANNA, PASSPORT, status="expired", review="not_reviewed"),
        _line(ANNA, MEDICAL, status=None),
        _line(IVAN, PASSPORT, status="unexpired"),
        _line(IVAN, MEDICAL, status="no_expiry_date"),
        _line(IVAN, PASSPORT, status="expiry_not_stated"),
        _line(OLGA, PASSPORT, status="expired"),  # Inactive: left out.
    ]
    totals = fleet_totals([ANNA, IVAN, OLGA], lines, "vessel")
    assert totals["totals"] == {
        "missing": 1, "expired": 1, "expiring_soon": 0, "unexpired": 1,
        "expiry_not_stated": 1, "no_expiry_date": 1,
    }
    assert list(totals["totals"]) == [
        "missing", "expired", "expiring_soon", "unexpired", "expiry_not_stated", "no_expiry_date",
    ]
    assert totals["breakdown"] == "vessel"
    assert totals["rows"] == [
        {"id": ALPHA, "name": "Alpha",
         "counts": {"missing": 1, "expired": 1, "expiring_soon": 0, "unexpired": 0,
                    "expiry_not_stated": 0, "no_expiry_date": 0}},
        {"id": None, "name": "Ashore / Unassigned",
         "counts": {"missing": 0, "expired": 0, "expiring_soon": 0, "unexpired": 1,
                    "expiry_not_stated": 1, "no_expiry_date": 1}},
    ]
    assert "Petrova" not in repr(totals) and "Anna" not in repr(totals)


def test_fleet_totals_by_position_and_document_type():
    lines = [_line(ANNA, PASSPORT, status="expired"), _line(IVAN, PASSPORT, status=None)]
    by_position = fleet_totals([ANNA, IVAN], lines, "position")
    assert [(r["name"], r["counts"]["expired"], r["counts"]["missing"]) for r in by_position["rows"]] == [
        ("Cook", 0, 1), ("Master", 1, 0),
    ]
    by_type = fleet_totals([ANNA, IVAN], lines, "document_type")
    assert [(r["id"], r["counts"]["expired"], r["counts"]["missing"]) for r in by_type["rows"]] == [
        (PASSPORT, 1, 1),
    ]


def test_every_breakdown_counts_expiry_not_stated_and_sums_match_the_required_documents():
    lines = [
        _line(ANNA, PASSPORT, status="expiry_not_stated"),
        _line(ANNA, MEDICAL, status=None),
        _line(IVAN, PASSPORT, status="expiry_not_stated"),
        _line(IVAN, MEDICAL, status="unexpired"),
    ]
    for breakdown in ("vessel", "position", "document_type"):
        totals = fleet_totals([ANNA, IVAN], lines, breakdown)
        assert totals["totals"]["expiry_not_stated"] == 2
        assert sum(r["counts"]["expiry_not_stated"] for r in totals["rows"]) == 2
        assert sum(sum(r["counts"].values()) for r in totals["rows"]) == 4


def test_small_counts_are_not_suppressed():
    totals = fleet_totals([IVAN], [_line(IVAN, PASSPORT, status="expired")], "position")
    assert totals["rows"][0]["counts"]["expired"] == 1
