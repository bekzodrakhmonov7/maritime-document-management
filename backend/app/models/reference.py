"""Reference data: the fleet, Positions and Document Types (FR-05, FR-07, T2)."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, model_validator

from app.countries import ISO_3166_ALPHA2

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


def _assigned_country_code(value: str) -> str:
    code = value.strip().upper()
    if code not in ISO_3166_ALPHA2:
        raise ValueError("must be an ISO 3166-1 alpha-2 country code, e.g. MT")
    return code


# A country, e.g. a vessel's flag or a seafarer's nationality.
CountryCode = Annotated[str, AfterValidator(_assigned_country_code)]


class VesselWrite(BaseModel):
    name: Name
    imo_number: str = Field(..., pattern=r"^[0-9]{7}$")
    flag: CountryCode


class VesselRead(BaseModel):
    id: int
    name: str
    imo_number: str
    flag: str
    active: bool
    created_at: datetime
    updated_at: datetime


class PositionWrite(BaseModel):
    name: Name


class PositionRead(BaseModel):
    id: int
    name: str
    retired: bool
    created_at: datetime
    updated_at: datetime


class DocumentTypeWrite(BaseModel):
    name: Name
    expires: bool
    max_validity_months: int | None = Field(None, ge=1, le=1200)
    renewable_at_sea: bool = False
    # Set: this type is an Endorsement of that (expiring, non-Endorsement) type.
    depends_on_id: int | None = None

    @model_validator(mode="after")
    def max_validity_only_when_expires(self) -> "DocumentTypeWrite":
        if not self.expires and self.max_validity_months is not None:
            raise ValueError("a maximum validity is allowed only on a type that expires")
        return self


class DocumentTypeRead(BaseModel):
    id: int
    name: str
    expires: bool
    max_validity_months: int | None
    renewable_at_sea: bool
    depends_on_id: int | None
    retired: bool
    created_at: datetime
    updated_at: datetime
