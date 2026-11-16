"""Coverage, missing documents and the readiness view (FR-17, FR-18, FR-19; T3, T4),
as plain functions."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.domain import (
    RequiredDocument,
    RequirementRows,
    RequirementException,
    coverage_class,
    evaluated_pair,
    missing_documents,
    readiness,
    VesselRef,
)

S = date(2027, 3, 1)
D = date(2027, 6, 30)
ONE_DAY = timedelta(days=1)


def _current(expiry: date | None) -> dict:
    return {"id": 1, "expiry_date": expiry}


# --- coverage_class -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "expiry, expected",
    [
        (S - ONE_DAY, "runs_out_before_start"),
        (S, "runs_out_during"),
        (D - ONE_DAY, "runs_out_during"),
        (D, "runs_out_during"),
        (D + ONE_DAY, "covers_all"),
        (None, "covers_all"),
    ],
)
def test_each_coverage_class_at_its_boundary(expiry, expected):
    assert coverage_class(S, D, _current(expiry)) == expected


def test_no_current_version_is_missing():
    assert coverage_class(S, D, None) == "missing"


def test_coverage_ignores_the_issue_date():
    # Issued after the start still covers: only the expiry date counts.
    version = {"id": 1, "issue_date": S + ONE_DAY, "expiry_date": D + ONE_DAY}
    assert coverage_class(S, D, version) == "covers_all"


# --- missing_documents --------------------------------------------------------------------

MASTER, CHIEF_OFFICER = 1, 2
PASSPORT, MEDICAL, YELLOW_FEVER = 10, 11, 12
LIBERIAN = VesselRef(id=100, flag="LR")
TODAY = date(2027, 2, 1)

ROWS = RequirementRows(
    matrix=[(MASTER, PASSPORT), (MASTER, MEDICAL), (CHIEF_OFFICER, PASSPORT)],
    exceptions=[RequirementException(document_type_id=YELLOW_FEVER, effect="add", flag="LR")],
    retired_types=set(),
)


def _assignment(start: date, end: date, position_id=CHIEF_OFFICER, cancelled=False) -> dict:
    return {
        "position_id": position_id,
        "vessel_id": LIBERIAN.id,
        "vessel_flag": LIBERIAN.flag,
        "start_date": start,
        "end_date": end,
        "cancelled_at": datetime(2027, 1, 1, tzinfo=timezone.utc) if cancelled else None,
    }


def test_ashore_the_held_position_with_no_vessel_is_evaluated():
    assert evaluated_pair(MASTER, [], TODAY) == (MASTER, None)


def test_an_upcoming_assignment_does_not_feed_missing_documents():
    upcoming = _assignment(TODAY + ONE_DAY, TODAY + 30 * ONE_DAY)
    assert evaluated_pair(MASTER, [upcoming], TODAY) == (MASTER, None)
    assert missing_documents(MASTER, [upcoming], TODAY, ROWS, {}) == {PASSPORT, MEDICAL}


def test_under_way_the_assignments_position_and_vessel_are_evaluated():
    under_way = _assignment(TODAY - ONE_DAY, TODAY + ONE_DAY)
    assert evaluated_pair(MASTER, [under_way], TODAY) == (CHIEF_OFFICER, LIBERIAN)
    # Chief Officer on a Liberian ship: passport plus the flag's yellow fever.
    assert missing_documents(MASTER, [under_way], TODAY, ROWS, {}) == {PASSPORT, YELLOW_FEVER}


def test_a_cancelled_assignment_does_not_count():
    cancelled = _assignment(TODAY - ONE_DAY, TODAY + ONE_DAY, cancelled=True)
    assert evaluated_pair(MASTER, [cancelled], TODAY) == (MASTER, None)


def test_missing_means_no_current_version_whatever_the_expiry():
    current = {PASSPORT: _current(TODAY - 100 * ONE_DAY), MEDICAL: None}
    # The expired passport is not missing; the all-rejected medical is.
    assert missing_documents(MASTER, [], TODAY, ROWS, current) == {MEDICAL}


# --- readiness ------------------------------------------------------------------------------

UPCOMING_TODAY = S - 10 * ONE_DAY
UNDER_WAY_TODAY = S + 20 * ONE_DAY

ASSIGNMENT = {
    "start_date": S,
    "end_date": D,
    "position_id": CHIEF_OFFICER,
    "position_name": "Chief Officer",
    "held_position_id": CHIEF_OFFICER,
    "held_position_name": "Chief Officer",
}


def _doc(
    name: str,
    expiry: date | None = None,
    *,
    missing: bool = False,
    renewable: bool = False,
    review: str = "accepted",
    verified: bool = False,
    type_id: int | None = None,
) -> RequiredDocument:
    return RequiredDocument(
        document_type_id=type_id or abs(hash(name)) % 10_000,
        name=name,
        renewable_at_sea=renewable,
        document_id=None if missing else 7,
        current_version=None if missing else _current(expiry),
        review_state=None if missing else review,
        verified=verified,
    )


def _view(*docs: RequiredDocument, today: date = UPCOMING_TODAY, assignment=ASSIGNMENT) -> dict:
    return readiness(assignment, docs, today)


def _only(view: dict, bucket: str) -> dict:
    [entry] = view["buckets"][bucket]
    return entry


def _buckets_holding(view: dict, name: str) -> set[str]:
    return {b for b, entries in view["buckets"].items() if any(e["name"] == name for e in entries)}


def test_missing_goes_before_joining():
    view = _view(_doc("Passport", missing=True))
    entry = _only(view, "before_joining")
    assert entry["coverage"] == "missing"
    assert entry["suggestion"] == "Obtain before joining"
    assert entry["review_state"] is None


def test_missing_under_way():
    entry = _only(_view(_doc("Passport", missing=True), today=UNDER_WAY_TODAY), "before_joining")
    assert entry["suggestion"] == "Obtain as soon as possible"


def test_runs_out_before_start():
    e = S - ONE_DAY
    entry = _only(_view(_doc("Passport", e)), "before_joining")
    assert entry["coverage"] == "runs_out_before_start"
    assert entry["suggestion"] == f"Renew before joining (runs out {e.isoformat()})"


def test_runs_out_before_start_under_way():
    e = S - ONE_DAY
    entry = _only(_view(_doc("Passport", e), today=UNDER_WAY_TODAY), "before_joining")
    assert entry["coverage"] == "runs_out_before_start"
    assert entry["suggestion"] == f"Expired {e.isoformat()}, renew as soon as possible"


def test_runs_out_during_and_renewable_at_sea():
    e = D - ONE_DAY
    view = _view(_doc("Medical", e, renewable=True))
    entry = _only(view, "renewable_at_sea")
    assert entry["coverage"] == "runs_out_during"
    assert entry["suggestion"] == f"Can be renewed at sea, by {e.isoformat()}"
    assert _buckets_holding(view, "Medical") == {"renewable_at_sea"}


def test_runs_out_during_and_renewable_at_sea_under_way_not_yet_expired():
    e = D - ONE_DAY
    entry = _only(_view(_doc("Medical", e, renewable=True), today=UNDER_WAY_TODAY), "renewable_at_sea")
    assert entry["suggestion"] == f"Can be renewed at sea, by {e.isoformat()}"


def test_runs_out_during_and_not_renewable_at_sea():
    entry = _only(_view(_doc("CoC", S)), "before_joining")
    assert entry["coverage"] == "runs_out_during"
    assert entry["suggestion"] == "Renew before joining, not renewable at sea"


def test_runs_out_during_not_renewable_under_way_not_yet_expired():
    e = D - ONE_DAY
    entry = _only(_view(_doc("CoC", e), today=UNDER_WAY_TODAY), "before_joining")
    assert entry["coverage"] == "runs_out_during"
    assert entry["suggestion"] == f"Plan relief or port renewal before {e.isoformat()}"


# Expiring on the planned end date runs out during: Assignments often end late.


def test_expiring_on_the_end_date_is_renew_before_joining_when_not_renewable_at_sea():
    entry = _only(_view(_doc("CoC", D)), "before_joining")
    assert entry["coverage"] == "runs_out_during"
    assert entry["suggestion"] == "Renew before joining, not renewable at sea"


def test_expiring_on_the_end_date_under_way_is_plan_relief_when_not_renewable_at_sea():
    entry = _only(_view(_doc("CoC", D), today=UNDER_WAY_TODAY), "before_joining")
    assert entry["coverage"] == "runs_out_during"
    assert entry["suggestion"] == f"Plan relief or port renewal before {D.isoformat()}"


def test_expiring_on_the_end_date_can_be_renewed_at_sea():
    entry = _only(_view(_doc("Medical", D, renewable=True)), "renewable_at_sea")
    assert entry["coverage"] == "runs_out_during"
    assert entry["suggestion"] == f"Can be renewed at sea, by {D.isoformat()}"


@pytest.mark.parametrize("renewable", [True, False])
def test_expired_on_board_is_renew_now_and_keeps_its_coverage_class(renewable):
    e = UNDER_WAY_TODAY - ONE_DAY  # S <= E < today: ran out while on board
    view = _view(_doc("Medical", e, renewable=renewable), today=UNDER_WAY_TODAY)
    entry = _only(view, "before_joining")
    assert entry["coverage"] == "runs_out_during"
    assert entry["suggestion"] == f"Expired {e.isoformat()} while on board, renew now"
    assert view["buckets"]["renewable_at_sea"] == []


def test_valid_through_today_on_board_is_not_expired_yet():
    view = _view(_doc("Medical", UNDER_WAY_TODAY, renewable=True), today=UNDER_WAY_TODAY)
    assert _only(view, "renewable_at_sea")["suggestion"].startswith("Can be renewed at sea")


@pytest.mark.parametrize("expiry", [D + ONE_DAY, None])
def test_covers_all_has_no_suggestion(expiry):
    view = _view(_doc("Passport", expiry))
    entry = _only(view, "covers_all")
    assert entry["coverage"] == "covers_all"
    assert entry["suggestion"] is None
    assert view["counters"] == {"before_joining": 0, "renewable_at_sea": 0, "not_reviewed": 0}


def test_an_awaiting_review_version_counts_toward_coverage():
    view = _view(_doc("Passport", D + ONE_DAY, review="not_reviewed"))
    entry = _only(view, "not_reviewed")
    assert entry["coverage"] == "covers_all"
    assert entry["review_state"] == "not_reviewed"
    # Bucket 4 is everything else, so it isn't listed twice.
    assert view["buckets"]["covers_all"] == []


def test_not_reviewed_overlaps_the_problem_buckets():
    view = _view(
        _doc("CoC", S - ONE_DAY, review="not_reviewed"),
        _doc("Medical", S, renewable=True, review="not_reviewed"),
    )
    assert _buckets_holding(view, "CoC") == {"before_joining", "not_reviewed"}
    assert _buckets_holding(view, "Medical") == {"renewable_at_sea", "not_reviewed"}
    assert view["counters"] == {"before_joining": 1, "renewable_at_sea": 1, "not_reviewed": 2}


def test_counters_count_the_buckets_and_entries_sort_by_name():
    view = _view(
        _doc("Passport", missing=True),
        _doc("CoC", S - ONE_DAY),
        _doc("Medical", S, renewable=True),
        _doc("Basic Safety", D + ONE_DAY, review="not_reviewed"),
        _doc("Seaman's Book", None),
    )
    assert view["counters"] == {"before_joining": 2, "renewable_at_sea": 1, "not_reviewed": 1}
    assert [e["name"] for e in view["buckets"]["before_joining"]] == ["CoC", "Passport"]
    assert [e["name"] for e in view["buckets"]["covers_all"]] == ["Seaman's Book"]


def test_the_first_counter_is_labelled_act_now_when_under_way():
    assert _view(today=UPCOMING_TODAY)["before_joining_label"] == "Before joining"
    assert _view(today=UNDER_WAY_TODAY)["before_joining_label"] == "Act now"
    assert _view(today=UPCOMING_TODAY)["state"] == "upcoming"
    assert _view(today=UNDER_WAY_TODAY)["state"] == "under_way"


def test_the_verified_shield_is_a_badge_only():
    plain = _view(_doc("Passport", S - ONE_DAY))
    shielded = _view(_doc("Passport", S - ONE_DAY, verified=True))
    assert _only(shielded, "before_joining")["verified"] is True
    assert _only(plain, "before_joining")["verified"] is False
    for key in ("coverage", "suggestion"):
        assert _only(shielded, "before_joining")[key] == _only(plain, "before_joining")[key]
    assert shielded["counters"] == plain["counters"]


def test_no_notice_when_the_positions_match():
    assert _view()["position_notice"] is None


def test_the_different_position_notice():
    promoted = {**ASSIGNMENT, "held_position_id": 3, "held_position_name": "Second Officer"}
    assert _view(assignment=promoted)["position_notice"] == (
        "Assigned as Chief Officer; holds Second Officer. "
        "Requirements below are for Chief Officer."
    )


def test_there_is_no_overall_verdict():
    view = _view(_doc("Passport", D + ONE_DAY))
    assert set(view) == {
        "state", "position_notice", "before_joining_label", "counters", "buckets"
    }


def test_a_finished_assignment_has_no_readiness():
    with pytest.raises(ValueError):
        _view(today=D + ONE_DAY)
