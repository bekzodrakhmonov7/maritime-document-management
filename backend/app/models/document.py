"""Documents, Versions, Reviews and Verifications (FR-09 to FR-13, FR-15; T1, T2)."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, StringConstraints, field_validator, model_validator

from app.domain import ExpiryStatus, ReviewState
from app.upload_safety import ReasonCode

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class VersionDetails(BaseModel):
    """A Version's key details, sent with an upload or alone for a
    details-only Version. The Document Type's rules (expires, maximum
    validity) are checked by the service against the type."""

    document_number: Text
    issuing_authority: Text
    issue_date: date
    # None = no expiry date; required or refused by the Document Type.
    expiry_date: date | None = None

    @field_validator("expiry_date", mode="before")
    @classmethod
    def blank_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def check_expiry_after_issue(self) -> "VersionDetails":
        if self.expiry_date is not None and self.expiry_date <= self.issue_date:
            raise ValueError("expiry_date must be after issue_date")
        return self


Decision = Literal["accept", "reject"]
VerificationResult = Literal["confirmed", "not_confirmed"]
Comment = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ReviewWrite(BaseModel):
    decision: Decision
    comment: Comment


class ReviewRead(BaseModel):
    id: int
    decision: Decision
    comment: str
    reviewed_by: UUID
    reviewed_by_name: str
    reviewed_at: datetime


class VerificationDetails(BaseModel):
    """A Verification's details, sent as form fields next to the optional
    proof file. The date can't be after today in the company time zone (the
    service checks that)."""

    checked_on: date
    source: Text
    result: VerificationResult
    reference: Text


class VerificationRead(VerificationDetails):
    id: int
    recorded_by: UUID
    recorded_by_name: str
    recorded_at: datetime
    # Both None when no proof file was attached.
    proof_original_filename: str | None
    proof_content_type: str | None


class VersionRead(BaseModel):
    id: int
    # 1 for the first upload, counting up.
    number: int
    document_number: str
    issuing_authority: str
    issue_date: date
    expiry_date: date | None
    original_filename: str
    content_type: str
    uploaded_by: UUID
    uploaded_by_name: str
    uploaded_at: datetime
    is_current: bool
    # Set on a details-only Version: the earlier Version whose file it reuses.
    file_from_version_number: int | None
    # The latest Review decides; never "rejected" for the Current Version.
    review_state: ReviewState
    # Newest first.
    reviews: list[ReviewRead]
    verifications: list[VerificationRead]


class CurrentVersionSummary(BaseModel):
    id: int
    document_number: str
    issue_date: date
    expiry_date: date | None
    uploaded_at: datetime
    # "not_reviewed" shows the Not-reviewed tag.
    review_state: ReviewState


class DocumentSummary(BaseModel):
    """One row of a seafarer's documents table."""

    id: int
    seafarer_id: int
    document_type_id: int
    document_type_name: str
    document_type_retired: bool
    expires: bool
    max_validity_months: int | None
    created_at: datetime
    version_count: int
    # None when every Version is rejected: the Document counts as missing.
    current_version: CurrentVersionSummary | None
    # Against the Effective Expiry (FR-14): an Endorsement is capped by its
    # certificate, and counts as expired with none behind it.
    expiry_status: ExpiryStatus | None
    # The Effective Expiry: the Current Version's own expiry date, or for an
    # Endorsement the earlier of it and its certificate's. None with no
    # Current Version, no expiry date, or no certificate.
    effective_expiry: date | None
    # The certificate's Document Type when its date caps this Endorsement.
    capped_by: str | None
    # An Endorsement with no certificate behind it: counts as expired.
    certificate_missing: bool
    # The certificate's Document Type, set for an Endorsement.
    certificate_type_name: str | None
    # The Current Version's latest Verification is confirmed (never Reviewed).
    verified: bool


class DocumentRead(DocumentSummary):
    """A Document with its full history, newest Version first."""

    seafarer_first_name: str
    seafarer_last_name: str
    seafarer_inactive: bool
    versions: list[VersionRead]


class FileUrl(BaseModel):
    url: str
    expires_in: int
    filename: str
    content_type: str


class UploadRefusal(BaseModel):
    code: ReasonCode
    message: str
