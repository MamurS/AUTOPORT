# File: crud/trip_crud.py (Refactored for router-level transactions & consistent eager loading)

import logging
from datetime import datetime, date
from typing import Optional, List
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, func, and_ # update is not used here
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError

from models import Trip, Car, CarVerificationStatus, TripStatus, Booking, BookingStatus, User # User for eager loading
from schemas import TripCreate, TripUpdate
from crud import booking_crud # For cancel_driver_trip

logger = logging.getLogger(__name__)

async def get_car_by_id(session: AsyncSession, car_id: UUID) -> Optional[Car]:
    """Helper function to get a car by ID."""
    try:
        result = await session.execute(select(Car).where(Car.id == car_id))
        car = result.scalar_one_or_none()
        if car:
            logger.debug(f"Helper get_car_by_id: Found car {car_id}")
        else:
            logger.debug(f"Helper get_car_by_id: Car {car_id} not found")
        return car
    except SQLAlchemyError as e:
        logger.error(f"DB error in get_car_by_id for car {car_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving car information.")

async def create_driver_trip(
    session: AsyncSession,
    trip_in: TripCreate,
    driver_id: UUID
) -> Trip:
    """
    Prepares a new trip for a driver. Caller handles transaction and final eager loading for response.
    It will session.add() and session.flush()/refresh().
    """
    # 1. Verify Car Ownership and Approval (raises HTTPException if issues)
    car = await get_car_by_id(session, trip_in.car_id)
    if not car:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Car specified for trip not found.")
    if car.driver_id != driver_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Specified car not owned by driver.")
    if car.verification_status != CarVerificationStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Specified car is not approved for trips.")
        
    # 2. Validate departure_datetime
    if trip_in.departure_datetime <= datetime.now(): # TZ Note
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Departure datetime must be in the future.")
        
    # 3. Validate total_seats_offered against car's capacity
    max_passenger_seats = car.seats_count - 1
    if trip_in.total_seats_offered <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Total seats offered must be a positive number.")
    if trip_in.total_seats_offered > max_passenger_seats:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Total seats offered ({trip_in.total_seats_offered}) exceeds car capacity ({max_passenger_seats}).")
        
    trip = Trip(
        driver_id=driver_id,
        car_id=trip_in.car_id,
        from_location_text=trip_in.from_location_text,
        to_location_text=trip_in.to_location_text,
        departure_datetime=trip_in.departure_datetime,
        estimated_arrival_datetime=trip_in.estimated_arrival_datetime,
        price_per_seat=trip_in.price_per_seat,
        total_seats_offered=trip_in.total_seats_offered,
        available_seats=trip_in.total_seats_offered,
        additional_info=trip_in.additional_info
        # status defaults to SCHEDULED from model
    )
    session.add(trip)
    try:
        await session.flush()
        await session.refresh(trip)
    except SQLAlchemyError as e:
        logger.error(f"DB error during trip creation flush/refresh for driver {driver_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error finalizing trip creation details.")
    
    logger.info(f"Trip {trip.id} prepared for driver {driver_id}")
    return trip

async def search_trips(
    session: AsyncSession,
    from_location: Optional[str] = None,
    to_location: Optional[str] = None,
    departure_date: Optional[date] = None,
    seats_needed: int = 1,
    skip: int = 0,
    limit: int = 20
) -> List[Trip]:
    """Search for available trips, with eager loading for driver and car."""
    try:
        query = (
            select(Trip)
            .options(selectinload(Trip.driver), selectinload(Trip.car))
        )
        conditions = [
            Trip.status == TripStatus.SCHEDULED,
            Trip.departure_datetime > datetime.now(), # TZ Note
            Trip.available_seats >= seats_needed
        ]
        if from_location:
            conditions.append(Trip.from_location_text.ilike(f"%{from_location}%"))
        if to_location:
            conditions.append(Trip.to_location_text.ilike(f"%{to_location}%"))
        if departure_date:
            conditions.append(func.date(Trip.departure_datetime) == departure_date)
            
        query = query.where(and_(*conditions))
        query = query.order_by(Trip.departure_datetime.asc())
        query = query.offset(skip).limit(limit)
        
        result = await session.execute(query)
        trips = result.scalars().all()
        logger.info(f"Found {len(trips)} trips matching search criteria")
        return trips
    except SQLAlchemyError as e:
        logger.error(f"Database error searching trips: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while searching for trips.")

async def get_trip_by_id(
    session: AsyncSession,
    trip_id: UUID
) -> Optional[Trip]:
    """Get a trip by its ID, eagerly loading driver and car."""
    try:
        result = await session.execute(
            select(Trip)
            .options(selectinload(Trip.driver), selectinload(Trip.car))
            .where(Trip.id == trip_id)
        )
        trip = result.scalar_one_or_none()
        if trip:
            logger.info(f"Found trip {trip_id} with driver/car details")
        else:
            logger.info(f"Trip {trip_id} not found")
        return trip
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching trip {trip_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching the trip.")

async def get_driver_created_trips(
    session: AsyncSession,
    driver_id: UUID,
    skip: int = 0,
    limit: int = 20
) -> List[Trip]:
    """Get all trips created by a driver, with eager loading for driver and car."""
    try:
        query = (
            select(Trip)
            .options(selectinload(Trip.driver), selectinload(Trip.car))
            .where(Trip.driver_id == driver_id)
            .order_by(Trip.departure_datetime.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(query)
        trips = result.scalars().all()
        logger.info(f"Found {len(trips)} trips for driver {driver_id}")
        return trips
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching trips for driver {driver_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching driver's trips.")

async def get_driver_trip_by_id(
    session: AsyncSession,
    trip_id: UUID,
    driver_id: UUID
) -> Optional[Trip]:
    """Get a specific trip by ID owned by a driver, with eager loading."""
    try:
        result = await session.execute(
            select(Trip)
            .options(selectinload(Trip.driver), selectinload(Trip.car))
            .where(Trip.id == trip_id, Trip.driver_id == driver_id)
        )
        trip = result.scalar_one_or_none()
        if trip:
            logger.info(f"Found trip {trip_id} for driver {driver_id}")
        else:
            logger.info(f"Trip {trip_id} not found or not owned by driver {driver_id}")
        return trip
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching trip {trip_id} for driver {driver_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching the trip.")

async def get_booked_seats_count(session: AsyncSession, trip_id: UUID) -> int:
    """Get total confirmed seats booked for a trip."""
    try:
        result = await session.execute(
            select(func.sum(Booking.seats_booked))
            .where(Booking.trip_id == trip_id, Booking.status == BookingStatus.CONFIRMED)
        )
        booked_seats = result.scalar() or 0
        logger.info(f"Found {booked_seats} booked seats for trip {trip_id}")
        return booked_seats
    except SQLAlchemyError as e:
        logger.error(f"Database error counting booked seats for trip {trip_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error counting booked seats.")

async def update_driver_trip(
    session: AsyncSession,
    trip_to_update: Trip, # Assumed to be fetched with ownership verified by router
    trip_in: TripUpdate
) -> Trip:
    """Prepare update for a driver's trip. Caller handles transaction."""
    if trip_to_update.status not in [TripStatus.SCHEDULED, TripStatus.FULL]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Trip is not in an updatable state.")
            
    update_data = trip_in.model_dump(exclude_unset=True)
    
    if "car_id" in update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Changing the car for an existing trip is not supported via this update.")
            
    if "departure_datetime" in update_data:
        if update_data["departure_datetime"] <= datetime.now(): # TZ Note
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Departure datetime must be in the future.")
                
    if "total_seats_offered" in update_data:
        new_total_seats_offered = update_data["total_seats_offered"]
        booked_seats = await get_booked_seats_count(session, trip_to_update.id)
        if new_total_seats_offered < booked_seats:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Total seats offered cannot be less than already booked seats.")
        update_data["available_seats"] = new_total_seats_offered - booked_seats
        
        if "status" not in update_data: 
            if update_data["available_seats"] == 0:
                update_data["status"] = TripStatus.FULL
            elif trip_to_update.status == TripStatus.FULL and update_data["available_seats"] > 0:
                update_data["status"] = TripStatus.SCHEDULED
                
    for field, value in update_data.items():
        setattr(trip_to_update, field, value)
            
    session.add(trip_to_update)
    try:
        await session.flush()
        await session.refresh(trip_to_update)
    except SQLAlchemyError as e:
        logger.error(f"Database error during trip update flush/refresh for trip {trip_to_update.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error finalizing trip update.")
        
    logger.info(f"Trip {trip_to_update.id} details prepared for update by driver {trip_to_update.driver_id}")
    return trip_to_update

async def cancel_driver_trip(
    session: AsyncSession,
    trip_to_cancel: Trip # Assumed to be fetched with ownership verified by router
) -> Trip:
    """Prepare cancellation of a driver's trip and its bookings. Caller handles transaction."""
    if trip_to_cancel.status not in [TripStatus.SCHEDULED, TripStatus.FULL]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Trip is not in a state that can be cancelled by the driver.")
            
    trip_to_cancel.status = TripStatus.CANCELLED_BY_DRIVER
    
    confirmed_bookings = await booking_crud.get_confirmed_bookings_for_trip(
        session=session,
        trip_id=trip_to_cancel.id
    )
    
    updated_booking_ids = []
    for booking_item in confirmed_bookings:
        booking_item.status = BookingStatus.CANCELLED_BY_DRIVER
        session.add(booking_item)
        updated_booking_ids.append(booking_item.id)
            
    session.add(trip_to_cancel)
    try:
        await session.flush()
        await session.refresh(trip_to_cancel)
        for booking_id_to_refresh in updated_booking_ids: # Refresh individually if needed by caller
            # Usually not needed if caller only cares about the trip object primarily
            refreshed_booking = await session.get(Booking, booking_id_to_refresh) # Example
            if refreshed_booking: await session.refresh(refreshed_booking)

    except SQLAlchemyError as e:
        logger.error(f"Database error during trip cancellation flush/refresh for trip {trip_to_cancel.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error finalizing trip cancellation.")

    logger.info(f"Trip {trip_to_cancel.id} and {len(confirmed_bookings)} bookings prepared for cancellation")
    return trip_to_cancel