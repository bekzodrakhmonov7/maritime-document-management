import ssl
from pathlib import Path

import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config import is_local, settings

_pool: asyncpg.Pool | None = None

# The Supabase root CA (Database settings > SSL Configuration). It signs the
# certificates of both the direct connection and the pooler (SR-11).
CA_PATH = Path(__file__).resolve().parent / "certs" / "supabase-ca.crt"


def tls_context(ca_path: Path = CA_PATH) -> ssl.SSLContext:
    """TLS 1.2 or later, trusting only the Supabase CA and checking the host name.

    asyncpg's `ssl="require"` encrypts without checking who answers; this
    context refuses a server whose certificate or host name doesn't match.
    """
    if not ca_path.is_file():
        raise RuntimeError(
            f"The Supabase CA certificate is missing: {ca_path}. Download it from the "
            "Supabase dashboard (Database settings, SSL Configuration) and commit it "
            "as backend/app/certs/supabase-ca.crt (README, Hosting)."
        )
    ctx = ssl.create_default_context(cafile=str(ca_path))  # CERT_REQUIRED, check_hostname
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def pool_options(url: str, ca_path: Path = CA_PATH) -> dict:
    """asyncpg pool options for `url`.

    Locally the connection is direct and keeps asyncpg's defaults. Hosted, the
    API runs as Vercel functions behind Supabase's transaction pooler (ADR
    0003): the pooler can't keep prepared statements across transactions, so
    the statement cache is off, and each instance holds only a few connections
    so parallel instances don't exhaust the pooler. The connection is TLS with
    the server's certificate checked (SR-11).
    """
    if is_local(url):
        return {}
    return {
        "ssl": tls_context(ca_path),
        "statement_cache_size": 0,
        "min_size": 0,
        "max_size": 5,
    }


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
