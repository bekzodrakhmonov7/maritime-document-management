"""Audit Log search and export (FR-23, T7)."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.audit import AuditAction, Outcome
from app.models.text import Text

MAX_PAGE_SIZE = 200


class AuditFilters(BaseModel):
    """One search of the Audit Log; every filter given must match."""

    date_from: date | None = None
    date_to: date | None = None
    actor_id: UUID | None = None
    actor_email: Text | None = None
    action: list[AuditAction] = []
    seafarer_id: int | None = None
    target_type: Text | None = None
    target_id: Text | None = None
    outcome: Outcome | None = None

    def given(self) -> dict[str, Any]:
        """The filters that were set, as plain values for the Audit Record."""
        return self.model_dump(mode="json", exclude_defaults=True)


class AuditRecordRead(BaseModel):
    id: int
    occurred_at: datetime
    actor_id: UUID | None
    actor_email: str | None
    actor_role: str | None
    action: str
    outcome: Outcome
    target_type: str | None
    target_id: str | None
    seafarer_id: int | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None
    ip: str | None
    request_id: str | None


class AuditPage(BaseModel):
    items: list[AuditRecordRead]
    total: int
    page: int
    page_size: int
    # The company time zone, for showing the timestamps.
    time_zone: str
