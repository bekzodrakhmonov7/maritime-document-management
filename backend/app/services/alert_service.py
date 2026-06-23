from datetime import date, timedelta

import asyncpg

from app.services.expiry_service import compute_days_remaining


async def get_threshold_config(conn: asyncpg.Connection) -> dict:
    row = await conn.fetchrow("SELECT days_90, days_60, days_30 FROM public.alert_threshold_config LIMIT 1")
    if row is None:
        return {"days_90": 90, "days_60": 60, "days_30": 30}
    return dict(row)


async def get_admin_recipients(conn: asyncpg.Connection) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT au.email
        FROM public.users pu
        JOIN auth.users au ON au.id = pu.id
        WHERE pu.role = 'administrator'
        """
    )
    return [r["email"] for r in rows if r["email"]]


async def generate_alerts(conn: asyncpg.Connection, thresholds: dict | None = None, today: date | None = None) -> int:
    if thresholds is None:
        thresholds = await get_threshold_config(conn)

    threshold_values = [
        ("days_90", thresholds.get("days_90", 90)),
        ("days_60", thresholds.get("days_60", 60)),
        ("days_30", thresholds.get("days_30", 30)),
    ]

    total_inserted = 0
    if today is None:
        today = date.today()

    for _key, threshold_days in threshold_values:
        rows = await conn.fetch(
            """
            SELECT d.document_id, d.expiry_date
            FROM public.document d
            WHERE d.status IN ('verified', 'valid', 'expiring_soon')
              AND d.expiry_date > $1
              AND d.expiry_date <= $2
              AND NOT EXISTS (
                  SELECT 1 FROM public.alert a
                  WHERE a.document_id = d.document_id
                    AND a.alert_threshold_days = $3
                    AND a.is_resolved = false
              )
            """,
            today,
            today + timedelta(days=threshold_days),
            threshold_days,
        )

        for row in rows:
            days_remaining = compute_days_remaining(row["expiry_date"], today)
            if days_remaining <= threshold_days and days_remaining > 0:
                await conn.execute(
                    """
                    INSERT INTO public.alert (document_id, alert_threshold_days)
                    VALUES ($1, $2)
                    """,
                    row["document_id"],
                    threshold_days,
                )
                total_inserted += 1

    return total_inserted


async def list_active_alerts(conn: asyncpg.Connection) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT
            a.alert_id,
            a.document_id,
            a.alert_threshold_days,
            a.generated_at,
            a.is_resolved,
            d.document_number,
            d.expiry_date,
            d.status AS document_status,
            dt.type_name AS document_type,
            s.first_name || ' ' || s.last_name AS seafarer_name
        FROM public.alert a
        JOIN public.document d ON d.document_id = a.document_id
        JOIN public.document_type dt ON dt.doc_type_id = d.doc_type_id
        JOIN public.seafarer s ON s.seafarer_id = d.seafarer_id
        WHERE a.is_resolved = false
        ORDER BY a.generated_at DESC
        """
    )
    return [dict(r) for r in rows]


async def resolve_alert(conn: asyncpg.Connection, alert_id: int) -> bool:
    result = await conn.execute(
        "UPDATE public.alert SET is_resolved = true WHERE alert_id = $1",
        alert_id,
    )
    count = int(result.split()[-1]) if result.split()[-1].isdigit() else 0
    return count > 0
