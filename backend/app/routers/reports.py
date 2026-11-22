"""Status Reports (FR-21, T12): an assignment report and a vessel report, each
as PDF or CSV.

Administrators download any report; crewing officers only within Scope (404
outside, recorded); managers get 403. Every generated report is audited.
"""

import asyncpg
from fastapi import APIRouter, Depends, Query, Response


from app.deps import get_db
from app.reports import ReportFormat
from app.refused_access import errors_as_http
from app.routers.crew_access import CrewAccess, get_crew_access
from app.services import reports as svc
from app.services.reports import RenderedReport
from app.routers.params import Id

router = APIRouter(tags=["reports"])


def _download(report: RenderedReport) -> Response:
    return Response(
        content=report.content,
        media_type=report.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{report.filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/assignments/{assignment_id}/report")
async def assignment_report(
    assignment_id: Id,
    format: ReportFormat = Query(...),
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
) -> Response:
    """The readiness view of one upcoming or under-way Assignment, frozen."""
    with errors_as_http():
        report = await svc.assignment_report(
            db, access.ctx, access.user, access.scope,
            assignment_id, format,
        )
    return _download(report)


@router.get("/vessels/{vessel_id}/report")
async def vessel_report(
    vessel_id: Id,
    format: ReportFormat = Query(...),
    db: asyncpg.Connection = Depends(get_db),
    access: CrewAccess = Depends(get_crew_access),
) -> Response:
    """One readiness section per Assignment under way or starting within the
    Planning Horizon, with the vessel's counter totals."""
    with errors_as_http():
        report = await svc.vessel_report(
            db, access.ctx, access.user, access.scope,
            vessel_id, format,
        )
    return _download(report)
