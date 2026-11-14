"""Administrator-only account management (FR-02)."""

from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.audit import audit_context_for
from app.deps import get_db, require_role
from app.models.account import (
    AccountRead,
    ApproveAccount,
    ChangeRole,
    Deactivate,
    PendingCount,
    Reactivate,
)
from app.models.auth import UserPayload
from app.services import accounts
from app.services.accounts import AccountConflict, AccountNotFound

router = APIRouter(prefix="/accounts", tags=["accounts"])

admin_only = require_role("administrator")


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AccountNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.get("", response_model=list[AccountRead])
async def list_accounts(
    status_filter: Literal["pending", "active", "deactivated"] | None = Query(None, alias="status"),
    db: asyncpg.Connection = Depends(get_db),
    _: UserPayload = Depends(admin_only),
):
    return await accounts.list_accounts(db, status_filter)


@router.get("/pending-count", response_model=PendingCount)
async def pending_count(
    db: asyncpg.Connection = Depends(get_db),
    _: UserPayload = Depends(admin_only),
):
    return PendingCount(pending=await accounts.count_pending(db))


@router.post("/{account_id}/approve", response_model=AccountRead)
async def approve(
    account_id: UUID,
    body: ApproveAccount,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    admin: UserPayload = Depends(admin_only),
):
    try:
        return await accounts.approve(
            db, audit_context_for(request, admin), account_id, body.role, body.reason
        )
    except (AccountNotFound, AccountConflict) as exc:
        raise _http_error(exc)


@router.post("/{account_id}/role", response_model=AccountRead)
async def change_role(
    account_id: UUID,
    body: ChangeRole,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    admin: UserPayload = Depends(admin_only),
):
    try:
        return await accounts.change_role(
            db, audit_context_for(request, admin), account_id, body.role, body.reason
        )
    except (AccountNotFound, AccountConflict) as exc:
        raise _http_error(exc)


@router.post("/{account_id}/deactivate", response_model=AccountRead)
async def deactivate(
    account_id: UUID,
    body: Deactivate,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    admin: UserPayload = Depends(admin_only),
):
    try:
        return await accounts.deactivate(
            db, audit_context_for(request, admin), account_id, body.reason
        )
    except (AccountNotFound, AccountConflict) as exc:
        raise _http_error(exc)


@router.post("/{account_id}/reactivate", response_model=AccountRead)
async def reactivate(
    account_id: UUID,
    body: Reactivate,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    admin: UserPayload = Depends(admin_only),
):
    try:
        return await accounts.reactivate(
            db, audit_context_for(request, admin), account_id, body.reason, body.role
        )
    except (AccountNotFound, AccountConflict) as exc:
        raise _http_error(exc)
