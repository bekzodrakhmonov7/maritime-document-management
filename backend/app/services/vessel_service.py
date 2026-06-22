import asyncpg
from fastapi import HTTPException, status

from app.models.vessel import VesselCreate, VesselUpdate


async def create_vessel(conn: asyncpg.Connection, data: VesselCreate) -> dict:
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO public.vessel (vessel_name, imo_number)
            VALUES ($1, $2)
            RETURNING vessel_id, vessel_name, imo_number
            """,
            data.vessel_name,
            data.imo_number,
        )
    except asyncpg.exceptions.UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vessel with this IMO number already exists",
        )
    return dict(row) if row else {}


async def get_vessels(conn: asyncpg.Connection) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT vessel_id, vessel_name, imo_number
        FROM public.vessel
        ORDER BY vessel_id
        """
    )
    return [dict(r) for r in rows]


async def get_vessel(conn: asyncpg.Connection, vessel_id: int) -> dict | None:
    row = await conn.fetchrow(
        """
        SELECT vessel_id, vessel_name, imo_number
        FROM public.vessel
        WHERE vessel_id = $1
        """,
        vessel_id,
    )
    return dict(row) if row else None


async def update_vessel(
    conn: asyncpg.Connection, vessel_id: int, data: VesselUpdate
) -> dict | None:
    fields = []
    values: list = []
    if data.vessel_name is not None:
        fields.append(f"vessel_name = ${len(values) + 1}")
        values.append(data.vessel_name)
    if data.imo_number is not None:
        fields.append(f"imo_number = ${len(values) + 1}")
        values.append(data.imo_number)

    if not fields:
        return await get_vessel(conn, vessel_id)

    values.append(vessel_id)
    sql = f"""
        UPDATE public.vessel
        SET {', '.join(fields)}
        WHERE vessel_id = ${len(values)}
        RETURNING vessel_id, vessel_name, imo_number
    """

    try:
        row = await conn.fetchrow(sql, *values)
    except asyncpg.exceptions.UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vessel with this IMO number already exists",
        )

    return dict(row) if row else None


async def delete_vessel(conn: asyncpg.Connection, vessel_id: int) -> bool:
    try:
        result = await conn.execute(
            """
            DELETE FROM public.vessel
            WHERE vessel_id = $1
            """,
            vessel_id,
        )
    except asyncpg.exceptions.ForeignKeyViolationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete vessel with seafarers attached",
        )

    return result == "DELETE 1"
