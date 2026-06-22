import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config import settings

_pool: asyncpg.Pool | None = None


async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(settings.database_url)


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool has not been initialized")
    return _pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> None:
    global _pool
    _pool = await create_pool()
    yield
    await _pool.close()
