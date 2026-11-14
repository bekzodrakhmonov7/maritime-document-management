"""Audit Log search and export (FR-23, T7, ADR 0002). Administrators only.

There are only read endpoints: nobody can edit or delete the log.
"""

from datetime import date, datetime, timezone
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response

from app.audit import AuditAction, Outcome, audit_context_for
from app.deps import get_db, require_role
from app.models.audit_log import MAX_PAGE_SIZE, AuditFilters, AuditPage
from app.models.auth import UserPayload
from app.services import audit_log as svc

router = APIRouter(prefix="/audit", tags=["audit"])

administrator = require_role("administrator")


def audit_filters(
    date_from: date | None = None,
    date_to: date | None = None,
    actor_id: UUID | None = None,
    actor_email: str | None = Query(None, max_length=320),
    action: list[AuditAction] = Query([]),
    seafarer_id: int | None = None,
    target_type: str | None = Query(None, max_length=100),
    target_id: str | None = Query(None, max_length=200),
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
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    filters: AuditFilters = Depends(audit_filters),
    db: asyncpg.Connection = Depends(get_db),
    admin: UserPayload = Depends(administrator),
):
    return await svc.search(db, audit_context_for(request, admin), filters, page, page_size)


@router.get("/export.csv")
async def export_audit_log(
    request: Request,
    filters: AuditFilters = Depends(audit_filters),
    db: asyncpg.Connection = Depends(get_db),
    admin: UserPayload = Depends(administrator),
) -> Response:
    result = await svc.export(db, audit_context_for(request, admin), filters)
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
