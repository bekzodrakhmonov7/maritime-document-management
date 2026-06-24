from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str
    supabase_service_role_key: str
    supabase_jwt_secret: str = ""

    database_url: str

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    frontend_url: str = "http://localhost:5173"

    resend_api_key: str = ""
    mail_from: str

    enable_daily_scan: bool = True


settings = Settings()
