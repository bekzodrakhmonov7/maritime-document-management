"""Supabase Auth (GoTrue), for the sign-in proxy (R1, ADR 0005, ADR 0007).

The backend talks to Supabase Auth on the person's behalf so it can record
failed attempts and so that no session leaves the proxy before both steps
are done: the password (`/token?grant_type=password`), then a TOTP code
from an authenticator app (`/factors`: enrol, challenge, verify), which
raises the session to `aal2`. Registering is finished with the e-mailed
confirmation code (`/signup`, `/verify`); a forgotten password is replaced
with an e-mailed code (`/recover`). The final session goes to the
browser, which never calls Supabase Auth itself (SR-01): it renews the
session through the API (`/token?grant_type=refresh_token`), and the API
ends it at sign-out (`/logout`). An administrator removes a lost
authenticator through the admin API, with the service key.
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

    async def refresh(self, refresh_token: str, client_ip: str | None) -> dict[str, Any]:
        """Renew a session with its refresh token (used once); answers the
        same session (id and aal kept) with new tokens."""
        ...

    async def list_factors(self, access_token: str, client_ip: str | None) -> list[dict[str, Any]]:
        """The session user's MFA factors: `{id, factor_type, status, ...}`."""
        ...

    async def enroll_totp(self, access_token: str, client_ip: str | None) -> dict[str, Any]:
        """Start a TOTP enrolment: `{id, totp: {qr_code (SVG), secret, uri}}`."""
        ...

    async def challenge(self, access_token: str, factor_id: str, client_ip: str | None) -> str:
        """Open an MFA challenge for the factor; answers its id."""
        ...

    async def verify_totp(
        self,
        access_token: str,
        factor_id: str,
        challenge_id: str,
        code: str,
        client_ip: str | None,
    ) -> dict[str, Any]:
        """Check a TOTP code; answers the same session raised to aal2. The
        first right code finishes an enrolment."""
        ...

    async def unenroll(self, access_token: str, factor_id: str, client_ip: str | None) -> None:
        """Remove one of the session user's factors (an unfinished enrolment)."""
        ...

    async def delete_factors(self, user_id: str) -> None:
        """Admin: remove every factor of a user (a lost authenticator)."""
        ...


# Shown in the authenticator app next to the e-mail.
TOTP_ISSUER = "Maritime Crew Monitor"


class GoTrue:
    def __init__(self, base_url: str, api_key: str, service_key: str = "") -> None:
        self.base_url = f"{base_url.rstrip('/')}/auth/v1"
        self.api_key = api_key
        self.service_key = service_key

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

    async def refresh(self, refresh_token: str, client_ip: str | None) -> dict[str, Any]:
        return await self._call(
            "POST", "/token?grant_type=refresh_token",
            {"refresh_token": refresh_token}, client_ip,
        )

    async def list_factors(self, access_token: str, client_ip: str | None) -> list[dict[str, Any]]:
        # GoTrue has no GET /factors: the user carries them (absent when none).
        user = await self._call("GET", "/user", None, client_ip, access_token)
        return list(user.get("factors") or [])

    async def enroll_totp(self, access_token: str, client_ip: str | None) -> dict[str, Any]:
        # No friendly name: GoTrue refuses a second factor with the same one.
        return await self._call(
            "POST", "/factors", {"factor_type": "totp", "issuer": TOTP_ISSUER},
            client_ip, access_token,
        )

    async def challenge(self, access_token: str, factor_id: str, client_ip: str | None) -> str:
        body = await self._call(
            "POST", f"/factors/{factor_id}/challenge", {}, client_ip, access_token
        )
        return str(body["id"])

    async def verify_totp(
        self,
        access_token: str,
        factor_id: str,
        challenge_id: str,
        code: str,
        client_ip: str | None,
    ) -> dict[str, Any]:
        return await self._call(
            "POST", f"/factors/{factor_id}/verify",
            {"challenge_id": challenge_id, "code": code}, client_ip, access_token,
        )

    async def unenroll(self, access_token: str, factor_id: str, client_ip: str | None) -> None:
        await self._call("DELETE", f"/factors/{factor_id}", None, client_ip, access_token)

    async def delete_factors(self, user_id: str) -> None:
        admin = f"/admin/users/{user_id}/factors"
        factors = await self._call("GET", admin, None, None, admin_key=True)
        for factor in factors if isinstance(factors, list) else []:
            await self._call("DELETE", f"{admin}/{factor['id']}", None, None, admin_key=True)

    async def _call(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None,
        client_ip: str | None,
        access_token: str | None = None,
        *,
        admin_key: bool = False,
    ) -> Any:
        if admin_key:
            headers = {"apikey": self.service_key, "Authorization": f"Bearer {self.service_key}"}
        else:
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
        if res.is_success and isinstance(body, list):
            return body  # the admin list of a user's factors
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
        settings.supabase_url,
        settings.supabase_anon_key or settings.supabase_service_role_key,
        settings.supabase_service_role_key,
    )
