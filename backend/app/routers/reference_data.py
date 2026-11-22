"""The fleet, Positions and Document Types (FR-05, FR-07, T5).

- Vessels: administrators and crewing officers read; administrators create,
  edit, deactivate and reactivate. Vessels are never deleted.
- Positions and Document Types: all staff read (pickers, manager totals);
  administrators create, edit, retire, unretire and delete while unused.
"""

import asyncpg
from fastapi import APIRouter, Depends, Response, status

from app.audit import AuditContext, acting_as
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
from app.refused_access import errors_as_http
from app.routers.params import Id
from app.services import reference_data as svc
from app.services import responsible_officers
from app.services.reference_data import DOCUMENT_TYPE, POSITION, VESSEL, Table

admin_ctx = acting_as("administrator")
fleet_readers = require_role("administrator", "crewing_officer")
all_staff = require_role("administrator", "crewing_officer", "manager")

# (path, flag value, audit verb) for the flag each table switches.
ACTIVE_FLAG = (("deactivate", False, "deactivated"), ("reactivate", True, "reactivated"))
RETIRED_FLAG = (("retire", True, "retired"), ("unretire", False, "unretired"))


def _router(
    table: Table,
    prefix: str,
    write_model: type,
    read_model: type,
    flag_routes: tuple[tuple[str, bool, str], ...],
    deletable: bool,
) -> APIRouter:
    """Create, edit, switch the flag and (if `deletable`) delete, for administrators."""
    router = APIRouter(prefix=prefix, tags=[table.name])

    @router.post("", response_model=read_model, status_code=status.HTTP_201_CREATED)
    async def create(
        body: write_model,  # type: ignore[valid-type]
        db: asyncpg.Connection = Depends(get_db),
        ctx: AuditContext = Depends(admin_ctx),
    ):
        with errors_as_http():
            return await svc.create(db, ctx, table, body.model_dump())

    @router.put("/{row_id}", response_model=read_model)
    async def edit(
        row_id: Id,
        body: write_model,  # type: ignore[valid-type]
        db: asyncpg.Connection = Depends(get_db),
        ctx: AuditContext = Depends(admin_ctx),
    ):
        with errors_as_http():
            return await svc.edit(db, ctx, table, row_id, body.model_dump())

    for path, value, verb in flag_routes:
        _flag_route(router, table, read_model, path, value, verb)

    if deletable:

        @router.delete("/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
        async def delete(
            row_id: Id,
            db: asyncpg.Connection = Depends(get_db),
            ctx: AuditContext = Depends(admin_ctx),
        ):
            with errors_as_http():
                await svc.delete(db, ctx, table, row_id)
            return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


def _flag_route(
    router: APIRouter, table: Table, read_model: type, path: str, value: bool, verb: str
) -> None:
    # Its own function, so each route keeps its own `value` and `verb`.
    @router.post(f"/{{row_id}}/{path}", response_model=read_model, name=f"{path}_{table.name}")
    async def switch(
        row_id: Id,
        db: asyncpg.Connection = Depends(get_db),
        ctx: AuditContext = Depends(admin_ctx),
    ):
        with errors_as_http():
            return await svc.set_flag(db, ctx, table, row_id, value, verb)


# --- Vessels ------------------------------------------------------------------

vessels = _router(VESSEL, "/vessels", VesselWrite, VesselRead, ACTIVE_FLAG, deletable=False)


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
    vessel_id: Id,
    db: asyncpg.Connection = Depends(get_db),
    _: UserPayload = Depends(fleet_readers),
):
    with errors_as_http():
        return await svc.get_row(db, VESSEL, vessel_id)


# --- Positions and Document Types ------------------------------------------------


def _retirable_router(table: Table, prefix: str, write_model: type, read_model: type) -> APIRouter:
    router = _router(table, prefix, write_model, read_model, RETIRED_FLAG, deletable=True)

    @router.get("", response_model=list[read_model])
    async def list_all(
        db: asyncpg.Connection = Depends(get_db), _: UserPayload = Depends(all_staff)
    ):
        return await svc.list_rows(db, table)

    return router


positions = _retirable_router(POSITION, "/positions", PositionWrite, PositionRead)
document_types = _retirable_router(
    DOCUMENT_TYPE, "/document-types", DocumentTypeWrite, DocumentTypeRead
)
