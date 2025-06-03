# File: routers/trips.py (Refactored for dependency-level transactions)

import logging
from datetime import date
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select # For re-fetch
from sqlalchemy.orm import selectinload # For re-fetch

from auth.dependencies import get_current_active_user
from crud import trip_crud
from database import get_db
from models import User, UserRole, Trip, Car # Added Trip, Car for selectinload context
from schemas import TripCreate, TripResponse, TripUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trips", tags=["trips"])

@router.post("/", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def create_trip(
    trip_in: TripCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TripResponse:
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can create trips.")
    try:
        # No db.begin_nested()
        created_trip_shell = await trip_crud.create_driver_trip(session=db, trip_in=trip_in, driver_id=current_user.id)
        
        # get_db will commit. Re-fetch for TripResponse which includes driver and car.
        trip_result = await db.execute(
            select(Trip).options(selectinload(Trip.driver), selectinload(Trip.car))
            .where(Trip.id == created_trip_shell.id)
        )
        trip_to_return = trip_result.scalar_one_or_none()
        if not trip_to_return:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve created trip for response.")

        logger.info(f"Successfully created trip {trip_to_return.id} for driver {current_user.id}")
        return trip_to_return
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in create_trip: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

# --- GET endpoints remain largely the same ---
# search_trips and get_my_created_trips already call CRUDs that eager load.
# get_trip already calls a CRUD that eager loads.

@router.get("/search", response_model=List[TripResponse])
async def search_trips(
    db: Annotated[AsyncSession, Depends(get_db)],
    from_location: Annotated[str, Query(description="...")] = None,
    to_location: Annotated[str, Query(description="...")] = None,
    departure_date: Annotated[date, Query(description="...")] = None,
    seats_needed: Annotated[int, Query(ge=1, description="...")] = 1,
    skip: Annotated[int, Query(ge=0, description="...")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="...")] = 20
) -> List[TripResponse]:
    trips = await trip_crud.search_trips(session=db, from_location=from_location, to_location=to_location, departure_date=departure_date, seats_needed=seats_needed, skip=skip, limit=limit)
    return trips

@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(trip_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> TripResponse:
    trip = await trip_crud.get_trip_by_id(session=db, trip_id=trip_id)
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")
    return trip 

@router.get("/my-created", response_model=List[TripResponse])
async def get_my_created_trips(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="...")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="...")] = 20
) -> List[TripResponse]:
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can view their created trips.")
    trips = await trip_crud.get_driver_created_trips(session=db, driver_id=current_user.id, skip=skip, limit=limit)
    logger.info(f"Successfully retrieved {len(trips)} trips for driver {current_user.id}")
    return trips 

@router.patch("/{trip_id}", response_model=TripResponse)
async def update_my_trip(
    trip_id: UUID, trip_in: TripUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TripResponse:
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can update their trips.")
    try:
        # No db.begin_nested()
        trip = await trip_crud.get_driver_trip_by_id(session=db, trip_id=trip_id, driver_id=current_user.id)
        if not trip:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found or you do not have permission to update it.")
        
        updated_trip_shell = await trip_crud.update_driver_trip(session=db, trip_to_update=trip, trip_in=trip_in, current_driver_id=current_user.id)
        
        # get_db will commit. Re-fetch for TripResponse.
        trip_result = await db.execute(
            select(Trip).options(selectinload(Trip.driver), selectinload(Trip.car))
            .where(Trip.id == updated_trip_shell.id)
        )
        trip_to_return = trip_result.scalar_one_or_none()
        if not trip_to_return:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve updated trip for response.")

        logger.info(f"Successfully updated trip {trip_to_return.id} for driver {current_user.id}")
        return trip_to_return
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_my_trip: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.post("/{trip_id}/cancel", response_model=TripResponse)
async def cancel_my_trip(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TripResponse:
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can cancel their trips.")
    try:
        # No db.begin_nested()
        trip = await trip_crud.get_driver_trip_by_id(session=db, trip_id=trip_id, driver_id=current_user.id)
        if not trip:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found or you do not have permission to cancel it.")
        
        cancelled_trip_shell = await trip_crud.cancel_driver_trip(session=db, trip_to_cancel=trip)
        
        # get_db will commit. Re-fetch for TripResponse.
        trip_result = await db.execute(
            select(Trip).options(selectinload(Trip.driver), selectinload(Trip.car))
            .where(Trip.id == cancelled_trip_shell.id)
        )
        trip_to_return = trip_result.scalar_one_or_none()
        if not trip_to_return:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve cancelled trip for response.")
            
        logger.info(f"Successfully cancelled trip {trip_to_return.id} for driver {current_user.id}")
        return trip_to_return
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in cancel_my_trip: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")