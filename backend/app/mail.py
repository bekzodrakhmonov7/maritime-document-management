"""E-mail through Resend (FR-16).

The daily check sends through `get_mailer()`, so tests can put an in-memory
stand-in in its place. A send that fails raises `MailFailed`; the caller keeps
the delivery unsent and a later run retries it.
"""

import asyncio
from typing import Protocol

import resend

from app.config import settings


class MailFailed(Exception):
    pass


class Mailer(Protocol):
    async def send(self, to: str, subject: str, html: str) -> None: ...


class ResendMailer:
    async def send(self, to: str, subject: str, html: str) -> None:
        if not settings.resend_api_key:
            raise MailFailed("RESEND_API_KEY is not set")
        resend.api_key = settings.resend_api_key
        params = {
            "from": f"Crew Monitor <{settings.mail_from}>",
            "to": [to],
            "subject": subject,
            "html": html,
        }
        try:
            await asyncio.to_thread(resend.Emails.send, params)
        except Exception as exc:
            raise MailFailed(str(exc) or type(exc).__name__) from exc


_mailer = ResendMailer()


def get_mailer() -> Mailer:
    return _mailer
