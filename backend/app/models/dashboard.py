"""The dashboard's work queues and the managers' fleet totals (FR-20, T10)."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.domain import ActionHint, Breakdown, DashboardQueue, ExpiryStatus, ReviewState


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
    # The Current Version's uploader, who may not review it (FR-11).
    uploaded_by: UUID | None = None
    action: ActionHint


class SeafarerGroup(BaseModel):
    seafarer: DashboardSeafarer
    entries: list[QueueEntry]


class ReadinessCounters(BaseModel):
    before_joining: int
    renewable_at_sea: int
    expiry_not_stated: int
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
    expiry_not_stated: int
    waiting_for_review: int
    starting_soon: int
    in_order: int


class DashboardRead(BaseModel):
    """Every queue's count and one page of one queue (`queue`). Waiting for
    review overlaps the expiry queues."""

    today: date
    planning_horizon_days: int
    # Entries per queue, after the filters: every queue, whichever page is read.
    counts: QueueCounts
    queue: DashboardQueue
    offset: int
    limit: int
    # Items in the whole queue after the filters: seafarer groups for a
    # document queue, Assignments for starting soon.
    total: int
    # The page of a document queue: seafarers by name (empty for starting soon).
    groups: list[SeafarerGroup]
    # The page of starting soon: Assignments by start date (empty otherwise).
    assignments: list[StartingSoonEntry]


class StatusCounts(BaseModel):
    missing: int
    expired: int
    expiring_soon: int
    unexpired: int
    expiry_not_stated: int
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
