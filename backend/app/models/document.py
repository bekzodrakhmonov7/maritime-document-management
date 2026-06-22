from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class DocumentCreate(BaseModel):
    doc_type_id: int
    seafarer_id: int
    document_number: str = Field(..., min_length=1)
    issue_date: date
    expiry_date: date

    @model_validator(mode="after")
    def check_expiry_after_issue(self) -> "DocumentCreate":
        if self.expiry_date <= self.issue_date:
            raise ValueError("expiry_date must be after issue_date")
        return self


class DocumentRead(BaseModel):
    document_id: int
    seafarer_id: int
    doc_type_id: int
    document_number: str
    issue_date: date
    expiry_date: date
    status: Literal["pending", "verified", "rejected", "expiring_soon", "expired"]
    file_path: str
    uploaded_by: UUID | None = None
    created_at: datetime | None = None
    signed_url: str | None = None


class DocumentVerify(BaseModel):
    status: str
