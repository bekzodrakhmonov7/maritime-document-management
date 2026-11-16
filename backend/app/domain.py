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


@dataclass(frozen=True)
class EffectiveExpiry:
    """The date a document is treated as valid through (FR-14, O1/T11).

    `expiry` is the Effective Expiry, `own_expiry` the Current Version's own
    date (which Alerts keep following). `capped_by` names the certificate's
    Document Type when its date is the earlier one; `missing_certificate`
    names it when an Endorsement has no certificate behind it, which counts as
    expired."""

    expiry: date | None
    own_expiry: date | None
    capped_by: str | None = None
    missing_certificate: str | None = None

    @property
    def certificate_missing(self) -> bool:
        return self.missing_certificate is not None

    def status(self, today: date, largest_step: int) -> ExpiryStatus:
        """The Expiry Status against the Effective Expiry."""
        if self.certificate_missing:
            return "expired"
        return expiry_status(self.expiry, today, largest_step)


def effective_expiry(
    document: Mapping[str, Any], certificate_current_version: Mapping[str, Any] | None
) -> EffectiveExpiry | None:
    """A Document's Effective Expiry, or None when it has no Current Version.

    For an Endorsement (`depends_on_id` set) it is the earlier of its own and
    its certificate's Current Version expiry date; a NULL own expiry takes the
    certificate's. The certificate's Current Version is already the newest
    one not rejected (awaiting review counts); with none, the Endorsement is
    treated as expired. Any other document keeps its own expiry date. There
    is no upload check: an Endorsement may expire after its certificate.
    """
    current = document["current_version"]
    if current is None:
        return None
    own = current["expiry_date"]
    if document.get("depends_on_id") is None:
        return EffectiveExpiry(expiry=own, own_expiry=own)
    certificate = document["certificate_type_name"]
    if certificate_current_version is None:
        return EffectiveExpiry(expiry=None, own_expiry=own, missing_certificate=certificate)
    cap = certificate_current_version["expiry_date"]
    if cap is not None and (own is None or cap < own):
        return EffectiveExpiry(expiry=cap, own_expiry=own, capped_by=certificate)
    return EffectiveExpiry(expiry=own, own_expiry=own)


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
    start: date,
    end: date,
    current: Mapping[str, Any] | None,
    effective: EffectiveExpiry | None = None,
) -> CoverageClass:
    """How one required document stands against an Assignment from `start` to
    `end`, by its Effective Expiry E (valid through E; the Current Version's
    own expiry date when `effective` isn't given). Runs out before start:
    E < start; runs out during: start <= E <= end; covers all: E > end or no
    expiry date. Covering all means outlasting the planned end date, because
    Assignments often end later than planned. Only the expiry counts: not
    the issue date, the review or the verification, so a Version awaiting
    review counts too. An Endorsement with no certificate runs out before
    start."""
    if current is None:
        return "missing"
    if effective is not None and effective.certificate_missing:
        return "runs_out_before_start"
    expiry = current["expiry_date"] if effective is None else effective.expiry
    if expiry is None or expiry > end:
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
    # The Current Version's Effective Expiry; None: its own expiry date counts.
    effective: EffectiveExpiry | None = None


def _certificate_advice(
    bucket: ReadinessBucket, effective: EffectiveExpiry, *, under_way: bool
) -> str | None:
    """The advice that names the certificate when it, not the Endorsement
    itself, is what limits it (FR-14), or None."""
    when = "as soon as possible" if under_way else "before joining"
    if effective.certificate_missing:
        return f"Obtain {effective.missing_certificate} {when} (certificate missing)"
    if effective.capped_by is None or effective.expiry is None:
        return None
    cap = effective.expiry.isoformat()
    if bucket == "renewable_at_sea":
        return f"Can be renewed at sea: renew {effective.capped_by} by {cap}"
    return f"Renew {effective.capped_by} {when} (endorsement capped at {cap})"


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
        current, effective = doc.current_version, doc.effective
        own = None if current is None else current["expiry_date"]
        expiry = own if effective is None else effective.expiry
        coverage = coverage_class(start, end, current, effective)
        bucket, suggestion = _advice(
            coverage, expiry, renewable_at_sea=doc.renewable_at_sea, under_way=under_way, today=today
        )
        if bucket is not None and effective is not None:
            suggestion = _certificate_advice(bucket, effective, under_way=under_way) or suggestion
        entry = {
            "document_type_id": doc.document_type_id,
            "name": doc.name,
            "document_id": doc.document_id,
            "expiry_date": own,
            "effective_expiry": expiry,
            "capped_by": None if effective is None else effective.capped_by,
            "certificate_missing": effective is not None and effective.certificate_missing,
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


# --- The dashboard (FR-20, T10) --------------------------------------------------------

DashboardQueue = Literal[
    "missing", "expired", "expiring_soon", "waiting_for_review", "starting_soon", "in_order"
]
DASHBOARD_QUEUES: tuple[DashboardQueue, ...] = (
    "missing", "expired", "expiring_soon", "waiting_for_review", "starting_soon", "in_order"
)
DOCUMENT_QUEUES: tuple[DashboardQueue, ...] = tuple(q for q in DASHBOARD_QUEUES if q != "starting_soon")
ActionHint = Literal["upload", "review", "open"]
_QUEUE_ACTIONS: dict[DashboardQueue, ActionHint] = {
    "missing": "upload",
    "expired": "upload",
    "expiring_soon": "upload",
    "waiting_for_review": "review",
    "in_order": "open",
}
TotalsColumn = Literal["missing", "expired", "expiring_soon", "unexpired", "no_expiry_date"]
TOTALS_COLUMNS: tuple[TotalsColumn, ...] = (
    "missing", "expired", "expiring_soon", "unexpired", "no_expiry_date"
)
Breakdown = Literal["vessel", "position", "document_type"]
ASHORE_UNASSIGNED = "Ashore / Unassigned"


@dataclass(frozen=True)
class DashboardSeafarer:
    """A seafarer as the dashboard groups by: held Position and Current Vessel
    (None: ashore)."""

    id: int
    first_name: str
    last_name: str
    position_id: int
    position_name: str
    current_vessel_id: int | None = None
    current_vessel_name: str | None = None
    inactive: bool = False


@dataclass(frozen=True)
class DocumentLine:
    """One of a seafarer's dashboard lines: a Document with a Current Version,
    or a required Document Type with none (`expiry_status` None: missing;
    `document_id` is set when every Version of it is rejected)."""

    seafarer_id: int
    document_type_id: int
    document_type_name: str
    document_id: int | None = None
    # The Current Version's own expiry date, and the Effective Expiry its
    # status follows (an Endorsement capped by its certificate, FR-14).
    expiry_date: date | None = None
    effective_expiry: date | None = None
    capped_by: str | None = None
    certificate_missing: bool = False
    expiry_status: ExpiryStatus | None = None
    review_state: ReviewState | None = None


@dataclass(frozen=True)
class StartingSoon:
    """An Assignment that may start soon, with its readiness counters."""

    assignment_id: int
    seafarer_id: int
    vessel_id: int
    vessel_name: str
    position_id: int
    position_name: str
    start_date: date
    end_date: date
    cancelled: bool
    counters: Mapping[str, int]


@dataclass(frozen=True)
class DashboardFilters:
    """The name text and click-to-add tags. Tags of one kind widen (any of
    them), kinds narrow each other. `ashore` is the "Ashore / Unassigned"
    vessel value: no Current Vessel."""

    name: str = ""
    position_ids: Set[int] = frozenset()
    vessel_ids: Set[int] = frozenset()
    ashore: bool = False
    document_type_ids: Set[int] = frozenset()
    show_inactive: bool = False

    def _person(self, s: DashboardSeafarer) -> bool:
        if s.inactive and not self.show_inactive:
            return False
        full_name = f"{s.first_name} {s.last_name}".lower()
        return all(word in full_name for word in self.name.lower().split())

    def _vessel(self, vessel_id: int | None, ashore_today: bool) -> bool:
        if not self.vessel_ids and not self.ashore:
            return True
        return vessel_id in self.vessel_ids or (self.ashore and ashore_today)

    def _position(self, position_id: int) -> bool:
        return not self.position_ids or position_id in self.position_ids

    def keeps_line(self, s: DashboardSeafarer, line: DocumentLine) -> bool:
        """A document line, by its seafarer's held Position and Current Vessel."""
        return (
            self._person(s)
            and self._position(s.position_id)
            and self._vessel(s.current_vessel_id, s.current_vessel_id is None)
            and (not self.document_type_ids or line.document_type_id in self.document_type_ids)
        )

    def keeps_joiner(self, s: DashboardSeafarer, a: StartingSoon) -> bool:
        """A starting-soon Assignment, by its own Position and vessel; "Ashore /
        Unassigned" keeps a joiner who is ashore today. Document Type tags
        don't apply: the counters are about the whole required set."""
        return (
            self._person(s)
            and self._position(a.position_id)
            and self._vessel(a.vessel_id, s.current_vessel_id is None)
        )


def document_queues(line: DocumentLine) -> tuple[DashboardQueue, ...]:
    """The work queues a line is in: missing, or its Expiry Status's queue
    (expired, expiring soon, or in order for unexpired and no expiry date),
    plus waiting for review when its Current Version has no Review yet."""
    if line.expiry_status is None:
        return ("missing",)
    expiry_queue: DashboardQueue = {
        "expired": "expired", "expiring_soon": "expiring_soon",
    }.get(line.expiry_status, "in_order")
    if line.review_state == "not_reviewed":
        return expiry_queue, "waiting_for_review"
    return (expiry_queue,)


def starts_soon(start: date, today: date, horizon_days: int) -> bool:
    """Upcoming (starts after today) and within the Planning Horizon."""
    return 0 < (start - today).days <= horizon_days


def _by_name(s: DashboardSeafarer) -> tuple[str, str, int]:
    return s.last_name.lower(), s.first_name.lower(), s.id


def _seafarer_fields(s: DashboardSeafarer) -> dict:
    return {
        "id": s.id,
        "first_name": s.first_name,
        "last_name": s.last_name,
        "position_id": s.position_id,
        "position_name": s.position_name,
        "current_vessel_id": s.current_vessel_id,
        "current_vessel_name": s.current_vessel_name,
        "inactive": s.inactive,
    }


def dashboard(
    seafarers: Iterable[DashboardSeafarer],
    lines: Iterable[DocumentLine],
    starting: Iterable[StartingSoon],
    filters: DashboardFilters,
    today: date,
    horizon_days: int,
) -> dict:
    """The work queues for the seafarers given (already the caller's Scope),
    each a list of seafarers by name with their entries, and their counts
    (entries, after the filters). Starting soon lists non-cancelled upcoming
    Assignments within the Planning Horizon by start date instead."""
    people = {s.id: s for s in seafarers}
    grouped: dict[DashboardQueue, dict[int, list[dict]]] = {q: {} for q in DOCUMENT_QUEUES}
    for line in sorted(lines, key=lambda l: (l.document_type_name.lower(), l.document_type_id)):
        s = people[line.seafarer_id]
        if not filters.keeps_line(s, line):
            continue
        for queue in document_queues(line):
            grouped[queue].setdefault(s.id, []).append({
                "document_type_id": line.document_type_id,
                "document_type_name": line.document_type_name,
                "document_id": line.document_id,
                "expiry_date": line.expiry_date,
                "effective_expiry": line.effective_expiry,
                "capped_by": line.capped_by,
                "certificate_missing": line.certificate_missing,
                "expiry_status": line.expiry_status,
                "review_state": line.review_state,
                "action": _QUEUE_ACTIONS[queue],
            })

    queues: dict[str, list[dict]] = {
        queue: [
            {"seafarer": _seafarer_fields(people[sid]), "entries": entries}
            for sid, entries in sorted(by_seafarer.items(), key=lambda i: _by_name(people[i[0]]))
        ]
        for queue, by_seafarer in grouped.items()
    }
    joiners = sorted(
        (
            a for a in starting
            if not a.cancelled
            and starts_soon(a.start_date, today, horizon_days)
            and filters.keeps_joiner(people[a.seafarer_id], a)
        ),
        key=lambda a: (a.start_date, *_by_name(people[a.seafarer_id]), a.assignment_id),
    )
    queues["starting_soon"] = [
        {
            "assignment_id": a.assignment_id,
            "seafarer": _seafarer_fields(people[a.seafarer_id]),
            "vessel_id": a.vessel_id,
            "vessel_name": a.vessel_name,
            "position_id": a.position_id,
            "position_name": a.position_name,
            "start_date": a.start_date,
            "end_date": a.end_date,
            "counters": dict(a.counters),
        }
        for a in joiners
    ]
    counts = {q: sum(len(g["entries"]) for g in queues[q]) for q in DOCUMENT_QUEUES}
    counts["starting_soon"] = len(joiners)
    return {"counts": {q: counts[q] for q in DASHBOARD_QUEUES}, "queues": queues}


def fleet_totals(
    seafarers: Iterable[DashboardSeafarer], lines: Iterable[DocumentLine], breakdown: Breakdown
) -> dict:
    """The managers' view: lines per Expiry Status plus Missing for the fleet
    (Inactive seafarers left out), and one breakdown table by Current Vessel
    ("Ashore / Unassigned" last), held Position or Document Type. No names
    of people, no review or starting-soon counts, no small-count suppression."""
    people = {s.id: s for s in seafarers}

    def row_key(s: DashboardSeafarer, line: DocumentLine) -> tuple[int | None, str]:
        if breakdown == "vessel":
            if s.current_vessel_id is None:
                return None, ASHORE_UNASSIGNED
            return s.current_vessel_id, s.current_vessel_name or ""
        if breakdown == "position":
            return s.position_id, s.position_name
        return line.document_type_id, line.document_type_name

    def empty() -> dict[str, int]:
        return dict.fromkeys(TOTALS_COLUMNS, 0)

    totals = empty()
    rows: dict[tuple[int | None, str], dict[str, int]] = {}
    for line in lines:
        s = people[line.seafarer_id]
        if s.inactive:
            continue
        column = line.expiry_status or "missing"
        totals[column] += 1
        rows.setdefault(row_key(s, line), empty())[column] += 1
    ordered = sorted(rows.items(), key=lambda r: (r[0][0] is None, r[0][1].lower(), r[0][0] or 0))
    return {
        "totals": totals,
        "breakdown": breakdown,
        "rows": [{"id": key[0], "name": key[1], "counts": counts} for key, counts in ordered],
    }
