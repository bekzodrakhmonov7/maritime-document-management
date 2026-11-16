import asyncpg
from fastapi import APIRouter, Depends

from app.deps import get_account, get_current_user, get_db
from app.models.account import Me
from app.models.auth import UserPayload
from app.services import responsible_officers

router = APIRouter(tags=["accounts"])


@router.get("/me", response_model=Me)
async def get_me(user: UserPayload = Depends(get_account)) -> Me:
    """The signed-in Account's status and role. Pending accounts may call it
    (to show the waiting page); deactivated ones get 403."""
    return Me(
        id=user.sub, email=user.email, full_name=user.full_name, status=user.status, role=user.role
    )


@router.get("/me/vessels", response_model=list[int])
async def get_my_vessels(
    user: UserPayload = Depends(get_current_user), db: asyncpg.Connection = Depends(get_db)
) -> list[int]:
    """The vessels a crewing officer is a Responsible Officer for, so the UI
    offers their vessel reports. Empty for other roles: administrators may
    report on any vessel, managers on none."""
    if user.role != "crewing_officer":
        return []
    return sorted(await responsible_officers.vessel_ids(db, user.sub))
