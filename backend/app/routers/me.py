from fastapi import APIRouter, Depends

from app.deps import get_account
from app.models.account import Me
from app.models.auth import UserPayload

router = APIRouter(tags=["accounts"])


@router.get("/me", response_model=Me)
async def get_me(user: UserPayload = Depends(get_account)) -> Me:
    """The signed-in Account's status and role. Pending accounts may call it
    (to show the waiting page); deactivated ones get 403."""
    return Me(
        id=user.sub, email=user.email, full_name=user.full_name, status=user.status, role=user.role
    )
