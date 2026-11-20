from pathlib import Path
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


def is_local(url: str) -> bool:
    """The URL points at this machine (the local Supabase stack)."""
    return (urlparse(url).hostname or "").lower() in LOCAL_HOSTS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str
    supabase_service_role_key: str
    # The public key, for the sign-in proxy; the service key is used if unset.
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""

    # The app's connection, as the restricted app_backend role (ADR 0002).
    database_url: str

    # Local development only (Vite on 5173 calling uvicorn on 8000). Hosted, the
    # app and the API share one Vercel origin, so no cross-origin access is needed.
    cors_origins: str ="http://localhost:5173,http://127.0.0.1:5173"

    frontend_url: str = "http://localhost:5173"

    resend_api_key: str = ""
    mail_from: str

    # Shared with the database's pg_cron job (Vault `cron_secret`). Empty means
    # POST /api/internal/daily-check always answers 404.
    cron_secret: str = ""

    @field_validator("supabase_url")
    @classmethod
    def _https_unless_local(cls, url: str) -> str:
        # Every connection leaving the host uses TLS (SR-11).
        if urlparse(url).scheme != "https" and not is_local(url):
            raise ValueError("must be an https:// URL (plain http only for a local host)")
        return url


settings = Settings()
