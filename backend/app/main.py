from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import lifespan
from app.request_context import RequestIdMiddleware
from app.routers import accounts, me


def create_app() -> FastAPI:
    app = FastAPI(title="Crew Document Management", lifespan=lifespan)

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(me.router, prefix="/api")
    app.include_router(accounts.router, prefix="/api")

    return app


app = create_app()
