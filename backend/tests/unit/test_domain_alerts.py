"""Alert-step choice, alert open-ness and recipients (FR-16, T6): pure functions."""

from datetime import date, datetime, time, timedelta
from uuid import uuid4

import pytest

from app.domain import (
    StepToRaise,
    alert_is_open,
    alert_recipients,
    current_version,
    daily_check_due,
    step_to_raise,
)

STEPS = [90, 60, 30, 0]
TODAY = date(2026, 11, 14)


def expiring_in(days: int) -> date:
    return TODAY + timedelta(days=days)


# --- step_to_raise -----------------------------------------------------------------------


def test_nothing_before_the_largest_step():
    assert step_to_raise(expiring_in(91), TODAY, STEPS, set()) is None


@pytest.mark.parametrize("days_left, step", [(90, 90), (60, 60), (31, 60), (30, 30), (1, 30), (0, 0)])
def test_each_step_is_reached_on_its_day(days_left, step):
    # Each earlier step has already been raised in turn.
    raised = {s for s in STEPS if s > step}
    assert step_to_raise(expiring_in(days_left), TODAY, STEPS, raised) == StepToRaise(step, ())


def test_a_step_already_raised_is_not_raised_again():
    assert step_to_raise(expiring_in(45), TODAY, STEPS, {90, 60}) is None


def test_steps_reached_late_send_only_the_most_urgent_and_skip_the_rest():
    # Missed runs: 90 was raised, then nothing until 20 days before expiry.
    assert step_to_raise(expiring_in(20), TODAY, STEPS, {90}) == StepToRaise(30, (60,))


def test_already_expired_at_upload_gives_one_step_zero_alert():
    choice = step_to_raise(expiring_in(-10), TODAY, STEPS, set())
    assert choice == StepToRaise(0, (90, 60, 30))


def test_the_expiry_day_itself_is_step_zero():
    assert step_to_raise(expiring_in(0), TODAY, STEPS, set()).step == 0


def test_once_step_zero_is_raised_nothing_more_comes_for_that_expiry():
    assert step_to_raise(expiring_in(-30), TODAY, STEPS, {90, 60, 30, 0}) is None


def test_steps_are_taken_in_any_order():
    assert step_to_raise(expiring_in(50), TODAY, [0, 90, 60], set()) == StepToRaise(60, (90,))


def test_a_renewal_with_a_new_expiry_restarts_the_steps():
    # Steps raised for the old expiry don't count for the new one.
    raised_by_expiry = {expiring_in(-1): {90, 60, 30, 0}}
    new_expiry = expiring_in(85)
    choice = step_to_raise(new_expiry, TODAY, STEPS, raised_by_expiry.get(new_expiry, set()))
    assert choice == StepToRaise(90, ())


def test_a_details_only_version_with_the_same_expiry_does_not_re_fire():
    # A corrected document number keeps the expiry, so the raised steps stand.
    expiry = expiring_in(25)
    old = {"id": 1, "uploaded_at": 1, "expiry_date": expiry}
    corrected = {"id": 2, "uploaded_at": 2, "expiry_date": expiry}
    raised_by_expiry = {expiry: {90, 60, 30}}
    current = current_version([old, corrected], [])
    assert current["id"] == 2
    assert step_to_raise(current["expiry_date"], TODAY, STEPS, raised_by_expiry[expiry]) is None


def test_a_rejection_fallback_to_an_expiry_already_alerted_does_not_re_fire():
    old_expiry, new_expiry = expiring_in(20), expiring_in(400)
    old = {"id": 1, "uploaded_at": 1, "expiry_date": old_expiry}
    renewal = {"id": 2, "uploaded_at": 2, "expiry_date": new_expiry}
    rejected = [{"id": 1, "version_id": 2, "decision": "reject"}]
    current = current_version([old, renewal], rejected)
    assert current["expiry_date"] == old_expiry
    assert step_to_raise(old_expiry, TODAY, STEPS, {90, 60, 30}) is None


# --- alert_is_open -----------------------------------------------------------------------


def test_an_alert_is_open_while_the_expiry_is_unchanged_and_the_seafarer_active():
    assert alert_is_open(expiring_in(5), current_expiry=expiring_in(5), seafarer_inactive=False)


def test_a_different_expiry_closes_the_alert():
    assert not alert_is_open(expiring_in(5), current_expiry=expiring_in(370), seafarer_inactive=False)


def test_no_current_version_closes_the_alert():
    assert not alert_is_open(expiring_in(5), current_expiry=None, seafarer_inactive=False)


def test_an_inactive_seafarer_closes_the_alert():
    assert not alert_is_open(expiring_in(5), current_expiry=expiring_in(5), seafarer_inactive=True)


# --- alert_recipients --------------------------------------------------------------------

OFFICER_A, OFFICER_B, ADMIN_1, ADMIN_2 = (uuid4() for _ in range(4))
ADMINS = {ADMIN_1, ADMIN_2}


def test_the_vessels_active_responsible_officers_receive_it():
    assert alert_recipients([1], {1: {OFFICER_A, OFFICER_B}}, ADMINS) == {OFFICER_A, OFFICER_B}


def test_pool_seafarers_go_to_administrators():
    assert alert_recipients([], {1: {OFFICER_A}}, ADMINS) == ADMINS


def test_a_vessel_without_an_active_officer_goes_to_administrators():
    assert alert_recipients([2], {1: {OFFICER_A}}, ADMINS) == ADMINS
    assert alert_recipients([2], {2: set()}, ADMINS) == ADMINS


def test_every_vessel_with_an_upcoming_or_under_way_assignment_counts():
    # Under way on vessel 1 (officer A), next on vessel 2 (no officer).
    assert alert_recipients([1, 2], {1: {OFFICER_A}}, ADMINS) == {OFFICER_A} | ADMINS


# --- daily_check_due ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "local_time, ran_today, due",
    [
        (time(6, 59), False, False),
        (time(7, 0), False, True),
        (time(23, 55), False, True),  # catching up after downtime
        (time(7, 5), True, False),
    ],
)
def test_the_check_runs_once_per_local_date_from_the_check_time(local_time, ran_today, due):
    assert daily_check_due(datetime.combine(TODAY, local_time), time(7, 0), ran_today) is due
