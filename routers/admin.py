# File: routers/admin.py (Corrected with Claude's suggested Query pattern)

import logging
import uuid
from typing import Annotated, List # Optional removed from here if not used elsewhere

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_admin_user
from crud import admin_crud
from database import get_db
from models import Car, CarVerificationStatus, User, UserStatus # Ensure Car is imported
from schemas import (
    AdminUpdateStatusRequest,
    CarResponse,
    UserResponse,
    TripResponse # For admin_list_all_trips
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_admin_user)]
)

@router.get(
    "/verifications/drivers/pending",
    response_model=List[UserResponse],
    summary="List drivers pending verification",
    description="Get a list of drivers whose accounts are pending verification by an admin."
)
async def list_drivers_pending_verification(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return")] = 20
) -> List[UserResponse]:
    """
    Retrieve a list of driver users pending verification.
    """
    logger.info(f"Admin {current_user.id} fetching drivers pending verification. Skip: {skip}, Limit: {limit}")
    try:
        drivers = await admin_crud.list_drivers_pending_verification(session=db, skip=skip, limit=limit)
        logger.info(f"Found {len(drivers)} drivers pending verification for admin {current_user.id}.")
        return drivers
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching drivers pending verification for admin {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.post(
    "/verifications/drivers/{driver_id}/approve",
    response_model=UserResponse,
    summary="Approve a driver's verification",
    description="Approve a driver's account, changing their status to ACTIVE."
)
async def approve_driver_verification(
    driver_id: uuid.UUID,
    request: AdminUpdateStatusRequest,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserResponse:
    """
    Approve a driver's verification.
    """
    logger.info(f"Admin {current_user.id} attempting to approve driver {driver_id}.")
    
    try:
        async with db.begin_nested():
            driver = await admin_crud.get_driver_user_by_id(session=db, driver_id=driver_id)
            if not driver:
                logger.warning(f"Admin {current_user.id} attempted to approve non-existent or non-driver user {driver_id}.")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Driver with ID {driver_id} not found or is not a driver."
                )

            updated_driver = await admin_crud.update_driver_verification_status(
                session=db,
                driver_to_verify=driver,
                new_status=UserStatus.ACTIVE,
                admin_notes=request.admin_notes
            )
            logger.info(f"Admin {current_user.id} successfully approved driver {driver_id}.")
            return updated_driver
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving driver {driver_id} by admin {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.post(
    "/verifications/drivers/{driver_id}/reject",
    response_model=UserResponse,
    summary="Reject/Block a driver's verification",
    description="Reject a driver's account, changing their status to BLOCKED."
)
async def reject_driver_verification(
    driver_id: uuid.UUID,
    request: AdminUpdateStatusRequest,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserResponse:
    """
    Reject/Block a driver's verification.
    """
    logger.info(f"Admin {current_user.id} attempting to reject driver {driver_id}.")
    
    try:
        async with db.begin_nested():
            driver = await admin_crud.get_driver_user_by_id(session=db, driver_id=driver_id)
            if not driver:
                logger.warning(f"Admin {current_user.id} attempted to reject non-existent or non-driver user {driver_id}.")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Driver with ID {driver_id} not found or is not a driver."
                )

            updated_driver = await admin_crud.update_driver_verification_status(
                session=db,
                driver_to_verify=driver,
                new_status=UserStatus.BLOCKED,
                admin_notes=request.admin_notes
            )
            logger.info(f"Admin {current_user.id} successfully rejected driver {driver_id}.")
            return updated_driver
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting driver {driver_id} by admin {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.get(
    "/verifications/cars/pending",
    response_model=List[CarResponse],
    summary="List cars pending verification",
    description="Get a list of cars that are pending verification by an admin."
)
async def list_cars_pending_verification(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return")] = 20
) -> List[CarResponse]:
    """
    Retrieve a list of cars pending verification.
    """
    logger.info(f"Admin {current_user.id} fetching cars pending verification. Skip: {skip}, Limit: {limit}")
    try:
        cars = await admin_crud.list_cars_pending_verification(session=db, skip=skip, limit=limit)
        logger.info(f"Found {len(cars)} cars pending verification for admin {current_user.id}.")
        return cars
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching cars pending verification for admin {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.post(
    "/verifications/cars/{car_id}/approve",
    response_model=CarResponse,
    summary="Approve a car's verification",
    description="Approve a car, changing its verification status to APPROVED."
)
async def approve_car_verification(
    car_id: uuid.UUID,
    request: AdminUpdateStatusRequest,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CarResponse:
    """
    Approve a car's verification.
    """
    logger.info(f"Admin {current_user.id} attempting to approve car {car_id}.")
    
    try:
        async with db.begin_nested():
            car = await admin_crud.get_car_by_id_simple(session=db, car_id=car_id)
            if not car:
                logger.warning(f"Admin {current_user.id} attempted to approve non-existent car {car_id}.")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Car with ID {car_id} not found."
                )

            updated_car = await admin_crud.update_car_verification_status(
                session=db,
                car_to_verify=car,
                new_status=CarVerificationStatus.APPROVED,
                admin_notes=request.admin_notes
            )
            logger.info(f"Admin {current_user.id} successfully approved car {car_id}.")
            return updated_car
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving car {car_id} by admin {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.post(
    "/verifications/cars/{car_id}/reject",
    response_model=CarResponse,
    summary="Reject a car's verification",
    description="Reject a car, changing its verification status to REJECTED."
)
async def reject_car_verification(
    car_id: uuid.UUID,
    request: AdminUpdateStatusRequest,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CarResponse:
    """
    Reject a car's verification.
    """
    logger.info(f"Admin {current_user.id} attempting to reject car {car_id}.")
    
    try:
        async with db.begin_nested():
            car = await admin_crud.get_car_by_id_simple(session=db, car_id=car_id)
            if not car:
                logger.warning(f"Admin {current_user.id} attempted to reject non-existent car {car_id}.")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Car with ID {car_id} not found."
                )

            updated_car = await admin_crud.update_car_verification_status(
                session=db,
                car_to_verify=car,
                new_status=CarVerificationStatus.REJECTED,
                admin_notes=request.admin_notes
            )
            logger.info(f"Admin {current_user.id} successfully rejected car {car_id}.")
            return updated_car
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting car {car_id} by admin {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.get(
    "/trips",
    response_model=List[TripResponse],
    summary="Admin: List all trips",
    description="Allows an admin to retrieve a paginated list of all trips in the system, with driver and car details."
)
async def admin_list_all_trips(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return")] = 20
) -> List[TripResponse]:
    """
    Admin endpoint to get a list of all trips in the system with pagination.
    """
    logger.info(f"Admin {current_user.id} requesting list of all trips. Skip: {skip}, Limit: {limit}")
    try:
        trips = await admin_crud.list_all_trips(session=db, skip=skip, limit=limit)
        logger.info(f"Admin {current_user.id} retrieved {len(trips)} trips.")
        return trips
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error for admin {current_user.id} while listing all trips: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )