"""Requirements (FR-08, T2, T5).

All staff read the matrix and the exceptions and evaluate the required set
for a (Position, Vessel or none) pair; administrators change them.
"""


import asyncpg
from fastapi import APIRouter, Depends, Response, status

from app.audit import AuditContext, acting_as
from app.deps import get_db, require_role
from app.models.auth import UserPayload
from app.models.requirements import (
    AddedToAllPositions,
    AddToAllPositions,
    Evaluation,
    MatrixCell,
    RequirementExceptionRead,
    RequirementExceptionWrite,
)
from app.refused_access import errors_as_http
from app.services import requirements as svc
from app.routers.params import Id

admin_ctx = acting_as("administrator")
all_staff = require_role("administrator", "crewing_officer", "manager")


# --- The matrix and the preview ----------------------------------------------------

matrix = APIRouter(prefix="/requirements", tags=["requirements"])


@matrix.get("", response_model=list[MatrixCell])
async def get_matrix(db: asyncpg.Connection = Depends(get_db), _: UserPayload = Depends(all_staff)):
    return await svc.get_matrix(db)


@matrix.get("/evaluate", response_model=Evaluation)
async def evaluate(
    position: int,
    vessel: int | None = None,
    db: asyncpg.Connection = Depends(get_db),
    _: UserPayload = Depends(all_staff),
):
    with errors_as_http():
        return await svc.evaluate(db, position, vessel)


@matrix.put("/{position_id}/{document_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def set_requirement(
    position_id: Id,
    document_type_id: Id,
    db: asyncpg.Connection = Depends(get_db),
    ctx: AuditContext = Depends(admin_ctx),
):
    with errors_as_http():
        await svc.set_requirement(db, ctx, position_id, document_type_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@matrix.delete("/{position_id}/{document_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_requirement(
    position_id: Id,
    document_type_id: Id,
    db: asyncpg.Connection = Depends(get_db),
    ctx: AuditContext = Depends(admin_ctx),
):
    await svc.clear_requirement(db, ctx, position_id, document_type_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@matrix.post("/add-to-all-positions", response_model=AddedToAllPositions)
async def add_to_all_positions(
    body: AddToAllPositions,
    db: asyncpg.Connection = Depends(get_db),
    ctx: AuditContext = Depends(admin_ctx),
):
    with errors_as_http():
        added = await svc.add_to_all_positions(
            db, ctx, body.document_type_id
        )
    return {"added": added}


# --- Exceptions --------------------------------------------------------------------

exceptions = APIRouter(prefix="/requirement-exceptions", tags=["requirements"])


@exceptions.get("", response_model=list[RequirementExceptionRead])
async def list_exceptions(
    db: asyncpg.Connection = Depends(get_db), _: UserPayload = Depends(all_staff)
):
    return await svc.list_exceptions(db)


@exceptions.post("", response_model=RequirementExceptionRead, status_code=status.HTTP_201_CREATED)
async def create_exception(
    body: RequirementExceptionWrite,
    db: asyncpg.Connection = Depends(get_db),
    ctx: AuditContext = Depends(admin_ctx),
):
    with errors_as_http():
        return await svc.create_exception(db, ctx, body.model_dump())


@exceptions.put("/{exception_id}", response_model=RequirementExceptionRead)
async def edit_exception(
    exception_id: Id,
    body: RequirementExceptionWrite,
    db: asyncpg.Connection = Depends(get_db),
    ctx: AuditContext = Depends(admin_ctx),
):
    with errors_as_http():
        return await svc.edit_exception(
            db, ctx, exception_id, body.model_dump()
        )


@exceptions.delete("/{exception_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exception(
    exception_id: Id,
    db: asyncpg.Connection = Depends(get_db),
    ctx: AuditContext = Depends(admin_ctx),
):
    with errors_as_http():
        await svc.delete_exception(db, ctx, exception_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
