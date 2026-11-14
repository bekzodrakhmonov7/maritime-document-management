"""Assignments (FR-06, T3)."""

from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

# Upcoming / under way / finished come from the dates; cancelled is stored.
AssignmentStatus = Literal["upcoming", "under_way", "finished", "cancelled"]


class AssignmentEdit(BaseModel):
    """What an edit may change. The seafarer is not among it: a different
    person means cancelling and planning a new Assignment."""

    model_config = ConfigDict(extra="forbid")

    vessel_id: int
    position_id: int
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def end_not_before_start(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("the end date can't be before the start date")
        return self


class AssignmentCreate(AssignmentEdit):
    seafarer_id: int


class CancelAssignment(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class AssignmentRead(BaseModel):
    id: int
    seafarer_id: int
    seafarer_first_name: str
    seafarer_last_name: str
    vessel_id: int
    vessel_name: str
    position_id: int
    position_name: str
    # Advisory only: the Assignment's Position differs from the held one.
    position_differs: bool
    start_date: date
    end_date: date
    state: AssignmentStatus
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime
    updated_at: datetime
