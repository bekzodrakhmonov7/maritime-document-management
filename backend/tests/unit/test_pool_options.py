"""The asyncpg pool options: direct locally, pooler-safe on hosted (ADR 0003)."""

from app.db import pool_options

POOLER_URL = (
    "postgresql://app_backend.abcdefghijklmnop:secret"
    "@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
)


def test_the_local_connection_keeps_asyncpg_defaults():
    assert pool_options("postgresql://app_backend:app_backend_dev@127.0.0.1:54322/postgres") == {}
    assert pool_options("postgresql://postgres:postgres@localhost:54322/postgres") == {}


def test_the_hosted_pooler_gets_tls_no_statement_cache_and_a_small_pool():
    assert pool_options(POOLER_URL) == {
        "ssl": "require",
        "statement_cache_size": 0,
        "min_size": 0,
        "max_size": 5,
    }
