# File: routers/bookings.py (Fixed with proper eager loading after transaction)

import logging
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.dependencies import get_current_active_user
from crud import booking_crud
from database import get_db
from models import User, UserRole, Booking, Trip, TripStatus, BookingStatus
from schemas import BookingCreate, BookingResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/bookings",
    tags=["bookings"]
)

@router.post(
    "/",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new booking",
    description="Create a new booking for a trip as an authenticated passenger."
)
async def create_booking(
    booking_in: BookingCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> BookingResponse:
    if current_user.role != UserRole.PASSENGER:
        logger.warning(f"User {current_user.id} attempted to create a booking without passenger role")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only passengers can create bookings."
        )
    try:
        booking_id: Optional[UUID] = None
        async with db.begin_nested():
            booking = await booking_crud.create_passenger_booking(
                session=db,
                booking_in=booking_in,
                passenger_id=current_user.id
            )
            booking_id = booking.id
            logger.info(f"Successfully created booking {booking.id} for passenger {current_user.id}")
        
        # After the transaction commits, re-fetch the booking with all relationships
        if booking_id:
            booking_result = await db.execute(
                select(Booking)
                .options(
                    selectinload(Booking.trip).options(
                        selectinload(Trip.driver),
                        selectinload(Trip.car)
                    ),
                    selectinload(Booking.passenger)
                )
                .where(Booking.id == booking_id)
            )
            booking_with_relations = booking_result.scalar_one_or_none()
            
            if not booking_with_relations:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to retrieve created booking."
                )
            
            return booking_with_relations
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Booking creation failed."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in create_booking: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.get(
    "/my-bookings",
    response_model=List[BookingResponse],
    summary="Get my bookings",
    description="Get a list of all bookings made by the authenticated passenger."
)
async def get_my_bookings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return")] = 20
) -> List[BookingResponse]:
    if current_user.role != UserRole.PASSENGER:
        logger.warning(f"User {current_user.id} attempted to view bookings without passenger role")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only passengers can view their bookings."
        )
    try:
        bookings = await booking_crud.get_passenger_bookings(
            session=db,
            passenger_id=current_user.id,
            skip=skip,
            limit=limit
        )
        logger.info(f"Successfully retrieved {len(bookings)} bookings for passenger {current_user.id}")
        return bookings
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_my_bookings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.get(
    "/{booking_id}",
    response_model=BookingResponse,
    summary="Get booking details",
    description="Get detailed information about a specific booking."
)
async def get_booking(
    booking_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> BookingResponse:
    if current_user.role != UserRole.PASSENGER:
        logger.warning(f"User {current_user.id} attempted to view booking {booking_id} without passenger role")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only passengers can view booking details."
        )
    try:
        booking = await booking_crud.get_booking_by_id_and_passenger(
            session=db,
            booking_id=booking_id,
            passenger_id=current_user.id
        )
        if not booking:
            logger.warning(f"Booking {booking_id} not found or not owned by passenger {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found or you do not have permission to view it."
            )
        return booking
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_booking: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.post(
    "/{booking_id}/cancel",
    response_model=BookingResponse,
    summary="Cancel my booking",
    description="Cancel one of your bookings as an authenticated passenger."
)
async def cancel_my_booking(
    booking_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> BookingResponse:
    if current_user.role != UserRole.PASSENGER:
        logger.warning(f"User {current_user.id} attempted to cancel booking {booking_id} without passenger role")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only passengers can cancel their bookings."
        )
    try:
        cancelled_booking_id: Optional[UUID] = None
        async with db.begin_nested():
            booking = await booking_crud.get_booking_by_id_and_passenger(
                session=db,
                booking_id=booking_id,
                passenger_id=current_user.id
            )
            if not booking:
                logger.warning(f"Booking {booking_id} not found or not owned by passenger {current_user.id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found or you do not have permission to cancel it."
                )
            cancelled_booking = await booking_crud.cancel_passenger_booking(
                session=db,
                booking_to_cancel=booking
            )
            cancelled_booking_id = cancelled_booking.id
            logger.info(f"Successfully cancelled booking {booking_id} for passenger {current_user.id}")
        
        # Re-fetch with all relationships after transaction
        if cancelled_booking_id:
            booking_result = await db.execute(
                select(Booking)
                .options(
                    selectinload(Booking.trip).options(
                        selectinload(Trip.driver),
                        selectinload(Trip.car)
                    ),
                    selectinload(Booking.passenger)
                )
                .where(Booking.id == cancelled_booking_id)
            )
            booking_with_relations = booking_result.scalar_one_or_none()
            
            if not booking_with_relations:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to retrieve cancelled booking."
                )
            
            return booking_with_relations
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Booking cancellation failed."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in cancel_my_booking: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )