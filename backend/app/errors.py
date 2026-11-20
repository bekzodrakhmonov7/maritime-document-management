"""General answers for malformed requests and unexpected errors (SR-16).

A 422 lists what is wrong (`loc`, `msg`, `type`) but never echoes the input,
so a refused password or token does not come back. Any other unhandled
error is logged with its traceback and request id and answered with a
plain 500. `HTTPException`s stay with `app.refused_access`.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

_KEPT = ("loc", "msg", "type")


def install(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [{k: e[k] for k in _KEPT if k in e} for e in exc.errors()]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": jsonable_encoder(errors)},
    )


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.exception(
        "Unexpected error on %s %s (request id %s)",
        request.method, request.url.path, request_id,
        exc_info=exc,
    )
    # This answer is sent outside RequestIdMiddleware, so it adds the header itself.
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "request_id": request_id},
        headers={"X-Request-ID": request_id} if request_id else None,
    )
