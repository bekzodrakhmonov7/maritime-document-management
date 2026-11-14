"""The audit helper writes in the change's own transaction (T7, ADR 0002)."""

from uuid import uuid4

import asyncpg
import pytest

from app import audit
from app.audit import AuditAction, AuditContext
from app.config import settings as app_settings


@pytest.fixture
async def app_conn():
    conn = await asyncpg.connect(app_settings.database_url)
    try:
        yield conn
    finally:
        await conn.close()


async def _count(conn, marker: str) -> int:
    return await conn.fetchval("SELECT count(*) FROM public.audit_log WHERE target_id = $1", marker)


async def test_a_record_rolls_back_with_its_change(app_conn):
    marker = str(uuid4())
    with pytest.raises(RuntimeError):
        async with app_conn.transaction():
            await audit.record(app_conn, AuditContext.system(), AuditAction.ACCOUNT_APPROVED,
                               target_type="account", target_id=marker)
            raise RuntimeError("the change failed")
    assert await _count(app_conn, marker) == 0


async def test_a_record_commits_with_its_change(app_conn):
    marker = str(uuid4())
    async with app_conn.transaction():
        await audit.record(app_conn, AuditContext.system(), AuditAction.ACCOUNT_APPROVED,
                           target_type="account", target_id=marker, reason="why")
    assert await _count(app_conn, marker) == 1


async def test_a_record_outside_a_transaction_is_refused(app_conn):
    with pytest.raises(RuntimeError, match="transaction"):
        await audit.record(app_conn, AuditContext.system(), AuditAction.ACCOUNT_APPROVED)


def test_changed_fields_keeps_only_differences():
    before, after = audit.changed_fields(
        {"status": "active", "role": "manager"}, {"status": "active", "role": "administrator"}
    )
    assert before == {"role": "manager"}
    assert after == {"role": "administrator"}
