"""Alerts (FR-16, T6): open Alerts within Scope for administrators and
crewing officers (managers get 403), and the administrators' manual run of
the daily check."""

import asyncpg
from fastapi import APIRouter, Depends, Request

from app.audit import audit_context_for
from app.deps import get_db, require_role
from app.mail import Mailer, get_mailer
from app.models.alert import AlertCount, AlertRead, DailyCheckResult
from app.models.auth import UserPayload
from app.routers.crew_access import CrewAccess, get_crew_access
from app.services import alerts as svc
from app.services import daily_check

router = APIRouter(prefix="/alerts", tags=["alerts"])
admin = APIRouter(prefix="/admin/daily-check", tags=["alerts"])


@router.get("", response_model=list[AlertRead])
async def list_alerts(
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    return await svc.list_open(db, access.scope)


@router.get("/count", response_model=AlertCount)
async def count_alerts(
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    return AlertCount(open=await svc.count_open(db, access.scope))


@admin.post("/run", response_model=DailyCheckResult)
async def run_now(
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    user: UserPayload = Depends(require_role("administrator")),
    mailer: Mailer = Depends(get_mailer),
):
    """Run the check now. It doesn't count as the day's scheduled run."""
    result = await daily_check.run_manually(db, mailer, audit_context_for(request, user), user.sub)
    return result.as_dict()
