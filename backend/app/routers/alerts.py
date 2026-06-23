from datetime import date
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from app.deps import get_current_user, get_db, require_role
from app.models.auth import UserPayload
from app.services import alert_service
from app.worker.run_expiry_scan import _run_scan

router = APIRouter(prefix="/alerts", tags=["alerts"])


class ThresholdUpdate(BaseModel):
    days_90: int | None = None
    days_60: int | None = None
    days_30: int | None = None

    @field_validator("days_90", "days_60", "days_30")
    @classmethod
    def check_positive(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("Threshold values must be positive integers")
        return v

    @field_validator("days_90")
    @classmethod
    def check_descending(cls, v: int | None, info) -> int | None:
        if v is None:
            return v
        data = info.data
        days_60 = data.get("days_60")
        days_30 = data.get("days_30")
        if days_60 is not None and v <= days_60:
            raise ValueError("days_90 must be greater than days_60")
        if days_30 is not None and v <= days_30:
            raise ValueError("days_90 must be greater than days_30")
        return v

    @field_validator("days_60")
    @classmethod
    def check_mid(cls, v: int | None, info) -> int | None:
        if v is None:
            return v
        data = info.data
        days_90 = data.get("days_90")
        days_30 = data.get("days_30")
        if days_90 is not None and v >= days_90:
            raise ValueError("days_60 must be less than days_90")
        if days_30 is not None and v <= days_30:
            raise ValueError("days_60 must be greater than days_30")
        return v

    @field_validator("days_30")
    @classmethod
    def check_low(cls, v: int | None, info) -> int | None:
        if v is None:
            return v
        data = info.data
        days_90 = data.get("days_90")
        days_60 = data.get("days_60")
        if days_90 is not None and v >= days_90:
            raise ValueError("days_30 must be less than days_90")
        if days_60 is not None and v >= days_60:
            raise ValueError("days_30 must be less than days_60")
        return v


@router.post("/scan", response_model=dict)
async def trigger_scan(
    current_user: Annotated[UserPayload, Depends(require_role("administrator"))],
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    return await _run_scan(date.today(), db)


@router.get("", response_model=list[dict])
async def list_alerts(
    current_user: UserPayload = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    return await alert_service.list_active_alerts(db)


@router.patch("/{alert_id}/resolve", response_model=dict)
async def resolve_alert(
    alert_id: int,
    current_user: UserPayload = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    ok = await alert_service.resolve_alert(db, alert_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        )
    return {"alert_id": alert_id, "is_resolved": True}


@router.get("/thresholds", response_model=dict)
async def get_thresholds(
    current_user: UserPayload = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    return await alert_service.get_threshold_config(db)


@router.patch("/thresholds", response_model=dict)
async def update_thresholds(
    payload: ThresholdUpdate,
    current_user: Annotated[UserPayload, Depends(require_role("administrator"))],
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    allowed = {"days_90", "days_60", "days_30"}
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if k in allowed}
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid threshold fields provided",
        )

    set_clauses = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
    values = list(updates.values())

    row = await db.fetchrow(
        f"""
        UPDATE public.alert_threshold_config
        SET {set_clauses}, updated_by = $1, updated_at = now()
        WHERE id = (SELECT id FROM public.alert_threshold_config LIMIT 1)
        RETURNING days_90, days_60, days_30
        """,
        current_user.sub,
        *values,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Threshold config not found"
        )
    return dict(row)
