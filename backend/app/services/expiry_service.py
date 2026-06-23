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
        return "valid"
    if days_remaining >= 1:
        return "expiring_soon"
    return "expired"


# ============================================================
# State Machine: Daily Document Expiry Check
# ============================================================
# STEP 1: Start
#         The process begins at the initial start node.
# STEP 2: Initiate Daily System Check
#         The scheduler triggers the scan once per day (09:00 local).
# STEP 3: Fetch All Documents with 'Verified' Status
#         Query documents with status IN ('verified', 'valid') for evaluation.
# STEP 4: Decision Point
#         For each candidate, are the days remaining <= 90?
# STEP 5: If "no" — Maintain Status as 'Valid'
#         For documents with > 90 days remaining, set status = 'valid'.
#         The process ends for those documents.
# STEP 6: If "yes" — Update Status to 'Expiring Soon' or 'Expired'
#         1-90 days remaining  -> status = 'expiring_soon'
#         <= 0 days remaining   -> status = 'expired'
# STEP 7: Generate and Dispatch Automated Alert
#         Insert alert rows and send emails for documents entering
#         the 90/60/30-day threshold windows.
# STEP 8: End
#         The process reaches the final termination node and concludes.
# ============================================================
async def scan_and_transition(
    conn: asyncpg.Connection, today: date, thresholds: dict | None = None
) -> int:
    if thresholds is None:
        thresholds = THRESHOLD_CONFIG_DEFAULTS
    days_90 = thresholds.get("days_90", 90)
    threshold_date = today + timedelta(days=days_90)

    row_to_valid = await conn.execute(
        """
        UPDATE public.document
        SET status = 'valid'
        WHERE status = 'verified'
          AND expiry_date > $1
        """,
        threshold_date,
    )
    valid_count = int(row_to_valid.split()[-1]) if row_to_valid.split()[-1].isdigit() else 0

    row_to_expiring = await conn.execute(
        """
        UPDATE public.document
        SET status = 'expiring_soon'
        WHERE status IN ('verified', 'valid')
          AND expiry_date <= $1
          AND expiry_date > $2
        """,
        threshold_date,
        today,
    )
    expiring_count = int(row_to_expiring.split()[-1]) if row_to_expiring.split()[-1].isdigit() else 0

    row_to_expired = await conn.execute(
        """
        UPDATE public.document
        SET status = 'expired'
        WHERE status IN ('verified', 'valid', 'expiring_soon')
          AND expiry_date <= $1
        """,
        today,
    )
    expired_count = int(row_to_expired.split()[-1]) if row_to_expired.split()[-1].isdigit() else 0

    return valid_count + expiring_count + expired_count
