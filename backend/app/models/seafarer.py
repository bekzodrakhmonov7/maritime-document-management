"""Seafarer records (FR-04, T3)."""

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

from app.models.reference import CountryCode

PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class SeafarerWrite(BaseModel):
    """Create and edit share the full body: personal details and held Position."""

    first_name: PersonName
    last_name: PersonName
    date_of_birth: date | None = None
    nationality: CountryCode | None = None
    # Must be a non-retired Position from the managed list.
    position_id: int

    @field_validator("date_of_birth")
    @classmethod
    def born_in_the_past(cls, value: date | None) -> date | None:
        if value is not None and not date(1900, 1, 1) <= value <= date.today():
            raise ValueError("must be a date in the past")
        return value


class SetInactive(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class SeafarerRead(BaseModel):
    id: int
    first_name: str
    last_name: str
    date_of_birth: date | None
    nationality: str | None
    position_id: int
    position_name: str
    position_retired: bool
    inactive_since: datetime | None
    inactive_reason: str | None
    created_at: datetime
    updated_at: datetime
