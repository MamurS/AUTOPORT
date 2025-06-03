# File: routers/cars.py (Refactored for dependency-level transactions)

import logging
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query # Added Query if used
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select # For re-fetch
from sqlalchemy.orm import selectinload # For re-fetch

from auth.dependencies import get_current_active_user
from crud import car_crud
from database import get_db
from models import User, UserRole, Car # Car needed for re-fetch
from schemas import CarCreate, CarResponse, CarUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cars", tags=["cars"])

@router.post("/", response_model=CarResponse, status_code=status.HTTP_201_CREATED)
async def add_car(
    car_in: CarCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CarResponse:
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can add cars.")
    try:
        # CRUD create_driver_car does not commit
        created_car_shell = await car_crud.create_driver_car(session=db, car_in=car_in, driver_id=current_user.id)
        
        # get_db will commit. Re-fetch for response if CarResponse nests driver.
        # Our CarResponse doesn't directly nest the User object for driver, just driver_id.
        # The created_car_shell (after refresh in CRUD) should be sufficient.
        logger.info(f"Car {created_car_shell.license_plate} created by driver {current_user.id}")
        return created_car_shell
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in add_car: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

# --- GET endpoints remain largely the same, as they are read operations ---
@router.get("/", response_model=List[CarResponse])
async def get_my_cars(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    # Using Claude's pattern for Query params that worked
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return")] = 20
) -> List[CarResponse]:
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can view their cars.")
    cars = await car_crud.get_driver_cars(session=db, driver_id=current_user.id, skip=skip, limit=limit)
    return cars

@router.get("/{car_id}", response_model=CarResponse)
async def get_my_car(
    car_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CarResponse:
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can view car details.")
    car = await car_crud.get_driver_car_by_id(session=db, car_id=car_id, driver_id=current_user.id)
    if not car:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Car not found or not owned by this driver.")
    return car

@router.patch("/{car_id}", response_model=CarResponse)
async def update_my_car(
    car_id: UUID,
    car_in: CarUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CarResponse:
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can update car details.")
    try:
        # No db.begin_nested()
        car = await car_crud.get_driver_car_by_id(session=db, car_id=car_id, driver_id=current_user.id)
        if not car:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Car not found or not owned by this driver.")
        
        updated_car_shell = await car_crud.update_driver_car(session=db, car_to_update=car, car_in=car_in)
        
        # get_db will commit. Re-fetch if needed for CarResponse's nested items.
        # CarResponse doesn't nest driver object, so refreshed updated_car_shell is fine.
        logger.info(f"Car {updated_car_shell.id} updated by driver {current_user.id}")
        return updated_car_shell
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_my_car: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.delete("/{car_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_car(
    car_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can delete cars.")
    try:
        # No db.begin_nested()
        car = await car_crud.get_driver_car_by_id(session=db, car_id=car_id, driver_id=current_user.id)
        if not car:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Car not found or not owned by this driver.")
        await car_crud.delete_driver_car(session=db, car_to_delete=car)
        # get_db will commit.
        logger.info(f"Car {car_id} deleted by driver {current_user.id}")
        return None # For 204 response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in delete_my_car: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.post("/{car_id}/set-default", response_model=CarResponse)
async def set_my_default_car(
    car_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CarResponse:
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can set default cars.")
    try:
        # No db.begin_nested()
        car = await car_crud.get_driver_car_by_id(session=db, car_id=car_id, driver_id=current_user.id)
        if not car:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Car not found or not owned by this driver.")
        
        updated_car_shell = await car_crud.set_driver_default_car(session=db, car_to_set_default=car, driver_id=current_user.id)
        # get_db will commit. Refreshed car from CRUD is fine for CarResponse.
        logger.info(f"Car {updated_car_shell.id} set as default by driver {current_user.id}")
        return updated_car_shell
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in set_my_default_car: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")