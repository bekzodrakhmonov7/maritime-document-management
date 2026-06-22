from pydantic import BaseModel, ConfigDict, Field


class VesselCreate(BaseModel):
    vessel_name: str = Field(..., min_length=1, max_length=255)
    imo_number: str = Field(..., pattern=r"^[0-9]{7}$")


class VesselUpdate(BaseModel):
    vessel_name: str | None = Field(None, min_length=1, max_length=255)
    imo_number: str | None = Field(None, pattern=r"^[0-9]{7}$")


class VesselRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vessel_id: int
    vessel_name: str
    imo_number: str
