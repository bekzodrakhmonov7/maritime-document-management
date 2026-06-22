from fastapi import APIRouter, Depends, HTTPException, status
from asyncpg import Connection

from app.deps import get_current_user, get_db, require_role
from app.models.auth import UserPayload
from app.models.seafarer import (
    SeafarerCreate,
    SeafarerRead,
    SeafarerUpdate,
    SeafarerWithVesselRead,
)
from app.services import seafarer_service

router = APIRouter(prefix="/seafarers", tags=["seafarers"])


@router.get("", response_model=list[SeafarerWithVesselRead])
async def list_seafarers(
    vessel_id: int | None = None,
    rank: str | None = None,
    cursor: int | None = None,
    limit: int = 20,
    db: Connection = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user),
) -> list[dict]:
    seafarers, _ = await seafarer_service.get_seafarers(
        db, vessel_id=vessel_id, rank=rank, cursor=cursor, limit=limit
    )
    return seafarers


@router.post("", response_model=SeafarerRead, status_code=status.HTTP_201_CREATED)
async def create_seafarer(
    data: SeafarerCreate,
    db: Connection = Depends(get_db),
    current_user: UserPayload = Depends(
        require_role("administrator", "crewing_officer")
    ),
) -> dict:
    return await seafarer_service.create_seafarer(db, data)


@router.get("/{seafarer_id}", response_model=SeafarerWithVesselRead)
async def get_seafarer(
    seafarer_id: int,
    db: Connection = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user),
) -> dict:
    seafarer = await seafarer_service.get_seafarer(db, seafarer_id)
    if not seafarer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seafarer not found",
        )
    return seafarer


@router.patch("/{seafarer_id}", response_model=SeafarerWithVesselRead)
async def update_seafarer(
    seafarer_id: int,
    data: SeafarerUpdate,
    db: Connection = Depends(get_db),
    current_user: UserPayload = Depends(
        require_role("administrator", "crewing_officer")
    ),
) -> dict | None:
    seafarer = await seafarer_service.update_seafarer(db, seafarer_id, data)
    if not seafarer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seafarer not found",
        )
    return seafarer


@router.delete("/{seafarer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_seafarer(
    seafarer_id: int,
    db: Connection = Depends(get_db),
    current_user: UserPayload = Depends(
        require_role("administrator", "crewing_officer")
    ),
) -> None:
    deleted = await seafarer_service.delete_seafarer(db, seafarer_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seafarer not found",
        )
    return None
