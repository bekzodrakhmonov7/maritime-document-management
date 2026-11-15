"""Calls from the database itself, not from staff (ADR 0003).

Every 5 minutes `pg_cron` POSTs to `/api/internal/daily-check` through
`pg_net`, with the shared secret from Supabase Vault in `X-Cron-Secret`. The
call runs the daily check if it is due (`daily_check.run_if_due`: once per
local date, from the check time on). Any other caller, a staff login
included, gets a plain 404, as does every caller while `CRON_SECRET` is
unset. Nothing here is a staff action, so nothing goes in the Audit Log.
"""

import hmac
import logging

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.deps import get_db
from app.mail import Mailer, get_mailer
from app.models.alert import ScheduledCheckResult
from app.services import daily_check

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def require_cron_secret(x_cron_secret: str | None = Header(default=None)) -> None:
    """404 unless the header matches CRON_SECRET (compared in constant time)."""
    expected = settings.cron_secret
    if not expected or x_cron_secret is None or not hmac.compare_digest(
        x_cron_secret.encode(), expected.encode()
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")


@router.post(
    "/daily-check",
    response_model=ScheduledCheckResult,
    dependencies=[Depends(require_cron_secret)],
)
async def run_daily_check_if_due(
    db: asyncpg.Connection = Depends(get_db),
    mailer: Mailer = Depends(get_mailer),
):
    try:
        result = await daily_check.run_if_due(db, mailer)
    except Exception:
        logger.exception("The daily check failed")
        return JSONResponse({"detail": "The daily check failed"}, status_code=500)
    if result is None:
        return ScheduledCheckResult(ran=False)
    return ScheduledCheckResult(ran=True, result=result.as_dict())
