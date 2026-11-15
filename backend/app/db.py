from urllib.parse import urlparse

import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config import settings

_pool: asyncpg.Pool | None = None


def _is_local(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


def pool_options(url: str) -> dict:
    """asyncpg pool options for `url`.

    Locally the connection is direct and keeps asyncpg's defaults. Hosted, the
    API runs as Vercel functions behind Supabase's transaction pooler (ADR
    0003): the pooler can't keep prepared statements across transactions, so
    the statement cache is off, and each instance holds only a few connections
    so parallel instances don't exhaust the pooler.
    """
    if _is_local(url):
        return {}
    return {"ssl": "require", "statement_cache_size": 0, "min_size": 0, "max_size": 5}


async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(settings.database_url, **pool_options(settings.database_url))


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool has not been initialized")
    return _pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> None:
    global _pool
    _pool = await create_pool()
    try:
        yield
    finally:
        await _pool.close()
