"""The domain rules, as pure functions over plain rows (no database, no HTTP).

Queries fetch rows; these functions decide what they mean. Readiness, the
dashboard, the daily check and the reports share these functions.
"""

import calendar
from collections.abc import Collection, Iterable, Mapping, Set
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Literal, TypeVar
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


# --- Alerts and the daily check (FR-16; T6, T9) --------------------------------------


@dataclass(frozen=True)
class StepToRaise:
    """The Alert Step to raise and send, and the earlier steps reached with it
    that are stored as skipped (never sent)."""

    step: int
    skipped: tuple[int, ...]


def step_to_raise(
    expiry: date, today: date, steps: Iterable[int], already_raised: Collection[int]
) -> StepToRaise | None:
    """The most urgent Alert Step reached for this expiry date, unless it was
    raised already. A step is reached from `step` days before expiry on, so an
    expired document has reached every step. Steps reached late (missed runs,
    an upload already inside a window) send only the most urgent one; the
    other ones not raised yet are skipped, largest first. `already_raised` are
    the steps raised (or skipped) for this same Document and expiry date, so a
    renewal with a new expiry date starts over."""
    days_left = (expiry - today).days
    reached = sorted((s for s in set(steps) if days_left <= s), reverse=True)
    if not reached or reached[-1] in already_raised:
        return None
    *earlier, most_urgent = reached
    return StepToRaise(most_urgent, tuple(s for s in earlier if s not in already_raised))


def alert_is_open(alert_expiry: date, *, current_expiry: date | None, seafarer_inactive: bool) -> bool:
    """An Alert stays open while the seafarer isn't Inactive and the Document's
    Current Version still has the expiry date it was raised for. Nobody closes
    one by hand."""
    return not seafarer_inactive and current_expiry == alert_expiry


Recipient = TypeVar("Recipient")


def alert_recipients(
    vessel_ids: Iterable[int],
    active_officers: Mapping[int, Set[Recipient]],
    administrators: Set[Recipient],
) -> set[Recipient]:
    """Who is warned about a seafarer's document: the active Responsible
    Officers of every vessel the seafarer has an upcoming or under-way
    Assignment on. A Pool seafarer (no such vessel), or a vessel with no
    active officer, brings in the active administrators."""
    vessel_ids = list(vessel_ids)
    if not vessel_ids:
        return set(administrators)
    recipients: set[Recipient] = set()
    for vessel_id in vessel_ids:
        recipients |= active_officers.get(vessel_id) or administrators
    return recipients


def daily_check_due(local_now: datetime, check_time: time, ran_today: bool) -> bool:
    """The scheduled check runs once per local date, from the check time on;
    after downtime it catches up on the next wake-up the same day."""
    return not ran_today and local_now.time() >= check_time


@dataclass(frozen=True)
class RequirementRows:
    """The rows the required set is read from: the matrix as (position id,
    document type id) pairs, the exceptions and the retired types."""

    matrix: Collection[tuple[int, int]]
    exceptions: Collection[RequirementException]
    retired_types: Collection[int]

    def required(self, position_id: int, vessel: VesselRef | None) -> set[int]:
        return required_set(position_id, vessel, self.matrix, self.exceptions, self.retired_types)


# --- Coverage, missing documents and readiness (FR-17, FR-18, FR-19; T3, T4) --------------

CoverageClass = Literal["missing", "runs_out_before_start", "runs_out_during", "covers_all"]
ReadinessBucket = Literal["before_joining", "renewable_at_sea", "not_reviewed", "covers_all"]
READINESS_BUCKETS: tuple[ReadinessBucket, ...] = (
    "before_joining", "renewable_at_sea", "not_reviewed", "covers_all"
)


def coverage_class(
    start: date, end: date, current: Mapping[str, Any] | None
) -> CoverageClass:
    """How one required document stands against an Assignment from `start` to
    `end`, by its Current Version's expiry date E (valid through E). Only the
    expiry counts: not the issue date, the review or the verification, so a
    Version awaiting review counts too."""
    if current is None:
        return "missing"
    expiry = current["expiry_date"]
    if expiry is None or expiry >= end:
        return "covers_all"
    if expiry < start:
        return "runs_out_before_start"
    return "runs_out_during"


def evaluated_pair(
    held_position_id: int, assignments: Iterable[Mapping[str, Any]], today: date
) -> tuple[int, VesselRef | None]:
    """The (Position, Vessel) a seafarer's missing documents are read for: the
    Assignment under way's, otherwise the held Position with no vessel.
    Upcoming Assignments don't count."""
    under_way = current_assignment(assignments, today)
    if under_way is None:
        return held_position_id, None
    return under_way["position_id"], VesselRef(
        id=under_way["vessel_id"], flag=under_way["vessel_flag"]
    )


def missing_documents(
    held_position_id: int,
    assignments: Iterable[Mapping[str, Any]],
    today: date,
    requirements: RequirementRows,
    current_by_type: Mapping[int, Mapping[str, Any] | None],
) -> set[int]:
    """The required Document Types a seafarer has no Current Version of (no
    Document, or every Version rejected). Expiry is a separate signal."""
    position_id, vessel = evaluated_pair(held_position_id, assignments, today)
    return {
        type_id
        for type_id in requirements.required(position_id, vessel)
        if current_by_type.get(type_id) is None
    }


@dataclass(frozen=True)
class RequiredDocument:
    """One required Document Type of an Assignment and what the seafarer holds of it."""

    document_type_id: int
    name: str
    renewable_at_sea: bool
    document_id: int | None = None
    current_version: Mapping[str, Any] | None = None
    review_state: ReviewState | None = None
    verified: bool = False


def _advice(
    coverage: CoverageClass,
    expiry: date | None,
    *,
    renewable_at_sea: bool,
    under_way: bool,
    today: date,
) -> tuple[ReadinessBucket | None, str | None]:
    """T4's suggestion rule: the action bucket (1 or 2, None: covers all) and its text."""
    e = expiry.isoformat() if expiry else ""
    if coverage == "missing":
        return "before_joining", (
            "Obtain as soon as possible" if under_way else "Obtain before joining"
        )
    if coverage == "runs_out_before_start":
        return "before_joining", (
            f"Expired {e}, renew as soon as possible" if under_way
            else f"Renew before joining (runs out {e})"
        )
    if coverage == "runs_out_during":
        if under_way and expiry < today:
            # The class stays "runs out during"; only the advice changes.
            return "before_joining", f"Expired {e} while on board, renew now"
        if renewable_at_sea:
            return "renewable_at_sea", f"Can be renewed at sea, by {e}"
        return "before_joining", (
            f"Plan relief or port renewal before {e}" if under_way
            else "Renew before joining, not renewable at sea"
        )
    return None, None


def readiness(
    assignment: Mapping[str, Any], required: Iterable[RequiredDocument], today: date
) -> dict:
    """The advice-only readiness view of one upcoming or under-way Assignment.

    Each required document lands in (1) before joining, or (2) can be renewed
    at sea, or neither; one awaiting review is also listed in (3) not
    reviewed; (4) covers all holds everything in none of the first three.
    There is no overall verdict. `assignment` carries its dates and its own
    and the held Position (ids and names).
    """
    start, end = assignment["start_date"], assignment["end_date"]
    state = assignment_state(start, end, today)
    if state == "finished":
        raise ValueError("A finished Assignment has no readiness view.")
    under_way = state == "under_way"

    buckets: dict[ReadinessBucket, list[dict]] = {b: [] for b in READINESS_BUCKETS}
    for doc in sorted(required, key=lambda d: (d.name.lower(), d.document_type_id)):
        current = doc.current_version
        expiry = None if current is None else current["expiry_date"]
        coverage = coverage_class(start, end, current)
        bucket, suggestion = _advice(
            coverage, expiry, renewable_at_sea=doc.renewable_at_sea, under_way=under_way, today=today
        )
        entry = {
            "document_type_id": doc.document_type_id,
            "name": doc.name,
            "document_id": doc.document_id,
            "expiry_date": expiry,
            "coverage": coverage,
            "suggestion": suggestion,
            "review_state": doc.review_state,
            "verified": doc.verified,
        }
        awaiting_review = doc.review_state == "not_reviewed"
        if bucket is not None:
            buckets[bucket].append(entry)
        if awaiting_review:
            buckets["not_reviewed"].append(entry)
        if bucket is None and not awaiting_review:
            buckets["covers_all"].append(entry)

    position_notice = None
    if assignment["position_id"] != assignment["held_position_id"]:
        position_notice = (
            f"Assigned as {assignment['position_name']}; holds "
            f"{assignment['held_position_name']}. Requirements below are for "
            f"{assignment['position_name']}."
        )
    return {
        "state": state,
        "position_notice": position_notice,
        "before_joining_label": "Act now" if under_way else "Before joining",
        "counters": {b: len(buckets[b]) for b in READINESS_BUCKETS if b != "covers_all"},
        "buckets": buckets,
    }
