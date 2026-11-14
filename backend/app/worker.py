"""The daily check's worker (T9): an APScheduler job inside the API process.

It wakes every 5 minutes (and once at start-up, to catch up after downtime)
and runs the check if today's local-date run hasn't happened and the local
time has reached the configured check time (`daily_check.run_if_due`). It
uses the app's `app_backend` pool. Stated limit: it runs only while the API
is up.
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.mail import get_mailer
from app.services import daily_check

logger = logging.getLogger(__name__)

WAKE_MINUTES = 5


async def tick() -> None:
    from app.db import get_pool

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await daily_check.run_if_due(conn, get_mailer())
    except Exception:
        logger.exception("The daily check failed")


def start() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=timezone.utc)
    scheduler.add_job(
        tick,
        IntervalTrigger(minutes=WAKE_MINUTES),
        id="daily_check",
        next_run_time=datetime.now(timezone.utc),
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
