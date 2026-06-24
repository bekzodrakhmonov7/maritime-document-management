from urllib.parse import urlparse

import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config import settings

_pool: asyncpg.Pool | None = None


def _is_local(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


async def create_pool() -> asyncpg.Pool:
    if _is_local(settings.database_url):
        return await asyncpg.create_pool(settings.database_url)
    return await asyncpg.create_pool(settings.database_url, ssl="require")


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
