"""The asyncpg pool options: direct locally, pooler-safe on hosted (ADR 0003).

Hosted, the connection checks the server's certificate against the Supabase CA
and its host name, with TLS 1.2 or later (SR-11).
"""

import ssl
from pathlib import Path

import certifi
import pytest

from app.db import CA_PATH, pool_options

POOLER_URL = (
    "postgresql://app_backend.abcdefghijklmnop:secret"
    "@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
)
# Any valid PEM bundle stands in for the Supabase CA in these tests.
SOME_CA = Path(certifi.where())


def test_the_local_connection_keeps_asyncpg_defaults():
    assert pool_options("postgresql://app_backend:app_backend_dev@127.0.0.1:54322/postgres") == {}
    assert pool_options("postgresql://postgres:postgres@localhost:54322/postgres") == {}
    assert pool_options("postgresql://postgres:postgres@[::1]:54322/postgres") == {}


def test_the_hosted_pooler_gets_no_statement_cache_and_a_small_pool():
    options = pool_options(POOLER_URL, ca_path=SOME_CA)
    assert isinstance(options.pop("ssl"), ssl.SSLContext)
    assert options == {"statement_cache_size": 0, "min_size": 0, "max_size": 5}


def test_the_hosted_connection_checks_the_certificate_and_host_name():
    ctx = pool_options(POOLER_URL, ca_path=SOME_CA)["ssl"]
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2


def test_the_hosted_connection_trusts_only_the_given_ca(tmp_path):
    ca = tmp_path / "ca.crt"
    ca.write_text(_first_pem(SOME_CA), encoding="ascii")
    ctx = pool_options(POOLER_URL, ca_path=ca)["ssl"]
    assert ctx.cert_store_stats()["x509_ca"] == 1


def test_a_missing_ca_file_stops_a_hosted_start_with_a_clear_error(tmp_path):
    missing = tmp_path / "supabase-ca.crt"
    with pytest.raises(RuntimeError, match="supabase-ca.crt"):
        pool_options(POOLER_URL, ca_path=missing)


def test_the_ca_lives_in_the_app_package():
    # vercel.json bundles backend/app/**, so the certificate ships with the function.
    assert CA_PATH == Path(__file__).resolve().parents[2] / "app" / "certs" / "supabase-ca.crt"


def _first_pem(bundle: Path) -> str:
    text = bundle.read_text(encoding="ascii")
    end = "-----END CERTIFICATE-----"
    return text[text.index("-----BEGIN CERTIFICATE-----") : text.index(end) + len(end)] + "\n"
