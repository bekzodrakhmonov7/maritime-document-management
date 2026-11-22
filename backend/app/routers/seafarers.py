"""Seafarer records (FR-04, T3, T5).

Administrators and crewing officers, within their Scope; managers get 403.
There is no delete endpoint: a seafarer is set Inactive instead.
"""

from datetime import date
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, Query, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError


from app.deps import get_db
from app.models.assignment import AssignmentRead
from app.models.coverage import SeafarerRecord
from app.models.seafarer import SeafarerRead, SeafarerWrite, SetInactive
from app.models.text import NO_NUL
from app.refused_access import errors_as_http
from app.routers.crew_access import CrewAccess, get_crew_access
from app.services import assignments, coverage
from app.services import seafarers as svc
from app.routers.params import Id

router = APIRouter(prefix="/seafarers", tags=["seafarers"])


def _born_by(body: SeafarerWrite, today: date) -> dict:
    """The body's values, its date of birth not after `today` (company time
    zone); refused with the same 422 as any other invalid field."""
    try:
        return body.born_by(today).model_dump()
    except ValidationError as exc:
        errors = exc.errors(include_url=False, include_context=False)
        raise RequestValidationError([{**e, "loc": ("body", *e["loc"])} for e in errors])


@router.get("", response_model=list[SeafarerRead])
async def list_seafarers(
    search: Annotated[str, Query(max_length=200), NO_NUL] = "",
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
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.create(
            db, access.ctx, _born_by(body, access.scope.today)
        )


@router.put("/{seafarer_id}", response_model=SeafarerRead)
async def edit_seafarer(
    seafarer_id: Id,
    body: SeafarerWrite,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.edit(
            db, access.ctx, access.scope, seafarer_id,
            _born_by(body, access.scope.today),
        )


@router.post("/{seafarer_id}/set-inactive", response_model=SeafarerRead)
async def set_seafarer_inactive(
    seafarer_id: Id,
    body: SetInactive,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.set_inactive(
            db, access.ctx, access.scope, seafarer_id, body.reason
        )


@router.post("/{seafarer_id}/reactivate", response_model=SeafarerRead)
async def reactivate_seafarer(
    seafarer_id: Id,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.reactivate(
            db, access.ctx, access.scope, seafarer_id
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
