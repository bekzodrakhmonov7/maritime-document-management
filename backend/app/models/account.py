from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from app.models.auth import AccountStatus, Role

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class AccountRead(BaseModel):
    id: UUID
    email: str
    full_name: str
    status: AccountStatus
    role: Role | None
    status_reason: str | None
    status_changed_at: datetime | None
    created_at: datetime


class PendingCount(BaseModel):
    pending: int


class ApproveAccount(BaseModel):
    role: Role
    reason: Reason
    # A crewing officer's vessels (Responsible Officer links); may be empty,
    # leaving the Unassigned Pool only.
    vessel_ids: list[int] = Field(default_factory=list, max_length=500)


class ChangeRole(BaseModel):
    role: Role
    reason: Reason


class Deactivate(BaseModel):
    reason: Reason


class SecondFactorReset(BaseModel):
    reason: Reason


class Reactivate(BaseModel):
    reason: Reason
    # Needed only when the account never had a role (a rejected sign-up).
    role: Role | None = None


class Me(BaseModel):
    id: UUID
    email: str
    full_name: str
    status: AccountStatus
    role: Role | None
