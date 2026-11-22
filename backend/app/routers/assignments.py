"""Assignments (FR-06, T3, T5).

Administrators and crewing officers, within their Scope; managers get 403.
Officers plan, edit and cancel only on vessels they are a Responsible Officer
for (403 otherwise, recorded). There is no delete: an Assignment is cancelled.
"""

import asyncpg
from fastapi import APIRouter, Depends, status


from app.deps import get_db
from app.models.assignment import (
    AssignmentCreate,
    AssignmentEdit,
    AssignmentRead,
    CancelAssignment,
)
from app.models.coverage import ReadinessRead
from app.refused_access import errors_as_http
from app.routers.crew_access import CrewAccess, get_crew_access
from app.services import assignments as svc
from app.services import coverage
from app.routers.params import Id

router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.get("/{assignment_id}", response_model=AssignmentRead)
async def get_assignment(
    assignment_id: Id,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.get(db, access.scope, assignment_id)


@router.get("/{assignment_id}/readiness", response_model=ReadinessRead)
async def get_readiness(
    assignment_id: Id,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    """Advice only, for upcoming and under-way Assignments; finished and
    cancelled ones have none (404)."""
    with errors_as_http():
        return await coverage.readiness(db, access.scope, assignment_id)


@router.post("", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
async def plan_assignment(
    body: AssignmentCreate,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.create(
            db, access.ctx, access.scope, access.user,
            body.model_dump(),
        )


@router.put("/{assignment_id}", response_model=AssignmentRead)
async def edit_assignment(
    assignment_id: Id,
    body: AssignmentEdit,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.edit(
            db, access.ctx, access.scope, access.user,
            assignment_id, body.model_dump(),
        )


@router.post("/{assignment_id}/cancel", response_model=AssignmentRead)
async def cancel_assignment(
    assignment_id: Id,
    body: CancelAssignment,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.cancel(
            db, access.ctx, access.scope, access.user,
            assignment_id, body.reason,
        )
