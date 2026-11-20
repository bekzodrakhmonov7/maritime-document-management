"""A vessel's people (FR-03, FR-06, T5): its Responsible Officers and its crew.

- Responsible Officers: administrators and crewing officers read;
  administrators add and remove links.
- Crew under way and upcoming: administrators and crewing officers, limited
  to the caller's Scope (an officer sees another vessel's page, not its crew).
"""

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Request, Response, status

from app.audit import audit_context_for
from app.deps import get_db, require_role
from app.models.assignment import AssignmentRead
from app.models.auth import UserPayload
from app.models.responsible_officer import AddResponsibleOfficer, ResponsibleOfficerRead
from app.routers.crew_access import CrewAccess, errors_as_http, get_crew_access
from app.services import assignments, responsible_officers as svc
from app.routers.params import Id

admin_only = require_role("administrator")
fleet_readers = require_role("administrator", "crewing_officer")

router = APIRouter(prefix="/vessels/{vessel_id}", tags=["vessels"])


@router.get("/crew", response_model=list[AssignmentRead])
async def list_crew(
    vessel_id: Id,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await assignments.list_for_vessel(db, access.scope, vessel_id)


@router.get("/responsible-officers", response_model=list[ResponsibleOfficerRead])
async def list_responsible_officers(
    vessel_id: Id,
    db: asyncpg.Connection = Depends(get_db),
    _: UserPayload = Depends(fleet_readers),
):
    with errors_as_http():
        return await svc.list_for_vessel(db, vessel_id)


@router.post(
    "/responsible-officers",
    response_model=list[ResponsibleOfficerRead],
    status_code=status.HTTP_201_CREATED,
)
async def add_responsible_officer(
    vessel_id: Id,
    body: AddResponsibleOfficer,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    admin: UserPayload = Depends(admin_only),
):
    with errors_as_http():
        return await svc.add(db, audit_context_for(request, admin), vessel_id, body.account_id)


@router.delete("/responsible-officers/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_responsible_officer(
    vessel_id: Id,
    account_id: UUID,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    admin: UserPayload = Depends(admin_only),
):
    with errors_as_http():
        await svc.remove(db, audit_context_for(request, admin), vessel_id, account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
