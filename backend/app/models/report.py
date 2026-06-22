from pydantic import BaseModel, ConfigDict, computed_field


class MissingDocRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seafarer_id: int
    first_name: str
    last_name: str
    rank: str
    vessel_name: str
    doc_type_id: int
    type_name: str

    @computed_field
    @property
    def seafarer_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @computed_field
    @property
    def doc_type_name(self) -> str:
        return self.type_name


class VesselComplianceRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vessel_id: int
    vessel_name: str
    total_seafarers: int = 0
    total_documents: int = 0
    valid_count: int
    expiring_soon_count: int
    expired_count: int
    missing_count: int

    @computed_field
    @property
    def valid(self) -> int:
        return self.valid_count

    @computed_field
    @property
    def expiring_soon(self) -> int:
        return self.expiring_soon_count

    @computed_field
    @property
    def expired(self) -> int:
        return self.expired_count

    @computed_field
    @property
    def missing_mandatory(self) -> int:
        return self.missing_count

    @computed_field
    @property
    def compliance_percentage(self) -> int:
        if self.total_documents == 0:
            return 0
        return int((self.valid_count / self.total_documents) * 100)


class FleetSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vessels: list[VesselComplianceRow]
    total_valid: int
    total_expiring_soon: int
    total_expired: int
    total_missing: int

    @computed_field
    @property
    def fleet_total_seafarers(self) -> int:
        return sum(v.total_seafarers for v in self.vessels)

    @computed_field
    @property
    def fleet_total_documents(self) -> int:
        return sum(v.total_documents for v in self.vessels)

    @computed_field
    @property
    def fleet_valid(self) -> int:
        return self.total_valid

    @computed_field
    @property
    def fleet_expiring_soon(self) -> int:
        return self.total_expiring_soon

    @computed_field
    @property
    def fleet_expired(self) -> int:
        return self.total_expired

    @computed_field
    @property
    def fleet_missing_mandatory(self) -> int:
        return self.total_missing

    @computed_field
    @property
    def fleet_compliance_percentage(self) -> int:
        if self.fleet_total_documents == 0:
            return 0
        return int((self.total_valid / self.fleet_total_documents) * 100)
