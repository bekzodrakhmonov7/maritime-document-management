"""Assignments (FR-06, T3, T5).

Administrators and crewing officers, within their Scope; managers get 403.
Officers plan, edit and cancel only on vessels they are a Responsible Officer
for (403 otherwise, recorded). There is no delete: an Assignment is cancelled.
"""

import asyncpg
from fastapi import APIRouter, Depends, Request, status

from app.audit import audit_context_for
from app.deps import get_db
from app.models.assignment import (
    AssignmentCreate,
    AssignmentEdit,
    AssignmentRead,
    CancelAssignment,
)
from app.routers.crew_access import CrewAccess, errors_as_http, get_crew_access
from app.services import assignments as svc

router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.get("/{assignment_id}", response_model=AssignmentRead)
async def get_assignment(
    assignment_id: int,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.get(db, access.scope, assignment_id)


@router.post("", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
async def plan_assignment(
    body: AssignmentCreate,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.create(
            db, audit_context_for(request, access.user), access.scope, access.user,
            body.model_dump(),
        )


@router.put("/{assignment_id}", response_model=AssignmentRead)
async def edit_assignment(
    assignment_id: int,
    body: AssignmentEdit,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.edit(
            db, audit_context_for(request, access.user), access.scope, access.user,
            assignment_id, body.model_dump(),
        )


@router.post("/{assignment_id}/cancel", response_model=AssignmentRead)
async def cancel_assignment(
    assignment_id: int,
    body: CancelAssignment,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
):
    with errors_as_http():
        return await svc.cancel(
            db, audit_context_for(request, access.user), access.scope, access.user,
            assignment_id, body.reason,
        )
