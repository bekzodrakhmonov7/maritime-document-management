"""Documents and Versions (FR-09, FR-10, FR-13, FR-15; T1, T2)."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, StringConstraints, field_validator, model_validator

from app.domain import ExpiryStatus

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


class CurrentVersionSummary(BaseModel):
    id: int
    document_number: str
    issue_date: date
    expiry_date: date | None
    uploaded_at: datetime


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
    expiry_status: ExpiryStatus | None


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
    code: Literal[
        "too_large", "unsupported_type", "type_mismatch", "corrupt",
        "pdf_active_content", "pdf_encrypted", "too_many_pages", "image_too_large",
    ]
    message: str
