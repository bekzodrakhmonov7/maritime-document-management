"""Seafarer records (FR-04, T3, T5).

Administrators and crewing officers, within their Scope; managers get 403.
There is no delete endpoint: a seafarer is set Inactive instead.
"""

import asyncpg
from fastapi import APIRouter, Depends, Query, Request, status

from app.audit import audit_context_for
from app.deps import get_db
from app.models.assignment import AssignmentRead
from app.models.coverage import SeafarerRecord
from app.models.seafarer import SeafarerRead, SeafarerWrite, SetInactive
from app.routers.crew_access import CrewAccess, errors_as_http, get_crew_access
from app.services import assignments, coverage
from app.services import seafarers as svc
from app.routers.params import Id

router = APIRouter(prefix="/seafarers", tags=["seafarers"])


@router.get("", response_model=list[SeafarerRead])
async def list_seafarers(
    search: str = Query("", max_length=200),
    show_inactive: bool = False,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    return await svc.list_seafarers(
        db, access.scope, search=search, show_inactive=show_inactive
    )


@router.get("/{seafarer_id}", response_model=SeafarerRecord)
async def get_seafarer(
    seafarer_id: Id,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    """The record, with the required documents it has no Current Version of."""
    with errors_as_http():
        seafarer = await svc.get_seafarer(db, access.scope, seafarer_id)
    missing = await coverage.missing_documents(db, seafarer, access.scope.today)
    return {**seafarer, "missing_documents": missing}


@router.post("", response_model=SeafarerRead, status_code=status.HTTP_201_CREATED)
async def create_seafarer(
    body: SeafarerWrite,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.create(db, audit_context_for(request, access.user), body.model_dump())


@router.put("/{seafarer_id}", response_model=SeafarerRead)
async def edit_seafarer(
    seafarer_id: Id,
    body: SeafarerWrite,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.edit(
            db, audit_context_for(request, access.user), access.scope, seafarer_id, body.model_dump()
        )


@router.post("/{seafarer_id}/set-inactive", response_model=SeafarerRead)
async def set_seafarer_inactive(
    seafarer_id: Id,
    body: SetInactive,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.set_inactive(
            db, audit_context_for(request, access.user), access.scope, seafarer_id, body.reason
        )


@router.post("/{seafarer_id}/reactivate", response_model=SeafarerRead)
async def reactivate_seafarer(
    seafarer_id: Id,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.reactivate(
            db, audit_context_for(request, access.user), access.scope, seafarer_id
        )


@router.get("/{seafarer_id}/assignments", response_model=list[AssignmentRead])
async def list_seafarer_assignments(
    seafarer_id: Id,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    """The whole Assignment history, finished and cancelled ones included."""
    with errors_as_http():
        return await assignments.list_for_seafarer(db, access.scope, seafarer_id)
