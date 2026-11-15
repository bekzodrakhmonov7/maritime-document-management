"""The one Settings row (FR-25, T9) and its validation."""

import re
from datetime import datetime
from functools import lru_cache
from typing import Annotated
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, Field, StrictInt

from app.upload_safety import FILE_SIZE_CEILING_MB

MAX_ALERT_STEPS = 6

# Files in a system zoneinfo directory that are not zones.
_NOT_ZONES = {"localtime", "posixrules"}

_CHECK_TIME = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")


@lru_cache(maxsize=1)
def iana_zones() -> frozenset[str]:
    return frozenset(available_timezones() - _NOT_ZONES)


def _alert_steps(steps: list[int]) -> list[int]:
    """1-6 distinct whole days >= 0 with 0 present; kept largest first."""
    if not 1 <= len(steps) <= MAX_ALERT_STEPS:
        raise ValueError(f"give between 1 and {MAX_ALERT_STEPS} alert steps")
    if any(s < 0 for s in steps):
        raise ValueError("alert steps are days before expiry, so 0 or more")
    if len(set(steps)) != len(steps):
        raise ValueError("alert steps must all be different")
    if 0 not in steps:
        raise ValueError("alert steps must include 0 (the expiry day)")
    return sorted(steps, reverse=True)


def _time_zone(zone: str) -> str:
    if zone not in iana_zones():
        raise ValueError("must be an IANA time zone, e.g. Europe/Malta")
    return zone


def _check_time(value: str) -> str:
    match = _CHECK_TIME.match(value)
    if match is None:
        raise ValueError("must be a time as HH:MM, e.g. 07:00")
    if int(match.group(2)) % 15:
        raise ValueError("must be on a 15-minute step (:00, :15, :30 or :45)")
    return value


AlertSteps = Annotated[list[StrictInt], AfterValidator(_alert_steps)]
TimeZone = Annotated[str, AfterValidator(_time_zone)]
CheckTime = Annotated[str, AfterValidator(_check_time)]


class SettingsValues(BaseModel):
    alert_steps: AlertSteps
    planning_horizon_days: StrictInt = Field(..., ge=7, le=365)
    max_file_size_mb: StrictInt = Field(..., ge=1, le=FILE_SIZE_CEILING_MB)
    max_pdf_pages: StrictInt = Field(..., ge=1, le=500)
    time_zone: TimeZone
    # "HH:MM" in the company time zone.
    daily_check_time: CheckTime


class SettingsWrite(SettingsValues):
    # The version the editor started from; a stale one is refused (409).
    version: int


class SettingsRead(BaseModel):
    alert_steps: list[int]
    planning_horizon_days: int
    max_file_size_mb: int
    max_pdf_pages: int
    time_zone: str
    daily_check_time: str
    version: int
    updated_at: datetime


EDITABLE = tuple(SettingsValues.model_fields)
