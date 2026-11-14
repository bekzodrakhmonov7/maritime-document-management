"""Responsible Officer links (FR-03, T5)."""

from uuid import UUID

from pydantic import BaseModel

from app.models.auth import AccountStatus


class AddResponsibleOfficer(BaseModel):
    account_id: UUID


class ResponsibleOfficerRead(BaseModel):
    """A linked officer. A deactivated one keeps the link, ignored meanwhile."""

    id: UUID
    email: str
    full_name: str
    status: AccountStatus
