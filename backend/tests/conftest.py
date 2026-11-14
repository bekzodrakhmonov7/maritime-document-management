"""Shared test fixtures.

Integration tests run the app as the restricted `app_backend` role, so missing
grants and Audit Log tampering fail here just as they would in production.
Fixtures build their own rows (never the seed) through OWNER_DATABASE_URL and
remove what they made afterwards.

- OWNER_DATABASE_URL: the table owner (postgres), for fixtures only.
- APP_DATABASE_URL: the app's connection. Defaults to OWNER_DATABASE_URL with
  the user swapped for app_backend and the local dev password from seed.sql.
"""

import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

APP_BACKEND_DEV_PASSWORD = "app_backend_dev"


def _app_backend_url(owner_url: str) -> str:
    parts = urlsplit(owner_url)
    host = parts.hostname or "127.0.0.1"
    netloc = f"app_backend:{APP_BACKEND_DEV_PASSWORD}@{host}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit(parts._replace(netloc=netloc))


OWNER_DATABASE_URL = os.environ.get("OWNER_DATABASE_URL") or os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)
os.environ["DATABASE_URL"] = os.environ.get("APP_DATABASE_URL") or _app_backend_url(
    OWNER_DATABASE_URL
)

import asyncpg  # noqa: E402
import jwt  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import create_app  # noqa: E402


def make_token(user_id: UUID, email: str = "someone@example.com") -> str:
    """A Supabase-style access token. Its role claim is never trusted."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")


def auth_header(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user_id)}"}


@pytest_asyncio.fixture
async def owner_db():
    """A connection as the table owner, for arranging and inspecting rows."""
    conn = await asyncpg.connect(OWNER_DATABASE_URL)
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def make_account(owner_db):
    """Create Accounts through the real sign-up trigger, then set their state.

    Returns an async factory: make_account(status="active", role=...) -> id.
    Afterwards the accounts it made are removed again. The Audit Log is
    append-only and left alone; tests look up their own records by id.
    """
    created: list[UUID] = []

    async def _make(
        status: str = "active",
        role: str | None = "administrator",
        email: str | None = None,
        full_name: str = "Test Account",
    ) -> UUID:
        user_id = uuid4()
        email = email or f"{user_id.hex[:12]}@example.com"
        await owner_db.execute(
            """
            INSERT INTO auth.users (id, email, encrypted_password, raw_user_meta_data,
                                    email_confirmed_at, created_at, updated_at)
            VALUES ($1, $2, 'x', jsonb_build_object('full_name', $3::text), now(), now(), now())
            """,
            user_id,
            email,
            full_name,
        )
        created.append(user_id)
        if status != "pending":
            await owner_db.execute(
                "UPDATE public.users SET status = $2, role = $3 WHERE id = $1",
                user_id,
                status,
                role,
            )
        return user_id

    yield _make

    if created:
        # Not TRUNCATE ... CASCADE: that would also empty `settings`, whose
        # updated_by references users.
        await owner_db.execute("DELETE FROM public.users WHERE id = ANY($1::uuid[])", created)
        await owner_db.execute("DELETE FROM auth.users WHERE id = ANY($1::uuid[])", created)


@pytest_asyncio.fixture
async def app():
    """The app with a real pool, connected as app_backend."""
    import app.db as db_module

    pool = await db_module.create_pool()
    db_module._pool = pool
    try:
        yield create_app()
    finally:
        await pool.close()
        db_module._pool = None


# Seafarers reference Positions, and Assignments and Responsible Officer links
# reference vessels, so they all go with the reference data.
REFERENCE_TABLES = (
    "vessel", "position", "document_type", "seafarer", "assignment", "responsible_officer",
)


@pytest_asyncio.fixture
async def reference_cleanup(owner_db):
    """Empty the reference-data, seafarer and Assignment tables before and after the test.

    Tests never depend on the seed, so its demo rows go too (a local
    `sandbox-db reset` brings them back).
    """
    statement = f"TRUNCATE {', '.join(f'public.{t}' for t in REFERENCE_TABLES)} CASCADE"
    await owner_db.execute(statement)
    yield
    await owner_db.execute(statement)


_RESET_SETTINGS = """
    UPDATE public.settings
       SET alert_steps = DEFAULT, planning_horizon_days = DEFAULT, max_file_size_mb = DEFAULT,
           max_pdf_pages = DEFAULT, time_zone = DEFAULT, daily_check_time = DEFAULT,
           version = DEFAULT, updated_at = now(), updated_by = NULL
"""


@pytest_asyncio.fixture
async def settings_reset(owner_db, make_account):
    """Put the Settings row back to its defaults before and after the test.

    It depends on make_account so it is torn down first: `updated_by` must be
    cleared before the accounts it may point to are deleted.
    """
    await owner_db.execute(_RESET_SETTINGS)
    yield
    await owner_db.execute(_RESET_SETTINGS)


@pytest_asyncio.fixture
async def client(app):
    """The app driven in-process over HTTP."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def crew(owner_db, reference_cleanup):
    """Factories for vessels, Positions, seafarers and Responsible Officer
    links, made as the owner (tests never depend on the seed)."""

    class Crew:
        imo = 1000000

        async def vessel(self, name: str = "Alpha", active: bool = True) -> int:
            Crew.imo += 1
            return await owner_db.fetchval(
                """
                INSERT INTO public.vessel (name, imo_number, flag, active)
                VALUES ($1, $2, 'MT', $3) RETURNING id
                """,
                name, str(Crew.imo), active,
            )

        async def position(self, name: str = "Master", retired: bool = False) -> int:
            return await owner_db.fetchval(
                "INSERT INTO public.position (name, retired) VALUES ($1, $2) RETURNING id",
                name, retired,
            )

        async def seafarer(self, position_id: int, first_name: str = "Anna") -> int:
            return await owner_db.fetchval(
                """
                INSERT INTO public.seafarer (first_name, last_name, position_id)
                VALUES ($1, 'Petrova', $2) RETURNING id
                """,
                first_name, position_id,
            )

        async def link(self, officer_id: UUID, *vessel_ids: int) -> None:
            for vessel_id in vessel_ids:
                await owner_db.execute(
                    "INSERT INTO public.responsible_officer (user_id, vessel_id) VALUES ($1, $2)",
                    officer_id, vessel_id,
                )

    return Crew()
