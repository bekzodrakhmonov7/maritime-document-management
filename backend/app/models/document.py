from datetime import date

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
