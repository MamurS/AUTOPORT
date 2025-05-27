# File: crud/booking_crud.py (Corrected for router-level transactions)

import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload 
from sqlalchemy.exc import SQLAlchemyError

from models import Booking, Trip, TripStatus, BookingStatus, User # User for selectinload on passenger
from schemas import BookingCreate

logger = logging.getLogger(__name__)

async def get_booking_by_trip_and_passenger(
    session: AsyncSession,
    trip_id: UUID,
    passenger_id: UUID
) -> Optional[Booking]:
    """
    Check if a passenger already has a confirmed booking for a specific trip.
    Eagerly loads trip and passenger.
    """
    try:
        result = await session.execute(
            select(Booking)
            .options(
                selectinload(Booking.trip), 
                selectinload(Booking.passenger)
            )
            .where(
                Booking.trip_id == trip_id,
                Booking.passenger_id == passenger_id,
                Booking.status == BookingStatus.CONFIRMED
            )
        )
        booking = result.scalar_one_or_none()
        if booking:
            logger.info(f"Found existing confirmed booking {booking.id} for trip {trip_id} by passenger {passenger_id}")
        return booking
    except SQLAlchemyError as e:
        logger.error(f"DB error checking for existing booking for trip {trip_id} by passenger {passenger_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error checking for existing booking.")
    except Exception as e:
        logger.error(f"Unexpected error checking for existing booking for trip {trip_id} by passenger {passenger_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error checking for existing booking.")


async def create_passenger_booking(
    session: AsyncSession, # Session is passed in
    booking_in: BookingCreate,
    passenger_id: UUID
) -> Booking: # Returns the Booking ORM object; caller will handle full loading for response
    """
    Prepares a new booking for a passenger on a trip and updates the trip.
    NOTE: This function expects the caller (router) to handle transactions (commit/rollback).
    It will session.add() new/modified objects and session.flush() to get IDs or check constraints.
    """
    # 1. Fetch the Trip
    trip_result = await session.execute(
        select(Trip).where(Trip.id == booking_in.trip_id) # Consider .with_for_update() if high concurrency for seats
    )
    trip: Optional[Trip] = trip_result.scalar_one_or_none()
    
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")
    if trip.status not in [TripStatus.SCHEDULED, TripStatus.FULL]: # Can only book scheduled or full (if last seat logic allows)
        # If trip is FULL, it means available_seats is 0. The check below will handle it.
        # More precise check for booking:
        if trip.status != TripStatus.SCHEDULED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Trip is not available for booking (not scheduled).")

    if trip.departure_datetime <= datetime.now(): # TZ Note
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot book a trip that has already departed or is departing now.")
    if trip.available_seats < booking_in.seats_booked:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not enough available seats on this trip.")
        
    existing_booking = await get_booking_by_trip_and_passenger(
        session=session, trip_id=trip.id, passenger_id=passenger_id
    )
    if existing_booking:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You have already booked this trip.")
        
    # Modify trip object (SQLAlchemy tracks this)
    trip.available_seats -= booking_in.seats_booked
    if trip.available_seats == 0:
        trip.status = TripStatus.FULL
    
    # session.add(trip) # Not strictly necessary if trip was loaded from this session, but good for clarity
        
    total_price = booking_in.seats_booked * trip.price_per_seat
    booking = Booking(
        trip_id=trip.id,
        passenger_id=passenger_id,
        seats_booked=booking_in.seats_booked,
        total_price=total_price,
        status=BookingStatus.CONFIRMED # Default status
    )
    
    session.add(booking) # Add the new booking object
    
    # Flush to ensure booking gets an ID and any DB constraints are checked before router commits.
    # Also, trip modifications are sent.
    try:
        await session.flush()
        # Refresh to get DB-generated values like booking.id, booking.booking_time, trip.updated_at
        await session.refresh(booking) 
        await session.refresh(trip) 
    except SQLAlchemyError as e: # Catch flush/refresh errors
        logger.error(f"Database error during booking flush/refresh: {e}", exc_info=True)
        # The router's transaction block will handle rollback
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error finalizing booking details.")

    logger.info(f"Booking {booking.id} prepared for passenger {passenger_id} on trip {trip.id}")
    return booking # Return the booking object; router will commit and then re-fetch for response.

async def get_passenger_bookings(
    session: AsyncSession,
    passenger_id: UUID,
    skip: int = 0,
    limit: int = 20
) -> List[Booking]:
    """
    Get all bookings for a specific passenger, with eager loading for response.
    """
    try:
        query = (
            select(Booking)
            .options(
                selectinload(Booking.trip).options(
                    selectinload(Trip.driver),
                    selectinload(Trip.car)
                ),
                selectinload(Booking.passenger)
            )
            .where(Booking.passenger_id == passenger_id)
            .order_by(Booking.booking_time.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(query)
        bookings = result.scalars().all()
        logger.info(f"Found {len(bookings)} bookings for passenger {passenger_id}")
        return bookings
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching bookings for passenger {passenger_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching your bookings.")
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"Unexpected error fetching bookings for passenger {passenger_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching your bookings.")


async def get_booking_by_id_and_passenger(
    session: AsyncSession,
    booking_id: UUID,
    passenger_id: UUID
) -> Optional[Booking]:
    """
    Get a specific booking by ID, ensuring it belongs to the specified passenger.
    Eagerly loads trip (with its driver/car) and the passenger.
    """
    try:
        result = await session.execute(
            select(Booking)
            .options(
                selectinload(Booking.trip).options(
                    selectinload(Trip.driver),
                    selectinload(Trip.car)
                ),
                selectinload(Booking.passenger)
            )
            .where(
                Booking.id == booking_id,
                Booking.passenger_id == passenger_id
            )
        )
        booking = result.scalar_one_or_none()
        if booking:
            logger.info(f"Found booking {booking_id} for passenger {passenger_id}")
        else:
            logger.info(f"Booking {booking_id} not found or not owned by passenger {passenger_id}")
        return booking
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching booking {booking_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching the booking.")
    except Exception as e:
        logger.error(f"Unexpected error fetching booking {booking_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching the booking.")


async def cancel_passenger_booking(
    session: AsyncSession,
    booking_to_cancel: Booking # Assumes booking_to_cancel.trip is already loaded by caller
) -> Booking: # Returns the Booking ORM object; caller handles full loading for response
    """
    Prepares a booking cancellation and updates the trip.
    NOTE: This function expects the caller (router) to handle transactions (commit/rollback).
    """
    trip = booking_to_cancel.trip
    if not trip: # Defensive reload if not loaded (though get_booking_by_id_and_passenger should load it)
        trip_result = await session.execute(select(Trip).where(Trip.id == booking_to_cancel.trip_id))
        trip = trip_result.scalar_one_or_none()
        if not trip:
            # This indicates a serious data integrity issue or stale booking object
            logger.error(f"Associated trip {booking_to_cancel.trip_id} not found for booking {booking_to_cancel.id} during cancellation prep.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Associated trip data inconsistent for cancellation.")

    if booking_to_cancel.status != BookingStatus.CONFIRMED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking is not in a cancellable state.")
    if trip.status not in [TripStatus.SCHEDULED, TripStatus.FULL]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking cannot be cancelled as the trip is not in a suitable state.")
    
    booking_to_cancel.status = BookingStatus.CANCELLED_BY_PASSENGER
    trip.available_seats += booking_to_cancel.seats_booked
    if trip.status == TripStatus.FULL and trip.available_seats > 0:
        trip.status = TripStatus.SCHEDULED
    
    session.add(booking_to_cancel)
    # session.add(trip) # trip is already part of the session
    
    try:
        await session.flush()
        await session.refresh(booking_to_cancel)
        await session.refresh(trip)
    except SQLAlchemyError as e:
        logger.error(f"Database error during booking cancellation flush/refresh: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error finalizing booking cancellation details.")

    logger.info(f"Booking {booking_to_cancel.id} prepared for cancellation for passenger {booking_to_cancel.passenger_id}")
    return booking_to_cancel # Return the modified booking object

async def get_confirmed_bookings_for_trip(
    session: AsyncSession,
    trip_id: UUID
) -> List[Booking]:
    """
    Get all confirmed bookings for a specific trip.
    """
    # ... (This function is read-only, no transaction changes needed here, but good error handling is present)
    try:
        result = await session.execute(
            select(Booking).where(
                Booking.trip_id == trip_id,
                Booking.status == BookingStatus.CONFIRMED
            )
        )
        bookings = result.scalars().all()
        logger.info(f"Found {len(bookings)} confirmed bookings for trip {trip_id}")
        return bookings
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching confirmed bookings for trip {trip_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching confirmed bookings.")
    except Exception as e:
        logger.error(f"Unexpected error fetching confirmed bookings for trip {trip_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching confirmed bookings.")