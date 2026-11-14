"""The fleet, Positions and Document Types (FR-05, FR-07, T5).

- Vessels: administrators and crewing officers read; administrators create,
  edit, deactivate and reactivate. Vessels are never deleted.
- Positions and Document Types: all staff read (pickers, manager totals);
  administrators create, edit, retire, unretire and delete while unused.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.audit import audit_context_for
from app.deps import get_db, require_role
from app.models.auth import UserPayload
from app.models.reference import (
    DocumentTypeRead,
    DocumentTypeWrite,
    PositionRead,
    PositionWrite,
    VesselRead,
    VesselWrite,
)
from app.services import errors
from app.services import reference_data as svc
from app.services import responsible_officers
from app.services.reference_data import DOCUMENT_TYPE, POSITION, VESSEL, Table

admin_only = require_role("administrator")
fleet_readers = require_role("administrator", "crewing_officer")
all_staff = require_role("administrator", "crewing_officer", "manager")


@contextmanager
def _errors_as_http(table: Table) -> Iterator[None]:
    try:
        yield
    except errors.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such {table.label}.")
    except errors.Conflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except errors.Invalid as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


# --- Vessels ------------------------------------------------------------------

vessels = APIRouter(prefix="/vessels", tags=["vessels"])


@vessels.get("", response_model=list[VesselRead])
async def list_vessels(
    without_active_officer: bool = False,
    db: asyncpg.Connection = Depends(get_db),
    _: UserPayload = Depends(fleet_readers),
):
    """The fleet; `without_active_officer` keeps the vessels no active crewing
    officer is responsible for."""
    if without_active_officer:
        return await responsible_officers.vessels_without_active_officer(db)
    return await svc.list_rows(db, VESSEL)


@vessels.get("/{vessel_id}", response_model=VesselRead)
async def get_vessel(
    vessel_id: int,
    db: asyncpg.Connection = Depends(get_db),
    _: UserPayload = Depends(fleet_readers),
):
    with _errors_as_http(VESSEL):
        return await svc.get_row(db, VESSEL, vessel_id)


@vessels.post("", response_model=VesselRead, status_code=status.HTTP_201_CREATED)
async def create_vessel(
    body: VesselWrite,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    admin: UserPayload = Depends(admin_only),
):
    with _errors_as_http(VESSEL):
        return await svc.create(db, audit_context_for(request, admin), VESSEL, body.model_dump())


@vessels.put("/{vessel_id}", response_model=VesselRead)
async def edit_vessel(
    vessel_id: int,
    body: VesselWrite,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    admin: UserPayload = Depends(admin_only),
):
    with _errors_as_http(VESSEL):
        return await svc.edit(
            db, audit_context_for(request, admin), VESSEL, vessel_id, body.model_dump()
        )


@vessels.post("/{vessel_id}/deactivate", response_model=VesselRead)
async def deactivate_vessel(
    vessel_id: int,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    admin: UserPayload = Depends(admin_only),
):
    with _errors_as_http(VESSEL):
        return await svc.set_flag(
            db, audit_context_for(request, admin), VESSEL, vessel_id, False, "deactivated"
        )


@vessels.post("/{vessel_id}/reactivate", response_model=VesselRead)
async def reactivate_vessel(
    vessel_id: int,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    admin: UserPayload = Depends(admin_only),
):
    with _errors_as_http(VESSEL):
        return await svc.set_flag(
            db, audit_context_for(request, admin), VESSEL, vessel_id, True, "reactivated"
        )


# --- Positions and Document Types ------------------------------------------------


def _retirable_router(
    table: Table, prefix: str, write_model: type, read_model: type
) -> APIRouter:
    """List for all staff; create, edit, retire, unretire, delete for administrators."""
    router = APIRouter(prefix=prefix, tags=[table.name])

    @router.get("", response_model=list[read_model])
    async def list_all(
        db: asyncpg.Connection = Depends(get_db), _: UserPayload = Depends(all_staff)
    ):
        return await svc.list_rows(db, table)

    @router.post("", response_model=read_model, status_code=status.HTTP_201_CREATED)
    async def create(
        body: write_model,  # type: ignore[valid-type]
        request: Request,
        db: asyncpg.Connection = Depends(get_db),
        admin: UserPayload = Depends(admin_only),
    ):
        with _errors_as_http(table):
            return await svc.create(db, audit_context_for(request, admin), table, body.model_dump())

    @router.put("/{row_id}", response_model=read_model)
    async def edit(
        row_id: int,
        body: write_model,  # type: ignore[valid-type]
        request: Request,
        db: asyncpg.Connection = Depends(get_db),
        admin: UserPayload = Depends(admin_only),
    ):
        with _errors_as_http(table):
            return await svc.edit(
                db, audit_context_for(request, admin), table, row_id, body.model_dump()
            )

    @router.post("/{row_id}/retire", response_model=read_model)
    async def retire(
        row_id: int,
        request: Request,
        db: asyncpg.Connection = Depends(get_db),
        admin: UserPayload = Depends(admin_only),
    ):
        with _errors_as_http(table):
            return await svc.set_flag(
                db, audit_context_for(request, admin), table, row_id, True, "retired"
            )

    @router.post("/{row_id}/unretire", response_model=read_model)
    async def unretire(
        row_id: int,
        request: Request,
        db: asyncpg.Connection = Depends(get_db),
        admin: UserPayload = Depends(admin_only),
    ):
        with _errors_as_http(table):
            return await svc.set_flag(
                db, audit_context_for(request, admin), table, row_id, False, "unretired"
            )

    @router.delete("/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete(
        row_id: int,
        request: Request,
        db: asyncpg.Connection = Depends(get_db),
        admin: UserPayload = Depends(admin_only),
    ):
        with _errors_as_http(table):
            await svc.delete(db, audit_context_for(request, admin), table, row_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


positions = _retirable_router(POSITION, "/positions", PositionWrite, PositionRead)
document_types = _retirable_router(
    DOCUMENT_TYPE, "/document-types", DocumentTypeWrite, DocumentTypeRead
)
