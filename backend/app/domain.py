"""The domain rules, as pure functions over plain rows (no database, no HTTP).

Queries fetch rows; these functions decide what they mean. Later slices add
Current Version, Expiry Status, the required set, coverage and the rest here.
"""

from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

AssignmentState = Literal["upcoming", "under_way", "finished"]


def today_in(time_zone: str, now: datetime | None = None) -> date:
    """Today's calendar date in the company time zone (Settings)."""
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(time_zone)).date()


def assignment_state(start: date, end: date, today: date) -> AssignmentState:
    """An Assignment by its dates: both the start and the end day are under way."""
    if today < start:
        return "upcoming"
    if today > end:
        return "finished"
    return "under_way"


def current_assignment(
    assignments: Iterable[Mapping[str, Any]], today: date
) -> Mapping[str, Any] | None:
    """The seafarer's non-cancelled Assignment under way today; its vessel is
    the Current Vessel. None means the seafarer is ashore. Non-cancelled
    Assignments never overlap, so there is at most one."""
    for row in assignments:
        if row["cancelled_at"] is None and (
            assignment_state(row["start_date"], row["end_date"], today) == "under_way"
        ):
            return row
    return None
