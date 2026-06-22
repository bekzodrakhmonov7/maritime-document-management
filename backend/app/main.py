from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import lifespan as db_lifespan
from app.routers import alerts, auth, documents, reports, seafarers, vessels


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with db_lifespan(app):
        yield


def create_app() -> FastAPI:
    app = FastAPI(title="Maritime Crew Document Expiry Monitoring System", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
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
