"""Settings (FR-25, T9): any active account reads, administrators save."""

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.audit import audit_context_for
from app.deps import get_current_user, get_db, require_role
from app.models.auth import UserPayload
from app.models.settings import EDITABLE, SettingsRead, SettingsWrite
from app.services import settings as svc

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsRead)
async def get_settings(
    db: asyncpg.Connection = Depends(get_db), _: UserPayload = Depends(get_current_user)
):
    return await svc.with_last_cleanup(db, await svc.get(db))


@router.put("", response_model=SettingsRead)
async def save_settings(
    body: SettingsWrite,
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    admin: UserPayload = Depends(require_role("administrator")),
):
    try:
        saved = await svc.save(
            db,
            audit_context_for(request, admin),
            admin.sub,
            body.model_dump(include=set(EDITABLE)),
            body.version,
        )
    except svc.StaleVersion:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Someone else saved the settings since you opened them. Reload to see their values.",
        )
    return await svc.with_last_cleanup(db, saved)
