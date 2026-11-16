"""The dashboard's work queues and the managers' fleet totals (FR-20, T10)."""

from datetime import date

from pydantic import BaseModel

from app.domain import ActionHint, Breakdown, ExpiryStatus, ReviewState


class DashboardSeafarer(BaseModel):
    id: int
    first_name: str
    last_name: str
    position_id: int
    position_name: str
    # None: ashore today.
    current_vessel_id: int | None
    current_vessel_name: str | None
    inactive: bool


class QueueEntry(BaseModel):
    document_type_id: int
    document_type_name: str
    # None for a missing type with no Document; set when every Version is rejected.
    document_id: int | None
    # The Current Version's own expiry date.
    expiry_date: date | None
    # The Effective Expiry the status follows (FR-14); see DocumentSummary.
    effective_expiry: date | None
    capped_by: str | None
    certificate_missing: bool
    # None: missing (no Current Version).
    expiry_status: ExpiryStatus | None
    review_state: ReviewState | None
    action: ActionHint


class SeafarerGroup(BaseModel):
    seafarer: DashboardSeafarer
    entries: list[QueueEntry]


class ReadinessCounters(BaseModel):
    before_joining: int
    renewable_at_sea: int
    not_reviewed: int


class StartingSoonEntry(BaseModel):
    assignment_id: int
    seafarer: DashboardSeafarer
    vessel_id: int
    vessel_name: str
    position_id: int
    position_name: str
    start_date: date
    end_date: date
    counters: ReadinessCounters


class QueueCounts(BaseModel):
    missing: int
    expired: int
    expiring_soon: int
    waiting_for_review: int
    starting_soon: int
    in_order: int


class Queues(BaseModel):
    missing: list[SeafarerGroup]
    expired: list[SeafarerGroup]
    expiring_soon: list[SeafarerGroup]
    # Overlaps the expiry queues.
    waiting_for_review: list[SeafarerGroup]
    # By start date.
    starting_soon: list[StartingSoonEntry]
    in_order: list[SeafarerGroup]


class DashboardRead(BaseModel):
    today: date
    planning_horizon_days: int
    # Entries per queue, after the filters.
    counts: QueueCounts
    queues: Queues


class StatusCounts(BaseModel):
    missing: int
    expired: int
    expiring_soon: int
    unexpired: int
    no_expiry_date: int


class BreakdownRow(BaseModel):
    # None: the "Ashore / Unassigned" row of the vessel breakdown.
    id: int | None
    name: str
    counts: StatusCounts


class FleetTotalsRead(BaseModel):
    """Counts only: no names of people, no review or starting-soon counts."""

    today: date
    totals: StatusCounts
    breakdown: Breakdown
    rows: list[BreakdownRow]
