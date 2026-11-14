"""The domain rules, as pure functions over plain rows (no database, no HTTP).

Queries fetch rows; these functions decide what they mean. Readiness, the
dashboard, the daily check and the reports share these functions; later
slices add coverage and the rest here.
"""

import calendar
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

AssignmentState = Literal["upcoming", "under_way", "finished"]
Effect = Literal["add", "remove"]
ExpiryStatus = Literal["unexpired", "expiring_soon", "expired", "no_expiry_date"]
ReviewState = Literal["not_reviewed", "accepted", "rejected"]


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


# --- Documents and Versions (FR-10, FR-15; T1, T2) ------------------------------------


def _latest_by_version(rows: Iterable[Mapping[str, Any]]) -> dict[int, Mapping[str, Any]]:
    """Each Version's latest row (the highest id) among its Reviews or Verifications."""
    latest: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        held = latest.get(row["version_id"])
        if held is None or row["id"] > held["id"]:
            latest[row["version_id"]] = row
    return latest


def _latest_for(version_id: int, rows: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """One Version's latest row (the highest id), or None when it has none."""
    return _latest_by_version(r for r in rows if r["version_id"] == version_id).get(version_id)


def review_state(version_id: int, reviews: Iterable[Mapping[str, Any]]) -> ReviewState:
    """A Version's latest Review decides: accepted, rejected, or not reviewed yet."""
    latest = _latest_for(version_id, reviews)
    if latest is None:
        return "not_reviewed"
    return "accepted" if latest["decision"] == "accept" else "rejected"


def current_version(
    versions: Iterable[Mapping[str, Any]], reviews: Iterable[Mapping[str, Any]]
) -> Mapping[str, Any] | None:
    """A Document's newest Version that is not rejected, reviewed or not.

    Each Version's latest Review (the highest id) is its decision, so a later
    Review overturns an earlier one. With every Version rejected (or none at
    all) the Document has no Current Version and counts as missing.
    """
    latest = _latest_by_version(reviews)
    candidates = [
        v for v in versions
        if v["id"] not in latest or latest[v["id"]]["decision"] != "reject"
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda v: (v["uploaded_at"], v["id"]))


def is_verified(
    current: Mapping[str, Any] | None, verifications: Iterable[Mapping[str, Any]]
) -> bool:
    """Verified: the Current Version's latest Verification (the highest id) is
    confirmed. A renewal is a new Version, so it is not Verified until it is
    checked again."""
    if current is None:
        return False
    latest = _latest_for(current["id"], verifications)
    return latest is not None and latest["result"] == "confirmed"


def expiry_status(expiry: date | None, today: date, largest_step: int) -> ExpiryStatus:
    """Where an expiry date stands today (company time zone). A document is
    valid through its expiry date and expired from the next day; it is
    expiring soon from the largest Alert Step down to the expiry day itself."""
    if expiry is None:
        return "no_expiry_date"
    days_left = (expiry - today).days
    if days_left < 0:
        return "expired"
    if days_left <= largest_step:
        return "expiring_soon"
    return "unexpired"


def latest_allowed_expiry(issue: date, max_validity_months: int) -> date:
    """Issue date plus whole months; a day the target month lacks becomes its last day."""
    months = issue.month - 1 + max_validity_months
    year, month = issue.year + months // 12, months % 12 + 1
    return date(year, month, min(issue.day, calendar.monthrange(year, month)[1]))


def version_dates_problem(
    issue: date, expiry: date | None, *, expires: bool, max_validity_months: int | None
) -> str | None:
    """Why a new Version's dates break its Document Type's rules, or None.
    Rules are checked only when a Version is created (T2)."""
    if expires and expiry is None:
        return "This document type expires, so the expiry date is required."
    if not expires and expiry is not None:
        return "This document type doesn't expire, so it takes no expiry date."
    if expiry is None:
        return None
    if expiry <= issue:
        return "The expiry date must be after the issue date."
    if max_validity_months is not None:
        latest = latest_allowed_expiry(issue, max_validity_months)
        if expiry > latest:
            return (
                f"The expiry date is past this type's maximum validity of "
                f"{max_validity_months} months (latest {latest.isoformat()})."
            )
    return None


# --- Requirements (FR-08, T2) ---------------------------------------------------


@dataclass(frozen=True)
class VesselRef:
    id: int
    flag: str


@dataclass(frozen=True)
class RequirementException:
    """An add or remove of one Document Type for one vessel or one flag
    (exactly one of the two), for one Position or, with none, for all."""

    document_type_id: int
    effect: Effect
    vessel_id: int | None = None
    flag: str | None = None
    position_id: int | None = None
    id: int | None = None


def deciding_exceptions(
    position_id: int, vessel: VesselRef | None, exceptions: Iterable[RequirementException]
) -> dict[int, RequirementException]:
    """For each Document Type an exception speaks about for this pair, the one
    that decides it: vessel beats flag, then Position-specific beats
    all-positions. With no vessel, none apply."""
    if vessel is None:
        return {}

    def rank(e: RequirementException) -> tuple[int, int] | None:
        if e.position_id is not None and e.position_id != position_id:
            return None
        if e.vessel_id is not None:
            if e.vessel_id != vessel.id:
                return None
            scope = 2
        elif e.flag == vessel.flag:
            scope = 1
        else:
            return None
        return scope, 1 if e.position_id is not None else 0

    deciding: dict[int, tuple[tuple[int, int], RequirementException]] = {}
    for e in exceptions:
        r = rank(e)
        if r is None:
            continue
        held = deciding.get(e.document_type_id)
        if held is None or r > held[0]:
            deciding[e.document_type_id] = (r, e)
    return {type_id: e for type_id, (_, e) in deciding.items()}


def required_set(
    position_id: int,
    vessel: VesselRef | None,
    matrix: Iterable[tuple[int, int]],
    exceptions: Iterable[RequirementException],
    retired_types: Collection[int],
) -> set[int]:
    """The Document Types required for a Position, on a vessel or ashore.

    Starts from the matrix rows (position id, document type id) for the
    Position, then applies flag exceptions, then vessel exceptions; the most
    specific one decides each type. Retired types are never required, and an
    Endorsement's certificate is never followed either way.
    """
    required = {type_id for p, type_id in matrix if p == position_id}
    for type_id, e in deciding_exceptions(position_id, vessel, exceptions).items():
        if e.effect == "add":
            required.add(type_id)
        else:
            required.discard(type_id)
    return required - set(retired_types)
