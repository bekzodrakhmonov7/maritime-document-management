import argparse
import asyncio
import logging
from datetime import date

logger = logging.getLogger(__name__)

import asyncpg

from app.config import settings
from app.db import create_pool
from app.services.alert_service import generate_alerts, get_threshold_config, list_active_alerts
from app.services.expiry_service import scan_and_transition
from app.services.notification_service import send_expiry_alert_email


async def _run_scan(today: date, conn: asyncpg.Connection | None = None) -> dict:
    pool = None
    if conn is None:
        pool = await create_pool()
        conn = await pool.acquire()

    try:
        thresholds = await get_threshold_config(conn)
        transitioned = await scan_and_transition(conn, today, thresholds)

        # Capture existing unresolved alert IDs before generating new ones
        existing_rows = await conn.fetch(
            "SELECT alert_id FROM public.alert WHERE is_resolved = false"
        )
        existing_alert_ids = {r["alert_id"] for r in existing_rows}

        alerts_generated = await generate_alerts(conn, thresholds, today)

        # Send emails only for newly created alerts
        alerts = await list_active_alerts(conn)
        emails_sent = 0
        for alert in alerts:
            if alert["alert_id"] not in existing_alert_ids:
                recipients = []
                if settings.alert_recipients:
                    recipients = [r.strip() for r in settings.alert_recipients.split(",") if r.strip()]
                if not recipients:
                    continue
                days_remaining = (alert["expiry_date"] - today).days
                try:
                    await send_expiry_alert_email(recipients, alert, days_remaining)
                    emails_sent += 1
                except Exception as exc:
                    logger.warning(
                        "Failed to send expiry alert email for alert_id=%s: %s",
                        alert["alert_id"],
                        exc,
                    )

        return {
            "date": str(today),
            "transitioned": transitioned,
            "alerts_generated": alerts_generated,
            "emails_sent": emails_sent,
        }
    finally:
        if pool is not None:
            await pool.close()


def run(today_override: date | None = None) -> dict:
    today = today_override or date.today()
    summary = asyncio.run(_run_scan(today))
    print(f"Expiry scan complete: {summary}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Maritime document expiry scan worker")
    parser.add_argument(
        "--date",
        type=lambda s: date.fromisoformat(s),
        default=None,
        help="Override today's date (ISO format, e.g. 2025-06-01)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit instead of scheduling",
    )
    args = parser.parse_args()

    if args.once:
        run(today_override=args.date)
    else:
        from app.worker.scheduler import start_scheduler, shutdown_scheduler

        async def job():
            await _run_scan(date.today())

        async def main_async():
            start_scheduler(job)
            print("Scheduler started. Daily expiry scan at 09:00.")
            try:
                await asyncio.Event().wait()
            finally:
                try:
                    shutdown_scheduler()
                except Exception:
                    pass

        try:
            asyncio.run(main_async())
        except (KeyboardInterrupt, SystemExit):
            pass


if __name__ == "__main__":
    main()
