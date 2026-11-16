"""Missing documents and the readiness view (FR-17, FR-18, FR-19; T3, T4)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.domain import CoverageClass, ReviewState
from app.models.assignment import AssignmentRead
from app.models.seafarer import SeafarerRead


class MissingDocument(BaseModel):
    document_type_id: int
    name: str
    # Set when a Document exists but every Version of it is rejected.
    document_id: int | None


class SeafarerRecord(SeafarerRead):
    """A seafarer's own record, with the required documents it has no Current Version of."""

    missing_documents: list[MissingDocument]


class ReadinessEntry(BaseModel):
    document_type_id: int
    name: str
    document_id: int | None
    # The Current Version's own expiry date.
    expiry_date: date | None
    # What coverage reads (FR-14): for an Endorsement capped by its certificate,
    # the certificate's earlier date; None with no certificate behind it.
    effective_expiry: date | None
    # The certificate's Document Type when its date caps this Endorsement.
    capped_by: str | None
    # An Endorsement with no certificate behind it: runs out before start.
    certificate_missing: bool
    coverage: CoverageClass
    # T4's advisory renewal suggestion; None when the document covers all.
    suggestion: str | None
    review_state: ReviewState | None
    # A badge only: verification has no bucket and no suggestion.
    verified: bool


class ReadinessAssignment(AssignmentRead):
    vessel_flag: str
    held_position_name: str


class ReadinessCounters(BaseModel):
    before_joining: int
    renewable_at_sea: int
    not_reviewed: int


class ReadinessBuckets(BaseModel):
    before_joining: list[ReadinessEntry]
    renewable_at_sea: list[ReadinessEntry]
    # Can overlap the first two: awaiting review still counts toward coverage.
    not_reviewed: list[ReadinessEntry]
    covers_all: list[ReadinessEntry]


class ReadinessRead(BaseModel):
    """Advice only: it approves and blocks nothing, and gives no overall verdict."""

    assignment: ReadinessAssignment
    state: Literal["upcoming", "under_way"]
    # Set when the Assignment's Position differs from the held one.
    position_notice: str | None
    # "Before joining", or "Act now" when under way.
    before_joining_label: str
    counters: ReadinessCounters
    buckets: ReadinessBuckets
