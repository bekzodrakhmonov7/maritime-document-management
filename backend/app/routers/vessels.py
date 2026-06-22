from fastapi import APIRouter, Depends, HTTPException, status
from asyncpg import Connection

from app.deps import get_current_user, get_db, require_role
from app.models.auth import UserPayload
from app.models.vessel import VesselCreate, VesselRead, VesselUpdate
from app.services import vessel_service

router = APIRouter(prefix="/vessels", tags=["vessels"])


@router.get("", response_model=list[VesselRead])
async def list_vessels(
    db: Connection = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user),
) -> list[dict]:
    return await vessel_service.get_vessels(db)


@router.post("", response_model=VesselRead, status_code=status.HTTP_201_CREATED)
async def create_vessel(
    data: VesselCreate,
    db: Connection = Depends(get_db),
    current_user: UserPayload = Depends(require_role("administrator")),
) -> dict:
    return await vessel_service.create_vessel(db, data)


@router.get("/{vessel_id}", response_model=VesselRead)
async def get_vessel(
    vessel_id: int,
    db: Connection = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user),
) -> dict:
    vessel = await vessel_service.get_vessel(db, vessel_id)
    if not vessel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vessel not found",
        )
    return vessel


@router.patch("/{vessel_id}", response_model=VesselRead)
async def update_vessel(
    vessel_id: int,
    data: VesselUpdate,
    db: Connection = Depends(get_db),
    current_user: UserPayload = Depends(require_role("administrator")),
) -> dict | None:
    vessel = await vessel_service.update_vessel(db, vessel_id, data)
    if not vessel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vessel not found",
        )
    return vessel


@router.delete("/{vessel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vessel(
    vessel_id: int,
    db: Connection = Depends(get_db),
    current_user: UserPayload = Depends(require_role("administrator")),
) -> None:
    deleted = await vessel_service.delete_vessel(db, vessel_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vessel not found",
        )
    return None
