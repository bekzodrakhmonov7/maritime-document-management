from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app import refused_access
from app.db import lifespan
from app.request_context import RequestIdMiddleware
from app.routers import (
    accounts,
    assignments,
    audit_log,
    auth,
    documents,
    me,
    reference_data,
    requirements,
    seafarers,
    settings as settings_router,
    vessel_crew,
)


def create_app() -> FastAPI:
    app = FastAPI(title="Crew Document Management", lifespan=lifespan)

    refused_access.install(app)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Content-Disposition", "X-Export-Rows", "X-Export-Truncated"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router, prefix="/api")
    app.include_router(me.router, prefix="/api")
    app.include_router(accounts.router, prefix="/api")
    app.include_router(reference_data.vessels, prefix="/api")
    app.include_router(vessel_crew.router, prefix="/api")
    app.include_router(reference_data.positions, prefix="/api")
    app.include_router(reference_data.document_types, prefix="/api")
    app.include_router(requirements.matrix, prefix="/api")
    app.include_router(requirements.exceptions, prefix="/api")
    app.include_router(seafarers.router, prefix="/api")
    app.include_router(assignments.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(settings_router.router, prefix="/api")
    app.include_router(audit_log.router, prefix="/api")

    return app


app = create_app()
