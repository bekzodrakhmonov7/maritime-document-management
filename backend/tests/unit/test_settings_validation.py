"""Settings validation (T9): every range, the alert-steps rules and IANA zones."""

import pytest
from pydantic import ValidationError

from app.models.settings import SettingsWrite

VALID = {
    "alert_steps": [90, 60, 30, 0],
    "planning_horizon_days": 90,
    "max_file_size_mb": 4,
    "max_pdf_pages": 50,
    "time_zone": "UTC",
    "daily_check_time": "07:00",
    "version": 1,
}


def _with(**changes) -> dict:
    return {**VALID, **changes}


def _refused(field: str, **changes) -> None:
    with pytest.raises(ValidationError) as exc_info:
        SettingsWrite(**_with(**changes))
    assert field in str(exc_info.value)


def test_the_defaults_are_valid():
    s = SettingsWrite(**VALID)
    assert s.alert_steps == [90, 60, 30, 0]
    assert s.daily_check_time == "07:00"


# --- Alert steps -------------------------------------------------------------


@pytest.mark.parametrize("steps", [[0], [0, 1, 2, 3, 4, 5], [365, 0], [7, 0, 14]])
def test_alert_steps_accepted(steps):
    assert SettingsWrite(**_with(alert_steps=steps)).alert_steps == sorted(steps, reverse=True)


def test_alert_steps_are_stored_largest_first():
    assert SettingsWrite(**_with(alert_steps=[0, 30, 90, 60])).alert_steps == [90, 60, 30, 0]


@pytest.mark.parametrize(
    "steps",
    [
        [],  # at least one
        [90, 60, 30],  # 0 must be present
        [0, 30, 30],  # distinct
        [0, 1, 2, 3, 4, 5, 6],  # at most six
        [0, -1],  # not negative
        [0, 7.5],  # whole numbers
        [0, "x"],
    ],
)
def test_alert_steps_refused(steps):
    _refused("alert_steps", alert_steps=steps)


# --- Ranges ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "field, low, high",
    [
        ("planning_horizon_days", 7, 365),
        ("max_file_size_mb", 1, 4),
        ("max_pdf_pages", 1, 500),
    ],
)
def test_range_bounds_are_inclusive(field, low, high):
    assert getattr(SettingsWrite(**_with(**{field: low})), field) == low
    assert getattr(SettingsWrite(**_with(**{field: high})), field) == high
    _refused(field, **{field: low - 1})
    _refused(field, **{field: high + 1})


@pytest.mark.parametrize("field", ["planning_horizon_days", "max_file_size_mb", "max_pdf_pages"])
def test_ranges_take_whole_numbers_only(field):
    _refused(field, **{field: 10.5})


# --- Time zone -----------------------------------------------------------------


@pytest.mark.parametrize("zone", ["UTC", "Europe/Malta", "Asia/Manila", "America/Argentina/Buenos_Aires"])
def test_iana_zones_accepted(zone):
    assert SettingsWrite(**_with(time_zone=zone)).time_zone == zone


@pytest.mark.parametrize(
    "zone", ["", "Mars/Olympus", "europe/malta", "+02:00", "CEST", "localtime", "../etc/passwd"]
)
def test_unknown_zones_refused(zone):
    _refused("time_zone", time_zone=zone)


# --- Daily check time -------------------------------------------------------------


@pytest.mark.parametrize("value", ["00:00", "07:15", "12:30", "23:45"])
def test_check_time_in_15_minute_steps_accepted(value):
    assert SettingsWrite(**_with(daily_check_time=value)).daily_check_time == value


@pytest.mark.parametrize("value", ["07:10", "07:00:30", "24:00", "7:00", "07-00", "", "noon"])
def test_check_time_refused(value):
    _refused("daily_check_time", daily_check_time=value)


def test_version_is_required():
    body = dict(VALID)
    del body["version"]
    with pytest.raises(ValidationError):
        SettingsWrite(**body)
