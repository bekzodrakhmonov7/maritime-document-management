"""Requirements: the Position Requirement matrix and its exceptions (FR-08, T2)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints, model_validator

from app.models.reference import CountryCode
from app.models.text import NO_NUL

Reason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500), NO_NUL
]


class MatrixCell(BaseModel):
    position_id: int
    document_type_id: int


class AddToAllPositions(BaseModel):
    document_type_id: int


class AddedToAllPositions(BaseModel):
    # The Positions that got the requirement (those that already had it, and
    # retired ones, are left out).
    added: list[int]


class RequirementExceptionWrite(BaseModel):
    # The scope: exactly one of a vessel or a flag.
    vessel_id: int | None = None
    flag: CountryCode | None = None
    # None: every Position.
    position_id: int | None = None
    document_type_id: int
    effect: Literal["add", "remove"]
    reason: Reason

    @model_validator(mode="after")
    def exactly_one_scope(self) -> "RequirementExceptionWrite":
        if (self.vessel_id is None) == (self.flag is None):
            raise ValueError("give exactly one of a vessel or a flag")
        return self


class RequirementExceptionRead(BaseModel):
    id: int
    vessel_id: int | None
    vessel_name: str | None
    flag: str | None
    position_id: int | None
    position_name: str | None
    document_type_id: int
    document_type_name: str
    effect: Literal["add", "remove"]
    reason: str
    created_at: datetime
    updated_at: datetime


class EvaluatedVessel(BaseModel):
    id: int
    name: str
    flag: str


class RequiredType(BaseModel):
    id: int
    name: str
    # The exception that added it; None when it comes from the matrix.
    exception_id: int | None


class Evaluation(BaseModel):
    position_id: int
    vessel: EvaluatedVessel | None
    required: list[RequiredType]
    # The exceptions that decide a type for this pair (most specific wins).
    applied_exceptions: list[RequirementExceptionRead]
