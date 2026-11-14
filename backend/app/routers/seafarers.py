"""Seafarer records (FR-04, T3, T5).

Administrators and crewing officers, within their Scope; managers get 403.
There is no delete endpoint: a seafarer is set Inactive instead.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.audit import audit_context_for
from app.deps import get_db, require_role
from app.models.auth import UserPayload
from app.models.seafarer import SeafarerRead, SeafarerWrite, SetInactive
from app.refused_access import OutOfScope
from app.scope import seafarer_scope
from app.services import errors
from app.services import seafarers as svc

crew_staff = require_role("administrator", "crewing_officer")

router = APIRouter(prefix="/seafarers", tags=["seafarers"])


@contextmanager
def _errors_as_http() -> Iterator[None]:
    try:
        yield
    except errors.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    except errors.OutOfScope as exc:
        raise OutOfScope(exc.target_type, exc.target_id, seafarer_id=exc.seafarer_id)
    except errors.Conflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except errors.Invalid as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


@router.get("", response_model=list[SeafarerRead])
async def list_seafarers(
    search: str = Query("", max_length=200),
    show_inactive: bool = False,
    db: asyncpg.Connection = Depends(get_db),
    user: UserPayload = Depends(crew_staff),
):
    return await svc.list_seafarers(
        db, seafarer_scope(user), search=search, show_inactive=show_inactive
    )


@router.get("/{seafarer_id}", response_model=SeafarerRead)
async def get_seafarer(
    seafarer_id: int,
    db: asyncpg.Connection = Depends(get_db),
    user: UserPayload = Depends(crew_staff),
):
    with _errors_as_http():
        return await svc.get_seafarer(db, seafarer_scope(user), seafarer_id)


@router.post("", response_model=SeafarerRead, status_code=status.HTTP_201_CREATED)
async def create_seafarer(
    body: SeafarerWrite,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    user: UserPayload = Depends(crew_staff),
):
    with _errors_as_http():
        return await svc.create(db, audit_context_for(request, user), body.model_dump())


@router.put("/{seafarer_id}", response_model=SeafarerRead)
async def edit_seafarer(
    seafarer_id: int,
    body: SeafarerWrite,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    user: UserPayload = Depends(crew_staff),
):
    with _errors_as_http():
        return await svc.edit(
            db, audit_context_for(request, user), seafarer_scope(user), seafarer_id, body.model_dump()
        )


@router.post("/{seafarer_id}/set-inactive", response_model=SeafarerRead)
async def set_seafarer_inactive(
    seafarer_id: int,
    body: SetInactive,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    user: UserPayload = Depends(crew_staff),
):
    with _errors_as_http():
        return await svc.set_inactive(
            db, audit_context_for(request, user), seafarer_scope(user), seafarer_id, body.reason
        )


@router.post("/{seafarer_id}/reactivate", response_model=SeafarerRead)
async def reactivate_seafarer(
    seafarer_id: int,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    user: UserPayload = Depends(crew_staff),
):
    with _errors_as_http():
        return await svc.reactivate(
            db, audit_context_for(request, user), seafarer_scope(user), seafarer_id
        )
