from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
import io

from app.deps import get_db, require_role
from app.models.auth import UserPayload
from app.models.report import FleetSummary, MissingDocRow
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/missing-mandatory", response_model=list[MissingDocRow])
async def get_missing_mandatory_documents(
    current_user: Annotated[UserPayload, Depends(require_role("administrator", "crewing_officer"))],
    db: asyncpg.Connection = Depends(get_db),
) -> list[MissingDocRow]:
    return await report_service.missing_mandatory_documents(db)


@router.get("/fleet-summary", response_model=FleetSummary)
async def get_fleet_summary(
    current_user: Annotated[UserPayload, Depends(require_role("administrator", "crewing_officer"))],
    db: asyncpg.Connection = Depends(get_db),
) -> FleetSummary:
    return await report_service.fleet_compliance_summary(db)


@router.get("/export.csv")
async def export_csv(
    current_user: Annotated[UserPayload, Depends(require_role("administrator", "crewing_officer"))],
    db: asyncpg.Connection = Depends(get_db),
):
    rows = await report_service.missing_mandatory_documents(db)
    return report_service.export_csv(rows)


@router.get("/export.pdf")
async def export_pdf(
    current_user: Annotated[UserPayload, Depends(require_role("administrator", "crewing_officer"))],
    db: asyncpg.Connection = Depends(get_db),
):
    summary = await report_service.fleet_compliance_summary(db)
    pdf_bytes = report_service.export_pdf(summary)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=fleet_summary.pdf"},
    )
