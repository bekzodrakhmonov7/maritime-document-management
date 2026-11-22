"""Audit Log search and export (FR-23, T7, ADR 0002). Administrators only.

There are only read endpoints: nobody can edit or delete the log.
"""

from datetime import date, datetime, timezone
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.audit import AuditContext, acting_as, AuditAction, Outcome
from app.deps import get_db
from app.models.audit_log import MAX_PAGE_SIZE, AuditFilters, AuditPage
from app.models.text import NO_NUL
from app.routers.params import MAX_ID
from app.services import audit_log as svc

router = APIRouter(prefix="/audit", tags=["audit"])

admin_ctx = acting_as("administrator")


def audit_filters(
    date_from: date | None = None,
    date_to: date | None = None,
    actor_id: UUID | None = None,
    actor_email: Annotated[str | None, Query(max_length=320), NO_NUL] = None,
    action: list[AuditAction] = Query([]),
    seafarer_id: int | None = Query(None, ge=1, le=MAX_ID),
    target_type: Annotated[str | None, Query(max_length=100), NO_NUL] = None,
    target_id: Annotated[str | None, Query(max_length=200), NO_NUL] = None,
    outcome: Outcome | None = None,
) -> AuditFilters:
    """The search as query parameters; `action` may be given several times."""
    if date_from and date_to and date_to < date_from:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The end date can't be before the start date."
        )
    return AuditFilters(
        date_from=date_from,
        date_to=date_to,
        actor_id=actor_id,
        actor_email=(actor_email or "").strip() or None,
        action=list(dict.fromkeys(action)),
        seafarer_id=seafarer_id,
        target_type=target_type or None,
        target_id=target_id or None,
        outcome=outcome,
    )


@router.get("", response_model=AuditPage)
async def search_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    filters: AuditFilters = Depends(audit_filters),
    db: asyncpg.Connection = Depends(get_db),
    ctx: AuditContext = Depends(admin_ctx),
):
    return await svc.search(db, ctx, filters, page, page_size)


@router.get("/export.csv")
async def export_audit_log(
    filters: AuditFilters = Depends(audit_filters),
    db: asyncpg.Connection = Depends(get_db),
    ctx: AuditContext = Depends(admin_ctx),
) -> Response:
    result = await svc.export(db, ctx, filters)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=result.csv,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="audit-log-{stamp}.csv"',
            "X-Export-Rows": str(result.rows),
            "X-Export-Truncated": "true" if result.truncated else "false",
        },
    )
