"""Password sign-in against Supabase Auth (GoTrue), for the sign-in proxy (R1).

The backend signs in on the person's behalf so that it can record failed
attempts; the frontend then hands the returned session to `setSession`.
"""

from typing import Any, Protocol

import httpx

from app.config import settings

TIMEOUT_SECONDS = 10.0


class SignInRefused(Exception):
    """Supabase Auth said no: wrong password, unknown e-mail, rate limit..."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class AuthUnavailable(Exception):
    """Supabase Auth could not be reached or failed on its side."""

    code = "auth_unavailable"


class SupabaseAuth(Protocol):
    async def sign_in_with_password(
        self, email: str, password: str, client_ip: str | None
    ) -> dict[str, Any]: ...


class GoTrue:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.token_url = f"{base_url.rstrip('/')}/auth/v1/token"
        self.api_key = api_key

    async def sign_in_with_password(
        self, email: str, password: str, client_ip: str | None
    ) -> dict[str, Any]:
        headers = {"apikey": self.api_key}
        if client_ip:
            # So Supabase's own rate limit and log see the person, not us.
            headers["X-Forwarded-For"] = client_ip
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
                res = await http.post(
                    self.token_url,
                    params={"grant_type": "password"},
                    json={"email": email, "password": password},
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise AuthUnavailable() from exc

        if res.status_code >= 500:
            raise AuthUnavailable()
        try:
            body = res.json()
        except ValueError:
            raise AuthUnavailable()
        if res.is_success:
            return body
        # Newer GoTrue: {error_code, msg}; older: {error, error_description}.
        code = body.get("error_code") or body.get("error") or f"http_{res.status_code}"
        message = body.get("msg") or body.get("error_description") or "Sign-in failed."
        raise SignInRefused(res.status_code, str(code), str(message))


def get_supabase_auth() -> SupabaseAuth:
    return GoTrue(
        settings.supabase_url, settings.supabase_anon_key or settings.supabase_service_role_key
    )
