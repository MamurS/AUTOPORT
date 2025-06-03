# File: routers/admin.py (Refactored for dependency-level transactions)

import logging
import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
# select and selectinload not needed here if responses are simple enough

from auth.dependencies import get_current_admin_user
from crud import admin_crud
from database import get_db
from models import Car, CarVerificationStatus, User, UserStatus, Trip # Trip needed for TripResponse
from schemas import (
    AdminUpdateStatusRequest,
    CarResponse,
    UserResponse,
    TripResponse 
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin",tags=["admin"],dependencies=[Depends(get_current_admin_user)])

# --- GET list endpoints remain largely the same ---
@router.get("/verifications/drivers/pending", response_model=List[UserResponse])
async def list_drivers_pending_verification(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="...")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="...")] = 20
) -> List[UserResponse]:
    logger.info(f"Admin {current_user.id} fetching drivers pending. Skip: {skip}, Limit: {limit}")
    try:
        drivers = await admin_crud.list_drivers_pending_verification(session=db, skip=skip, limit=limit)
        logger.info(f"Found {len(drivers)} pending drivers for admin {current_user.id}.")
        return drivers
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Error listing pending drivers: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error listing drivers.")

@router.get("/verifications/cars/pending", response_model=List[CarResponse])
async def list_cars_pending_verification(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="...")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="...")] = 20
) -> List[CarResponse]:
    # list_cars_pending_verification CRUD already eager loads Car.driver.
    # CarResponse doesn't include other deep nests from Car model itself.
    logger.info(f"Admin {current_user.id} fetching cars pending. Skip: {skip}, Limit: {limit}")
    try:
        cars = await admin_crud.list_cars_pending_verification(session=db, skip=skip, limit=limit)
        logger.info(f"Found {len(cars)} pending cars for admin {current_user.id}.")
        return cars
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Error listing pending cars: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error listing cars.")

@router.get("/trips", response_model=List[TripResponse])
async def admin_list_all_trips(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="...")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="...")] = 20
) -> List[TripResponse]:
    # admin_crud.list_all_trips already eager loads Trip.driver and Trip.car.
    logger.info(f"Admin {current_user.id} listing all trips. Skip: {skip}, Limit: {limit}")
    try:
        trips = await admin_crud.list_all_trips(session=db, skip=skip, limit=limit)
        logger.info(f"Admin {current_user.id} retrieved {len(trips)} trips.")
        return trips
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Error listing all trips for admin: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error listing trips.")

# --- Write Endpoints ---
@router.post("/verifications/drivers/{driver_id}/approve", response_model=UserResponse)
async def approve_driver_verification(
    driver_id: uuid.UUID, request: AdminUpdateStatusRequest,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserResponse:
    logger.info(f"Admin {current_user.id} approving driver {driver_id}.")
    try:
        # No db.begin_nested()
        driver = await admin_crud.get_driver_user_by_id(session=db, driver_id=driver_id)
        if not driver:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Driver {driver_id} not found or not a driver.")
        updated_driver = await admin_crud.update_driver_verification_status(
            session=db, driver_to_verify=driver, new_status=UserStatus.ACTIVE, admin_notes=request.admin_notes
        )
        # UserResponse is simple enough that refreshed 'updated_driver' from CRUD is fine.
        logger.info(f"Admin {current_user.id} approved driver {driver_id}.")
        return updated_driver
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Error approving driver {driver_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error approving driver.")

@router.post("/verifications/drivers/{driver_id}/reject", response_model=UserResponse)
async def reject_driver_verification(
    driver_id: uuid.UUID, request: AdminUpdateStatusRequest,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserResponse:
    logger.info(f"Admin {current_user.id} rejecting driver {driver_id}.")
    try:
        # No db.begin_nested()
        driver = await admin_crud.get_driver_user_by_id(session=db, driver_id=driver_id)
        if not driver:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Driver {driver_id} not found or not a driver.")
        updated_driver = await admin_crud.update_driver_verification_status(
            session=db, driver_to_verify=driver, new_status=UserStatus.BLOCKED, admin_notes=request.admin_notes
        )
        logger.info(f"Admin {current_user.id} rejected driver {driver_id}.")
        return updated_driver
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Error rejecting driver {driver_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error rejecting driver.")

@router.post("/verifications/cars/{car_id}/approve", response_model=CarResponse)
async def approve_car_verification(
    car_id: uuid.UUID, request: AdminUpdateStatusRequest,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CarResponse:
    logger.info(f"Admin {current_user.id} approving car {car_id}.")
    try:
        # No db.begin_nested()
        car = await admin_crud.get_car_by_id_simple(session=db, car_id=car_id)
        if not car:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Car {car_id} not found.")
        updated_car = await admin_crud.update_car_verification_status(
            session=db, car_to_verify=car, new_status=CarVerificationStatus.APPROVED, admin_notes=request.admin_notes
        )
        # CarResponse doesn't deeply nest ORM objects from Car that need special loading beyond what refresh in CRUD provides.
        logger.info(f"Admin {current_user.id} approved car {car_id}.")
        return updated_car
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Error approving car {car_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error approving car.")

@router.post("/verifications/cars/{car_id}/reject", response_model=CarResponse)
async def reject_car_verification(
    car_id: uuid.UUID, request: AdminUpdateStatusRequest,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CarResponse:
    logger.info(f"Admin {current_user.id} rejecting car {car_id}.")
    try:
        # No db.begin_nested()
        car = await admin_crud.get_car_by_id_simple(session=db, car_id=car_id)
        if not car:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Car {car_id} not found.")
        updated_car = await admin_crud.update_car_verification_status(
            session=db, car_to_verify=car, new_status=CarVerificationStatus.REJECTED, admin_notes=request.admin_notes
        )
        logger.info(f"Admin {current_user.id} rejected car {car_id}.")
        return updated_car
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Error rejecting car {car_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error rejecting car.")