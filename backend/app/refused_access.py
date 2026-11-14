"""Refused access reaches the Audit Log (T7, ADR 0002).

The one exception-handling point for refusals. It writes *access refused*
for every 403 (wrong role, no account, pending or deactivated account) and
every `OutOfScope` 404, then answers as FastAPI normally would. A plain 404
(the id doesn't exist) writes nothing.

The record is written on its own connection and in its own transaction,
because the refused request's transaction rolls back.
"""

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from app import audit
from app.audit import AuditAction, audit_context_for, request_audit_context
from app.models.auth import UserPayload

logger = logging.getLogger(__name__)


class OutOfScope(HTTPException):
    """A record that exists but is outside the caller's Scope. It looks
    exactly like a missing record (404) but is recorded as refused access."""

    def __init__(
        self, target_type: str, target_id: object, *, seafarer_id: int | None = None
    ) -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, "Not found")
        self.target_type = target_type
        self.target_id = target_id
        self.seafarer_id = seafarer_id


def install(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> Response:
    if isinstance(exc, OutOfScope) or exc.status_code == status.HTTP_403_FORBIDDEN:
        try:
            await _record_refusal(request, exc)
        except Exception:
            # The refusal stands either way; a missing record must be noticed.
            logger.exception("Refused access could not be recorded")
    return await http_exception_handler(request, exc)


def _reason(exc: StarletteHTTPException) -> str:
    if isinstance(exc, OutOfScope):
        return "out_of_scope"
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        return str(detail["code"])
    return "forbidden"


async def _record_refusal(request: Request, exc: StarletteHTTPException) -> None:
    from app.db import get_pool

    # Set by the sign-in dependency: the Account, or just the token's subject
    # when the token has no Account.
    account: UserPayload | None = getattr(request.state, "account", None)
    if account is not None:
        ctx = audit_context_for(request, account)
    else:
        ctx = request_audit_context(request, getattr(request.state, "token_sub", None), None, None)

    if isinstance(exc, OutOfScope):
        target = {
            "target_type": exc.target_type,
            "target_id": exc.target_id,
            "seafarer_id": exc.seafarer_id,
        }
    else:
        target = {"target_type": "request", "target_id": f"{request.method} {request.url.path}"}

    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await audit.record(
            conn, ctx, AuditAction.ACCESS_REFUSED,
            reason=_reason(exc), outcome="refused", **target,
        )
