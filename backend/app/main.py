from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import get_pool, lifespan as db_lifespan
from app.routers import alerts, auth, documents, reports, seafarers, vessels
from app.worker.run_expiry_scan import _run_scan
from app.worker.scheduler import shutdown_scheduler, start_scheduler


async def _daily_scan_job() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _run_scan(date.today(), conn)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with db_lifespan(app):
        if settings.enable_daily_scan:
            start_scheduler(_daily_scan_job)
            try:
                yield
            finally:
                shutdown_scheduler()
        else:
            yield


def create_app() -> FastAPI:
    app = FastAPI(title="Maritime Crew Document Expiry Monitoring System", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            o.strip() for o in settings.cors_origins.split(",") if o.strip()
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(vessels.router)
    app.include_router(seafarers.router)
    app.include_router(documents.router)
    app.include_router(alerts.router)
    app.include_router(reports.router)

    return app


app = create_app()
