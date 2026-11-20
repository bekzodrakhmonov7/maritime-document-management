"""Pwned Passwords: is a new password known from a data breach? (SR-02)

k-anonymity range search: only the first five hex characters of the
password's SHA-1 leave the host (`GET /range/{prefix}`); the answer lists
every known suffix with that prefix and its count, padded with count-0 lines
(`Add-Padding`) so the answer's size says nothing either.

If the service cannot be reached the password is accepted and a warning is
logged (fail open; plan section 14, item 7): an outage of an outside service
must not stop registration or a password reset.
"""

import hashlib
import logging

import httpx

logger = logging.getLogger(__name__)

RANGE_URL = "https://api.pwnedpasswords.com/range/"
TIMEOUT_SECONDS = 3.0
USER_AGENT = "maritime-document-management"


class PwnedPasswords:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        # Tests pass an httpx.MockTransport; None is the real network.
        self.transport = transport

    async def is_breached(self, password: str) -> bool:
        sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
        prefix, suffix = sha1[:5], sha1[5:]
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=TIMEOUT_SECONDS
            ) as http:
                res = await http.get(
                    f"{RANGE_URL}{prefix}",
                    headers={"Add-Padding": "true", "User-Agent": USER_AGENT},
                )
            res.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "Pwned Passwords unreachable (%s); the password was accepted unchecked",
                type(exc).__name__,
            )
            return False
        for line in res.text.splitlines():
            found, _, count = line.strip().partition(":")
            if found.upper() == suffix:
                return count.strip().isdigit() and int(count) > 0
        return False


def get_pwned_passwords() -> PwnedPasswords:
    return PwnedPasswords()
