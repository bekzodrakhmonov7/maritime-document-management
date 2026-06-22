from datetime import date, timedelta

import asyncpg


THRESHOLD_CONFIG_DEFAULTS = {"days_90": 90, "days_60": 60, "days_30": 30}


def compute_days_remaining(expiry_date: date, today: date) -> int:
    return (expiry_date - today).days


def classify_status(days_remaining: int, thresholds: dict | None = None) -> str:
    if thresholds is None:
        thresholds = THRESHOLD_CONFIG_DEFAULTS
    boundary = thresholds.get("days_90", 90)
    if days_remaining >= boundary + 1:
        return "verified"
    if days_remaining >= 1:
        return "expiring_soon"
    return "expired"


async def scan_and_transition(
    conn: asyncpg.Connection, today: date, thresholds: dict | None = None
) -> int:
    if thresholds is None:
        thresholds = THRESHOLD_CONFIG_DEFAULTS
    days_90 = thresholds.get("days_90", 90)
    threshold_date = today + timedelta(days=days_90)

    row_to_expiring = await conn.execute(
        """
        UPDATE public.document
        SET status = 'expiring_soon'
        WHERE status = 'verified'
          AND expiry_date <= $1
        """,
        threshold_date,
    )
    expiring_count = int(row_to_expiring.split()[-1]) if row_to_expiring.split()[-1].isdigit() else 0

    row_to_expired = await conn.execute(
        """
        UPDATE public.document
        SET status = 'expired'
        WHERE status = 'expiring_soon'
          AND expiry_date <= $1
        """,
        today,
    )
    expired_count = int(row_to_expired.split()[-1]) if row_to_expired.split()[-1].isdigit() else 0

    return expiring_count + expired_count
