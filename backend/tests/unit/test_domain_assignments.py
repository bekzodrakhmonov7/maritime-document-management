"""Assignment state and Current Vessel (T3), as plain functions."""

from datetime import date, datetime, timezone

from app import domain

START = date(2027, 3, 1)
END = date(2027, 6, 30)


def test_an_assignment_is_upcoming_before_its_start_date():
    assert domain.assignment_state(START, END, date(2027, 2, 28)) == "upcoming"


def test_an_assignment_is_under_way_on_its_start_date():
    assert domain.assignment_state(START, END, START) == "under_way"


def test_an_assignment_is_under_way_on_its_end_date():
    assert domain.assignment_state(START, END, END) == "under_way"


def test_an_assignment_is_finished_the_day_after_its_end_date():
    assert domain.assignment_state(START, END, date(2027, 7, 1)) == "finished"


def test_a_one_day_assignment_is_under_way_on_that_day():
    assert domain.assignment_state(START, START, START) == "under_way"


def _row(vessel_id, start, end, cancelled=False):
    return {
        "vessel_id": vessel_id,
        "start_date": start,
        "end_date": end,
        "cancelled_at": datetime(2027, 1, 1, tzinfo=timezone.utc) if cancelled else None,
    }


def test_the_current_vessel_is_the_one_of_the_assignment_under_way():
    rows = [
        _row(1, date(2027, 1, 1), date(2027, 2, 28)),
        _row(2, START, END),
        _row(3, date(2027, 7, 1), date(2027, 9, 30)),
    ]
    assert domain.current_assignment(rows, START)["vessel_id"] == 2
    assert domain.current_assignment(rows, date(2027, 7, 1))["vessel_id"] == 3


def test_a_seafarer_with_no_assignment_under_way_is_ashore():
    rows = [_row(2, START, END)]
    assert domain.current_assignment(rows, date(2027, 2, 28)) is None
    assert domain.current_assignment([], START) is None


def test_a_cancelled_assignment_is_never_the_current_one():
    assert domain.current_assignment([_row(2, START, END, cancelled=True)], START) is None


def test_today_is_the_date_in_the_company_time_zone():
    late_evening_utc = datetime(2027, 3, 1, 23, 30, tzinfo=timezone.utc)
    assert domain.today_in("UTC", late_evening_utc) == date(2027, 3, 1)
    assert domain.today_in("Asia/Manila", late_evening_utc) == date(2027, 3, 2)
    assert domain.today_in("America/New_York", late_evening_utc) == date(2027, 3, 1)
