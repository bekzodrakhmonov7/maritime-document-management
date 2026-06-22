from pydantic import BaseModel, ConfigDict, Field


class SeafarerCreate(BaseModel):
    vessel_id: int
    first_name: str = Field(..., min_length=1, max_length=255)
    last_name: str = Field(..., min_length=1, max_length=255)
    rank: str = Field(..., min_length=1, max_length=255)


class SeafarerUpdate(BaseModel):
    vessel_id: int | None = None
    first_name: str | None = Field(None, min_length=1, max_length=255)
    last_name: str | None = Field(None, min_length=1, max_length=255)
    rank: str | None = Field(None, min_length=1, max_length=255)


class SeafarerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seafarer_id: int
    vessel_id: int
    first_name: str
    last_name: str
    rank: str


class SeafarerWithVesselRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seafarer_id: int
    vessel_id: int
    first_name: str
    last_name: str
    rank: str
    vessel_name: str
