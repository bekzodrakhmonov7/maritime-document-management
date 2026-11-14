"""The dashboard (FR-20; T5, T10).

`GET /dashboard`: the work queues for administrators and crewing officers,
within their Scope (managers get 403). `GET /dashboard/totals`: the fleet
totals with no names, for managers and administrators. Plain reads: nothing
is recorded except refused access.
"""

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.deps import get_db, require_role
from app.domain import Breakdown, DashboardFilters
from app.models.auth import UserPayload
from app.models.dashboard import DashboardRead, FleetTotalsRead
from app.routers.crew_access import CrewAccess, get_crew_access
from app.services import dashboard as svc
from app.services.settings import company_today

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardRead)
async def get_dashboard(
    name: str = Query("", max_length=200),
    position_id: list[int] = Query([]),
    vessel_id: list[int] = Query([]),
    # The "Ashore / Unassigned" vessel value.
    ashore: bool = False,
    document_type_id: list[int] = Query([]),
    show_inactive: bool = False,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    filters = DashboardFilters(
        name=name,
        position_ids=frozenset(position_id),
        vessel_ids=frozenset(vessel_id),
        ashore=ashore,
        document_type_ids=frozenset(document_type_id),
        show_inactive=show_inactive,
    )
    return await svc.dashboard(db, access.scope, filters)


@router.get("/totals", response_model=FleetTotalsRead)
async def get_totals(
    breakdown: Breakdown = "vessel",
    db: asyncpg.Connection = Depends(get_db),
    _: UserPayload = Depends(require_role("manager", "administrator")),
):
    return await svc.fleet_totals(db, await company_today(db), breakdown)
