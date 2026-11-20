"""Pwned Passwords (SR-02): k-anonymity range search. Only the first five hex
characters of the password's SHA-1 leave the host; an unreachable service
lets the password through with a warning in the server log (fail open).

Every test answers through `httpx.MockTransport`: nothing reaches the network.
"""

import hashlib
import logging

import httpx
import pytest

from app.pwned_passwords import RANGE_URL, TIMEOUT_SECONDS, PwnedPasswords

PASSWORD = "harbour-pilot-ladder-7"
SHA1 = hashlib.sha1(PASSWORD.encode()).hexdigest().upper()
PREFIX, SUFFIX = SHA1[:5], SHA1[5:]


def _service(lines: list[str], seen: list[httpx.Request] | None = None, status: int = 200):
    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, text="\r\n".join(lines))

    return httpx.MockTransport(handle)


async def test_a_password_in_the_range_answer_is_breached():
    seen: list[httpx.Request] = []
    pwned = PwnedPasswords(transport=_service(["0018A45C4D1DEF81644B54AB7F969B88D65:1",
                                               f"{SUFFIX}:42"], seen))

    assert await pwned.is_breached(PASSWORD) is True


async def test_only_the_first_five_hash_characters_leave_the_host():
    seen: list[httpx.Request] = []
    pwned = PwnedPasswords(transport=_service([f"{SUFFIX}:3"], seen))

    await pwned.is_breached(PASSWORD)

    [request] = seen
    assert request.method == "GET"
    assert str(request.url) == f"{RANGE_URL}{PREFIX}"
    assert request.url.query == b""
    assert request.content == b""
    assert request.headers["Add-Padding"] == "true"
    assert request.headers["User-Agent"]
    sent = str(request.url) + "".join(f"{k}:{v}" for k, v in request.headers.items())
    assert SUFFIX not in sent and SHA1 not in sent and PASSWORD not in sent


async def test_a_padding_line_with_count_zero_is_not_breached():
    pwned = PwnedPasswords(transport=_service([f"{SUFFIX}:0", "0018A45C4D1DEF81644B54AB7F969B88D65:7"]))

    assert await pwned.is_breached(PASSWORD) is False


async def test_a_password_not_in_the_answer_is_not_breached():
    pwned = PwnedPasswords(transport=_service(["0018A45C4D1DEF81644B54AB7F969B88D65:7"]))

    assert await pwned.is_breached(PASSWORD) is False


def test_the_timeout_is_three_seconds():
    assert TIMEOUT_SECONDS == 3.0


@pytest.mark.parametrize("failure", ["connect", "timeout", "server_error"])
async def test_an_unreachable_service_lets_the_password_through_with_a_warning(failure, caplog):
    def handle(request: httpx.Request) -> httpx.Response:
        if failure == "connect":
            raise httpx.ConnectError("no route", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(503, text="down")

    pwned = PwnedPasswords(transport=httpx.MockTransport(handle))

    with caplog.at_level(logging.WARNING, logger="app.pwned_passwords"):
        assert await pwned.is_breached(PASSWORD) is False

    assert "Pwned Passwords" in caplog.text
    assert PASSWORD not in caplog.text
