# File: routers/trips.py (Complete fixed version)

import logging
from datetime import date
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.dependencies import get_current_active_user
from crud import trip_crud
from database import get_db
from models import User, UserRole, Trip, Car
from schemas import TripCreate, TripResponse, TripUpdate

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/trips",
    tags=["trips"]
)

@router.post(
    "/",
    response_model=TripResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new trip",
    description="Create a new trip as an authenticated driver. Requires a valid car ID and trip details."
)
async def create_trip(
    trip_in: TripCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TripResponse:
    if current_user.role != UserRole.DRIVER:
        logger.warning(f"User {current_user.id} attempted to create a trip without driver role")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can create trips.")
    
    try:
        created_trip_id: Optional[UUID] = None
        async with db.begin_nested():
            trip_shell = await trip_crud.create_driver_trip(
                session=db, trip_in=trip_in, driver_id=current_user.id
            )
            created_trip_id = trip_shell.id
        
        if created_trip_id is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Trip creation failed to return an ID.")

        final_trip_result = await db.execute(
            select(Trip).options(selectinload(Trip.driver), selectinload(Trip.car)).where(Trip.id == created_trip_id)
        )
        trip_to_return = final_trip_result.scalar_one_or_none()

        if not trip_to_return:
            logger.error(f"Failed to re-fetch trip {created_trip_id} for response after transaction.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to confirm trip details.")
        
        logger.info(f"Successfully created and retrieved trip {trip_to_return.id} for driver {current_user.id}")
        return trip_to_return
    except HTTPException:
        raise 
    except Exception as e:
        logger.error(f"Unexpected error in create_trip router: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.get(
    "/search",
    response_model=List[TripResponse],
    summary="Search for available trips",
    description="Search for available trips based on various criteria. All parameters are optional."
)
async def search_trips(
    db: Annotated[AsyncSession, Depends(get_db)],
    from_location: Annotated[str, Query(description="Location to search in from_location_text")] = None,
    to_location: Annotated[str, Query(description="Location to search in to_location_text")] = None,
    departure_date: Annotated[date, Query(description="Date to match in departure_datetime (YYYY-MM-DD)")] = None,
    seats_needed: Annotated[int, Query(ge=1, description="Minimum number of available seats required")] = 1,
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return")] = 20
) -> List[TripResponse]:
    # CRUD search_trips already eager loads driver and car
    trips = await trip_crud.search_trips(
        session=db, from_location=from_location, to_location=to_location,
        departure_date=departure_date, seats_needed=seats_needed, skip=skip, limit=limit
    )
    return trips

@router.get(
    "/my-created",
    response_model=List[TripResponse],
    summary="Get my created trips",
    description="Get a list of all trips created by the authenticated driver."
)
async def get_my_created_trips(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return")] = 20
) -> List[TripResponse]:
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can view their created trips.")
    # CRUD get_driver_created_trips already eager loads driver and car
    trips = await trip_crud.get_driver_created_trips(
        session=db, driver_id=current_user.id, skip=skip, limit=limit
    )
    logger.info(f"Successfully retrieved {len(trips)} trips for driver {current_user.id}")
    return trips 

@router.get(
    "/{trip_id}",
    response_model=TripResponse,
    summary="Get trip details",
    description="Get detailed information about a specific trip."
)
async def get_trip(
    trip_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TripResponse:
    # CRUD get_trip_by_id already eager loads driver and car
    trip = await trip_crud.get_trip_by_id(session=db, trip_id=trip_id)
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")
    return trip 

@router.patch(
    "/{trip_id}",
    response_model=TripResponse,
    summary="Update my trip",
    description="Update details of one of your trips as an authenticated driver."
)
async def update_my_trip(
    trip_id: UUID,
    trip_in: TripUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TripResponse:
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can update their trips.")
    
    try:
        updated_trip_id: Optional[UUID] = None
        async with db.begin_nested():
            trip_to_modify = await trip_crud.get_driver_trip_by_id(
                session=db, trip_id=trip_id, driver_id=current_user.id
            )
            if not trip_to_modify:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found or you do not have permission to update it.")
            
            # Fixed: Removed the extra current_driver_id parameter
            trip_shell = await trip_crud.update_driver_trip(
                session=db, trip_to_update=trip_to_modify, trip_in=trip_in
            )
            updated_trip_id = trip_shell.id
        
        if updated_trip_id is None:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Trip update failed to return an ID.")

        final_trip_result = await db.execute(
            select(Trip).options(selectinload(Trip.driver), selectinload(Trip.car)).where(Trip.id == updated_trip_id)
        )
        trip_to_return = final_trip_result.scalar_one_or_none()

        if not trip_to_return:
            logger.error(f"Failed to re-fetch trip {updated_trip_id} for response after update transaction.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to confirm trip update details.")
            
        logger.info(f"Successfully updated and retrieved trip {trip_id} for driver {current_user.id}")
        return trip_to_return
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in update_my_trip router: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.post(
    "/{trip_id}/cancel",
    response_model=TripResponse,
    summary="Cancel my trip",
    description="Cancel one of your trips as an authenticated driver. This will also cancel all confirmed bookings on the trip."
)
async def cancel_my_trip(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TripResponse:
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can cancel their trips.")
    
    try:
        cancelled_trip_id: Optional[UUID] = None
        async with db.begin_nested():
            trip_to_modify = await trip_crud.get_driver_trip_by_id(
                session=db, trip_id=trip_id, driver_id=current_user.id
            )
            if not trip_to_modify:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found or you do not have permission to cancel it.")
            
            trip_shell = await trip_crud.cancel_driver_trip(
                session=db, trip_to_cancel=trip_to_modify
            )
            cancelled_trip_id = trip_shell.id
        
        if cancelled_trip_id is None:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Trip cancellation failed to return an ID.")

        final_trip_result = await db.execute(
            select(Trip).options(selectinload(Trip.driver), selectinload(Trip.car)).where(Trip.id == cancelled_trip_id)
        )
        trip_to_return = final_trip_result.scalar_one_or_none()

        if not trip_to_return:
            logger.error(f"Failed to re-fetch trip {cancelled_trip_id} for response after cancellation transaction.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to confirm trip cancellation details.")

        logger.info(f"Successfully cancelled and retrieved trip {trip_id} for driver {current_user.id}")
        return trip_to_return
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in cancel_my_trip router: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")