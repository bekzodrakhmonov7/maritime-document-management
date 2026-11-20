"""The app refuses to start with a plain-HTTP Supabase URL, except locally (SR-11)."""

import pytest
from pydantic import ValidationError

from app.config import Settings

REQUIRED = {
    "supabase_service_role_key": "key",
    "database_url": "postgresql://app_backend:x@127.0.0.1:54322/postgres",
    "mail_from": "alerts@example.test",
}


def _settings(url: str) -> Settings:
    return Settings(_env_file=None, supabase_url=url, **REQUIRED)


@pytest.mark.parametrize(
    "url",
    [
        "https://abcdefghijklmnop.supabase.co",
        "http://127.0.0.1:54321",
        "http://localhost:54321",
        "http://[::1]:54321",
    ],
)
def test_https_or_a_local_host_is_accepted(url):
    assert _settings(url).supabase_url == url


@pytest.mark.parametrize(
    "url",
    [
        "http://abcdefghijklmnop.supabase.co",
        "http://10.0.0.5:54321",
        "ftp://abcdefghijklmnop.supabase.co",
        "abcdefghijklmnop.supabase.co",
        "http://localhost.evil.example",
    ],
)
def test_plain_http_to_a_non_local_host_is_refused(url):
    with pytest.raises(ValidationError, match="supabase_url"):
        _settings(url)
