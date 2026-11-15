"""Alerts and the daily check (FR-16)."""

from datetime import date, datetime

from pydantic import BaseModel


class AlertRead(BaseModel):
    id: int
    document_id: int
    seafarer_id: int
    seafarer_name: str
    document_type_name: str
    # The Alert Step raised: days before expiry.
    step: int
    expiry_date: date
    # Against today in the company time zone; negative once expired.
    days_left: int
    raised_at: datetime
    # The Current Version has no Review yet.
    awaiting_review: bool


class AlertCount(BaseModel):
    open: int


class DailyCheckResult(BaseModel):
    run_id: int
    local_date: date
    manual: bool
    raised: int
    skipped: int
    # Digests, one per recipient.
    sent: int
    failed: int


class ScheduledCheckResult(BaseModel):
    """The scheduled daily check: whether it ran, and its result if it did."""

    ran: bool
    result: DailyCheckResult | None = None
