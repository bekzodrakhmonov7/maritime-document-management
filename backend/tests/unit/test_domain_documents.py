"""Current Version, Expiry Status and the Version date rules, Review state and
Verified (FR-10, FR-11, FR-12, FR-15; T1, T2)."""

from datetime import date, datetime, timezone

import pytest

from app.domain import (
    current_version,
    expiry_status,
    is_verified,
    latest_allowed_expiry,
    review_state,
    version_dates_problem,
)

E = date(2026, 6, 30)


def _v(version_id: int, minute: int = 0) -> dict:
    return {"id": version_id, "uploaded_at": datetime(2026, 1, 1, 12, minute, tzinfo=timezone.utc)}


def _review(version_id: int, decision: str, review_id: int) -> dict:
    return {"id": review_id, "version_id": version_id, "decision": decision}


# --- current_version -----------------------------------------------------------------


def test_no_versions_means_no_current_version():
    assert current_version([], []) is None


def test_the_newest_version_is_current_reviewed_or_not():
    assert current_version([_v(1, 0), _v(3, 2), _v(2, 1)], [])["id"] == 3


def test_a_rejected_newest_version_falls_back_to_the_previous_one():
    versions = [_v(1, 0), _v(2, 1)]
    assert current_version(versions, [_review(2, "reject", 1)])["id"] == 1


def test_the_latest_review_decides_so_an_overturned_rejection_is_current_again():
    versions = [_v(1, 0), _v(2, 1)]
    reviews = [_review(2, "reject", 1), _review(2, "accept", 2)]
    assert current_version(versions, reviews)["id"] == 2
    reviews.append(_review(2, "reject", 3))
    assert current_version(versions, reviews)["id"] == 1


def test_every_version_rejected_means_no_current_version():
    versions = [_v(1, 0), _v(2, 1)]
    reviews = [_review(1, "reject", 1), _review(2, "reject", 2)]
    assert current_version(versions, reviews) is None


def test_versions_uploaded_at_the_same_time_are_ordered_by_id():
    assert current_version([_v(5, 0), _v(4, 0)], [])["id"] == 5


# --- expiry_status -------------------------------------------------------------------


def test_the_expiry_day_itself_is_expiring_soon_and_still_valid():
    assert expiry_status(E, E, 90, expires=True) == "expiring_soon"


def test_the_day_after_expiry_is_expired():
    assert expiry_status(E, date(2026, 7, 1), 90, expires=True) == "expired"


def test_no_expiry_date():
    assert expiry_status(None, E, 90, expires=False) == "no_expiry_date"


def test_expiry_not_stated_for_an_empty_date_on_an_expiring_type():
    assert expiry_status(None, E, 90, expires=True) == "expiry_not_stated"


def test_expiring_soon_starts_at_the_largest_alert_step():
    assert expiry_status(E, date(2026, 4, 1), 90, expires=True) == "expiring_soon"  # 90 days left
    assert expiry_status(E, date(2026, 3, 31), 90, expires=True) == "unexpired"  # 91 days left


def test_a_smaller_largest_step_moves_the_boundary():
    assert expiry_status(E, date(2026, 4, 1), 30, expires=True) == "unexpired"
    assert expiry_status(E, date(2026, 5, 31), 30, expires=True) == "expiring_soon"


def test_with_only_the_expiry_day_as_a_step_only_that_day_is_expiring_soon():
    assert expiry_status(E, E, 0, expires=True) == "expiring_soon"
    assert expiry_status(E, date(2026, 6, 29), 0, expires=True) == "unexpired"


# --- Version date rules (T2) ---------------------------------------------------------------


@pytest.mark.parametrize(
    "issue, months, latest",
    [
        (date(2026, 1, 15), 12, date(2027, 1, 15)),
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2024, 1, 31), 1, date(2024, 2, 29)),
        (date(2026, 11, 30), 3, date(2027, 2, 28)),
    ],
)
def test_latest_allowed_expiry_adds_whole_months(issue, months, latest):
    assert latest_allowed_expiry(issue, months) == latest


def test_an_expiring_type_needs_an_expiry_date_or_the_tick():
    problem = version_dates_problem(date(2026, 1, 1), None, expires=True, max_validity_months=None)
    assert problem == (
        "This document type expires: enter the expiry date, "
        "or tick 'Expiry not stated on the document'."
    )


def test_an_expiring_type_takes_no_date_with_the_tick():
    assert version_dates_problem(
        date(2026, 1, 1), None, expires=True, max_validity_months=60, expiry_not_stated=True
    ) is None


def test_the_tick_and_a_date_are_refused_together():
    assert "one or the other" in version_dates_problem(
        date(2026, 1, 1), date(2027, 1, 1), expires=True, max_validity_months=None,
        expiry_not_stated=True,
    )


def test_the_tick_is_refused_on_a_type_that_doesnt_expire():
    assert "doesn't expire" in version_dates_problem(
        date(2026, 1, 1), None, expires=False, max_validity_months=None, expiry_not_stated=True
    )


def test_a_non_expiring_type_takes_no_expiry_date():
    assert "no expiry date" in version_dates_problem(
        date(2026, 1, 1), date(2027, 1, 1), expires=False, max_validity_months=None
    )
    assert version_dates_problem(date(2026, 1, 1), None, expires=False, max_validity_months=None) is None


@pytest.mark.parametrize("expiry", [date(2026, 1, 1), date(2025, 12, 31)])
def test_the_expiry_must_be_after_the_issue_date(expiry):
    assert "after the issue date" in version_dates_problem(
        date(2026, 1, 1), expiry, expires=True, max_validity_months=None
    )


def test_maximum_validity_is_a_hard_limit():
    issue = date(2026, 1, 15)
    assert version_dates_problem(issue, date(2031, 1, 15), expires=True, max_validity_months=60) is None
    assert "maximum validity" in version_dates_problem(
        issue, date(2031, 1, 16), expires=True, max_validity_months=60
    )


# --- review_state and is_verified (FR-11, FR-12) --------------------------------------


def _verification(version_id: int, result: str, verification_id: int) -> dict:
    return {"id": verification_id, "version_id": version_id, "result": result}


def test_a_version_without_reviews_is_not_reviewed():
    assert review_state(1, [_review(2, "accept", 1)]) == "not_reviewed"


def test_the_latest_review_is_the_review_state():
    reviews = [_review(1, "accept", 4), _review(1, "reject", 2)]
    assert review_state(1, reviews) == "accepted"
    assert review_state(1, reviews + [_review(1, "reject", 5)]) == "rejected"


def test_verified_when_the_current_versions_latest_verification_is_confirmed():
    current = _v(2, 1)
    assert is_verified(current, [_verification(2, "confirmed", 1)]) is True
    overturned = [_verification(2, "confirmed", 1), _verification(2, "not_confirmed", 2)]
    assert is_verified(current, overturned) is False
    assert is_verified(current, overturned + [_verification(2, "confirmed", 3)]) is True


def test_a_renewal_is_not_verified_by_the_previous_versions_verification():
    assert is_verified(_v(2, 1), [_verification(1, "confirmed", 1)]) is False


def test_no_current_version_is_never_verified():
    assert is_verified(None, [_verification(1, "confirmed", 1)]) is False
