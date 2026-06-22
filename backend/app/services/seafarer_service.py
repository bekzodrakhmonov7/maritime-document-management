import asyncpg
from fastapi import HTTPException, status

from app.models.seafarer import SeafarerCreate, SeafarerUpdate


async def create_seafarer(conn: asyncpg.Connection, data: SeafarerCreate) -> dict:
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO public.seafarer (vessel_id, first_name, last_name, rank)
            VALUES ($1, $2, $3, $4)
            RETURNING seafarer_id, vessel_id, first_name, last_name, rank
            """,
            data.vessel_id,
            data.first_name,
            data.last_name,
            data.rank,
        )
    except asyncpg.exceptions.ForeignKeyViolationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invalid vessel_id",
        )
    return dict(row) if row else {}


async def get_seafarers(
    conn: asyncpg.Connection,
    *,
    vessel_id: int | None = None,
    rank: str | None = None,
    cursor: int | None = None,
    limit: int = 20,
) -> tuple[list[dict], int | None]:
    conditions = []
    params: list = []

    if vessel_id is not None:
        params.append(vessel_id)
        conditions.append(f"s.vessel_id = ${len(params)}")

    if rank is not None:
        params.append(rank)
        conditions.append(f"s.rank = ${len(params)}")

    if cursor is not None:
        params.append(cursor)
        conditions.append(f"s.seafarer_id > ${len(params)}")

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # Fetch one extra to determine if there's a next page
    query_limit = limit + 1
    params.append(query_limit)

    sql = f"""
        SELECT s.seafarer_id, s.vessel_id, s.first_name, s.last_name, s.rank,
               v.vessel_name
        FROM public.seafarer s
        JOIN public.vessel v ON v.vessel_id = s.vessel_id
        {where_clause}
        ORDER BY s.seafarer_id
        LIMIT ${len(params)}
    """

    rows = await conn.fetch(sql, *params)

    next_cursor: int | None = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1]["seafarer_id"]
        rows = rows[:limit]

    return [dict(r) for r in rows], next_cursor


async def get_seafarer(conn: asyncpg.Connection, seafarer_id: int) -> dict | None:
    row = await conn.fetchrow(
        """
        SELECT s.seafarer_id, s.vessel_id, s.first_name, s.last_name, s.rank,
               v.vessel_name
        FROM public.seafarer s
        JOIN public.vessel v ON v.vessel_id = s.vessel_id
        WHERE s.seafarer_id = $1
        """,
        seafarer_id,
    )
    return dict(row) if row else None


async def update_seafarer(
    conn: asyncpg.Connection, seafarer_id: int, data: SeafarerUpdate
) -> dict | None:
    fields = []
    values: list = []
    if data.vessel_id is not None:
        fields.append(f"vessel_id = ${len(values) + 1}")
        values.append(data.vessel_id)
    if data.first_name is not None:
        fields.append(f"first_name = ${len(values) + 1}")
        values.append(data.first_name)
    if data.last_name is not None:
        fields.append(f"last_name = ${len(values) + 1}")
        values.append(data.last_name)
    if data.rank is not None:
        fields.append(f"rank = ${len(values) + 1}")
        values.append(data.rank)

    if not fields:
        return await get_seafarer(conn, seafarer_id)

    values.append(seafarer_id)
    sql = f"""
        UPDATE public.seafarer
        SET {', '.join(fields)}
        WHERE seafarer_id = ${len(values)}
        RETURNING seafarer_id, vessel_id, first_name, last_name, rank
    """

    try:
        row = await conn.fetchrow(sql, *values)
    except asyncpg.exceptions.ForeignKeyViolationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invalid vessel_id",
        )

    if row is None:
        return None

    # Fetch vessel_name in a separate query to avoid complex RETURNING with JOIN
    vessel_row = await conn.fetchrow(
        "SELECT vessel_name FROM public.vessel WHERE vessel_id = $1",
        row["vessel_id"],
    )
    result = dict(row)
    result["vessel_name"] = vessel_row["vessel_name"] if vessel_row else ""
    return result


async def delete_seafarer(conn: asyncpg.Connection, seafarer_id: int) -> bool:
    result = await conn.execute(
        """
        DELETE FROM public.seafarer
        WHERE seafarer_id = $1
        """,
        seafarer_id,
    )
    return result == "DELETE 1"
