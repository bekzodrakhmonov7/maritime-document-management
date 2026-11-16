"""Supabase Auth (GoTrue), for the sign-in proxy (R1, ADR-0005).

The backend talks to Supabase Auth on the person's behalf so it can record
failed attempts and so that no session leaves the proxy before both steps
are done: the password (`/token?grant_type=password`, or `/signup` when
registering), then the Sign-in Code e-mailed to the address (`/otp`, or the
signup confirmation, checked with `/verify`). The frontend hands the final
session to `setSession`. A forgotten password is replaced through `/recover`.
"""

from typing import Any, Literal, Protocol

import httpx

from app.config import settings

TIMEOUT_SECONDS = 10.0


class SignInRefused(Exception):
    """Supabase Auth said no: wrong password or code, rate limit, weak password..."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class AuthUnavailable(Exception):
    """Supabase Auth could not be reached or failed on its side."""

    code = "auth_unavailable"


CodeType = Literal["email", "recovery"]


class SupabaseAuth(Protocol):
    async def sign_up(
        self, email: str, password: str, full_name: str, client_ip: str | None
    ) -> dict[str, Any]:
        """Create the Account. Answers with the user (a confirmation code was
        e-mailed) or, where e-mail confirmation is off, a session."""
        ...

    async def password_grant(
        self, email: str, password: str, client_ip: str | None
    ) -> dict[str, Any]:
        """Check the password; answers with a session."""
        ...

    async def send_code(self, email: str, client_ip: str | None) -> None:
        """E-mail a Sign-in Code to an existing, confirmed Account."""
        ...

    async def resend_confirmation(self, email: str, client_ip: str | None) -> None:
        """E-mail the code that finishes a Register again."""
        ...

    async def verify_code(
        self, email: str, code: str, client_ip: str | None, type: CodeType = "email"
    ) -> dict[str, Any]:
        """Check a code and return the session it opens."""
        ...

    async def send_password_reset(self, email: str, client_ip: str | None) -> None:
        """E-mail a code for setting a new password."""
        ...

    async def set_password(self, access_token: str, password: str, client_ip: str | None) -> None:
        """Set the password of the session's user."""
        ...

    async def sign_out(
        self, access_token: str, scope: Literal["local", "global"], client_ip: str | None
    ) -> None:
        """End the session (`local`) or every session of its user (`global`)."""
        ...


class GoTrue:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = f"{base_url.rstrip('/')}/auth/v1"
        self.api_key = api_key

    async def sign_up(
        self, email: str, password: str, full_name: str, client_ip: str | None
    ) -> dict[str, Any]:
        return await self._call(
            "POST", "/signup",
            {"email": email, "password": password, "data": {"full_name": full_name}},
            client_ip,
        )

    async def password_grant(
        self, email: str, password: str, client_ip: str | None
    ) -> dict[str, Any]:
        return await self._call(
            "POST", "/token?grant_type=password",
            {"email": email, "password": password}, client_ip,
        )

    async def send_code(self, email: str, client_ip: str | None) -> None:
        await self._call("POST", "/otp", {"email": email, "create_user": False}, client_ip)

    async def resend_confirmation(self, email: str, client_ip: str | None) -> None:
        await self._call("POST", "/resend", {"type": "signup", "email": email}, client_ip)

    async def verify_code(
        self, email: str, code: str, client_ip: str | None, type: CodeType = "email"
    ) -> dict[str, Any]:
        return await self._call(
            "POST", "/verify", {"type": type, "email": email, "token": code}, client_ip
        )

    async def send_password_reset(self, email: str, client_ip: str | None) -> None:
        await self._call("POST", "/recover", {"email": email}, client_ip)

    async def set_password(self, access_token: str, password: str, client_ip: str | None) -> None:
        await self._call("PUT", "/user", {"password": password}, client_ip, access_token)

    async def sign_out(
        self, access_token: str, scope: Literal["local", "global"], client_ip: str | None
    ) -> None:
        await self._call("POST", f"/logout?scope={scope}", None, client_ip, access_token)

    async def _call(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None,
        client_ip: str | None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        headers = {"apikey": self.api_key}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        if client_ip:
            # So Supabase's own rate limit and log see the person, not us.
            headers["X-Forwarded-For"] = client_ip
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
                res = await http.request(
                    method, f"{self.base_url}{path}", json=json, headers=headers
                )
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
