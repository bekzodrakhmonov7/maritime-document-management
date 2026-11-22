"""Administrator-only account management (FR-02, SR-03)."""

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.audit import AuditContext, acting_as
from app.deps import get_db, require_role
from app.models.account import (
    AccountRead,
    ApproveAccount,
    ChangeRole,
    Deactivate,
    PendingCount,
    Reactivate,
    SecondFactorReset,
)
from app.models.auth import AccountStatus, UserPayload
from app.services import accounts
from app.refused_access import errors_as_http
from app.supabase_auth import AuthUnavailable, SignInRefused, SupabaseAuth, get_supabase_auth

router = APIRouter(prefix="/accounts", tags=["accounts"])

admin_only = require_role("administrator")
admin_ctx = acting_as("administrator")


@router.get("", response_model=list[AccountRead])
async def list_accounts(
    status_filter: AccountStatus | None = Query(None, alias="status"),
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
    db: asyncpg.Connection = Depends(get_db),
    ctx: AuditContext = Depends(admin_ctx),
):
    with errors_as_http():
        return await accounts.approve(
            db, ctx, account_id, body.role, body.reason,
            body.vessel_ids,
        )


@router.post("/{account_id}/role", response_model=AccountRead)
async def change_role(
    account_id: UUID,
    body: ChangeRole,
    db: asyncpg.Connection = Depends(get_db),
    ctx: AuditContext = Depends(admin_ctx),
):
    with errors_as_http():
        return await accounts.change_role(
            db, ctx, account_id, body.role, body.reason
        )


@router.post("/{account_id}/deactivate", response_model=AccountRead)
async def deactivate(
    account_id: UUID,
    body: Deactivate,
    db: asyncpg.Connection = Depends(get_db),
    ctx: AuditContext = Depends(admin_ctx),
):
    with errors_as_http():
        return await accounts.deactivate(
            db, ctx, account_id, body.reason
        )


@router.post("/{account_id}/reactivate", response_model=AccountRead)
async def reactivate(
    account_id: UUID,
    body: Reactivate,
    db: asyncpg.Connection = Depends(get_db),
    ctx: AuditContext = Depends(admin_ctx),
):
    with errors_as_http():
        return await accounts.reactivate(
            db, ctx, account_id, body.reason, body.role
        )


@router.post("/{account_id}/second-factor/reset", response_model=AccountRead)
async def reset_second_factor(
    account_id: UUID,
    body: SecondFactorReset,
    db: asyncpg.Connection = Depends(get_db),
    ctx: AuditContext = Depends(admin_ctx),
    supabase_auth: SupabaseAuth = Depends(get_supabase_auth),
):
    """A lost authenticator: the Account enrols a new one at its next sign-in."""

    async def remove_factors(user_id: UUID) -> None:
        try:
            await supabase_auth.delete_factors(str(user_id))
        except (AuthUnavailable, SignInRefused):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                {"code": "auth_unavailable", "message": "Supabase Auth is unavailable. Try again later."},
            )

    with errors_as_http():
        return await accounts.reset_second_factor(db, ctx, account_id, body.reason, remove_factors)
