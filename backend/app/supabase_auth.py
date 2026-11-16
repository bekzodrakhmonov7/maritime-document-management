"""Sign-in Codes from Supabase Auth (GoTrue), for the sign-in proxy (R1, ADR-0004).

The backend asks Supabase Auth to e-mail a Sign-in Code (`/auth/v1/otp`) and
checks the code the person types (`/auth/v1/verify`) on their behalf, so that
it can record failed attempts; the frontend then hands the returned session
to `setSession`. There is no password sign-in.
"""

from typing import Any, Protocol

import httpx

from app.config import settings

TIMEOUT_SECONDS = 10.0


class SignInRefused(Exception):
    """Supabase Auth said no: unknown e-mail, wrong or expired code, rate limit..."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class AuthUnavailable(Exception):
    """Supabase Auth could not be reached or failed on its side."""

    code = "auth_unavailable"


class SupabaseAuth(Protocol):
    async def send_code(
        self, email: str, create: bool, full_name: str | None, client_ip: str | None
    ) -> None:
        """E-mail a Sign-in Code. `create` lets Supabase make the Account
        (Register); without it an unknown e-mail is refused (`otp_disabled`)."""
        ...

    async def verify_code(self, email: str, code: str, client_ip: str | None) -> dict[str, Any]:
        """Check a Sign-in Code and return the session."""
        ...


class GoTrue:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = f"{base_url.rstrip('/')}/auth/v1"
        self.api_key = api_key

    async def send_code(
        self, email: str, create: bool, full_name: str | None, client_ip: str | None
    ) -> None:
        body: dict[str, Any] = {"email": email, "create_user": create}
        if full_name:
            body["data"] = {"full_name": full_name}
        await self._post("/otp", body, client_ip)

    async def verify_code(self, email: str, code: str, client_ip: str | None) -> dict[str, Any]:
        return await self._post(
            "/verify", {"type": "email", "email": email, "token": code}, client_ip
        )

    async def _post(
        self, path: str, json: dict[str, Any], client_ip: str | None
    ) -> dict[str, Any]:
        headers = {"apikey": self.api_key}
        if client_ip:
            # So Supabase's own rate limit and log see the person, not us.
            headers["X-Forwarded-For"] = client_ip
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
                res = await http.post(f"{self.base_url}{path}", json=json, headers=headers)
        except httpx.HTTPError as exc:
            raise AuthUnavailable() from exc

        if res.status_code >= 500:
            raise AuthUnavailable()
        try:
            body = res.json() if res.content else {}
        except ValueError:
            raise AuthUnavailable()
        if not isinstance(body, dict):
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
