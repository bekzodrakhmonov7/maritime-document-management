import os

os.environ.setdefault("ENABLE_DAILY_SCAN", "0")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import jwt
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from app.config import settings
from app.main import create_app


@pytest_asyncio.fixture
async def async_client() -> AsyncClient:
    import app.db as db_module

    pool = await db_module.create_pool()
    db_module._pool = pool

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await pool.close()
    db_module._pool = None


@pytest.fixture
def admin_token() -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid4()),
        "email": "admin@example.com",
        "role": "administrator",
        "aud": "authenticated",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")


@pytest.fixture
def crewing_officer_token() -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid4()),
        "email": "crew@example.com",
        "role": "crewing_officer",
        "aud": "authenticated",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")


@pytest.fixture
def no_role_token() -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid4()),
        "email": "user@example.com",
        "role": "viewer",
        "aud": "authenticated",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")


from uuid import UUID



def make_token(user_id: UUID | None = None, role: str = "administrator") -> str:

    user_id = user_id or uuid4()

    now = datetime.now(timezone.utc)

    payload = {

        "sub": str(user_id),

        "email": "test@example.com",

        "role": role,

        "aud": "authenticated",

        "iat": now,

        "exp": now + timedelta(hours=1),

    }

    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")



@pytest_asyncio.fixture

async def db_conn():

    from app.db import create_pool

    pool = await create_pool()

    async with pool.acquire() as conn:

        tr = conn.transaction()

        await tr.start()

        yield conn

        await tr.rollback()

    await pool.close()



@pytest_asyncio.fixture

async def client(db_conn):

    from app.deps import get_db

    async def override_get_db():

        yield db_conn

    app = create_app()

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:

        yield client

    app.dependency_overrides.clear()



@pytest_asyncio.fixture

async def test_user(db_conn):

    user_id = uuid4()

    await db_conn.execute(

        """

        INSERT INTO auth.users (id, email, encrypted_password, email_confirmed_at, created_at, updated_at)

        VALUES ($1, $2, 'fake', now(), now(), now())

        ON CONFLICT DO NOTHING

        """,

        user_id,

        f"{user_id}@test.com",

    )

    await db_conn.execute(
        "INSERT INTO public.users (id, full_name, role) VALUES ($1, $2, $3) ON CONFLICT (id) DO UPDATE SET role = EXCLUDED.role, full_name = EXCLUDED.full_name",
        user_id,
        "Test User",
        "administrator",
    )


    return user_id



@pytest_asyncio.fixture
async def test_seafarer(db_conn):
    import time
    imo = f"{int(time.time() * 1000) % 10000000:07d}"
    vessel_id = await db_conn.fetchval(
        "INSERT INTO public.vessel (vessel_name, imo_number) VALUES ($1, $2) RETURNING vessel_id",
        "Test Vessel",
        imo,
    )
    seafarer_id = await db_conn.fetchval(
        """
        INSERT INTO public.seafarer (vessel_id, first_name, last_name, rank)
        VALUES ($1, $2, $3, $4)
        RETURNING seafarer_id
        """,
        vessel_id,
        "John",
        "Doe",
        "Captain",
    )
    return seafarer_id


@pytest_asyncio.fixture
async def test_doc_type(db_conn):
    type_name = f"Passport-{uuid4().hex[:8]}"
    doc_type_id = await db_conn.fetchval(
        "INSERT INTO public.document_type (type_name, is_mandatory) VALUES ($1, $2) RETURNING doc_type_id",
        type_name,
        True,
    )
    return doc_type_id

