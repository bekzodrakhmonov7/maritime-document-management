"""Seafarer records (FR-04, T3)."""

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints, ValidationInfo, field_validator

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
    def born_in_the_past(cls, value: date | None, info: ValidationInfo) -> date | None:
        """Not after today in the company time zone. That date comes from
        Settings, so it is checked only when the caller passes it as the
        validation context `today` (`born_by`); never the server's own date."""
        today = (info.context or {}).get("today")
        if value is not None and (
            value < date(1900, 1, 1) or (today is not None and value > today)
        ):
            raise ValueError("must be a date in the past")
        return value

    def born_by(self, today: date) -> "SeafarerWrite":
        """This body validated again with the company's today as the upper
        bound of the date of birth; raises ValidationError like the parse."""
        return SeafarerWrite.model_validate(self.model_dump(), context={"today": today})


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
    # The vessel of the Assignment under way today; None means ashore.
    current_vessel_id: int | None
    current_vessel_name: str | None
    created_at: datetime
    updated_at: datetime
