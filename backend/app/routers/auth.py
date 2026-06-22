from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models.auth import UserPayload

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserPayload)
async def get_me(current_user: UserPayload = Depends(get_current_user)) -> UserPayload:
    return current_user
