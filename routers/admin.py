# File: routers/admin.py (Complete updated version with conversion functions)

import logging
import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_admin_user
from crud import admin_crud
from database import get_db
from models import Car, CarVerificationStatus, User, UserStatus, Trip
from schemas import (
    AdminUpdateStatusRequest,
    CarResponse,
    UserResponse,
    TripResponse 
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_admin_user)])

# --- CONVERSION HELPER FUNCTIONS ---

def convert_user_to_response(user: User) -> UserResponse:
    """Convert SQLAlchemy User model to UserResponse dataclass"""
    return UserResponse(
        id=user.id,
        phone_number=user.phone_number,
        status=user.status,
        created_at=user.created_at,
        updated_at=user.updated_at,
        full_name=user.full_name,
        role=user.role,
        profile_image_url=user.profile_image_url,
        date_of_birth=user.date_of_birth,
        gender=user.gender,
        spoken_languages=user.spoken_languages or ["uz"],
        bio=user.bio,
        email=user.email,
        preferred_language=user.preferred_language or "uz",
        currency_preference=user.currency_preference or "UZS",
        admin_verification_notes=user.admin_verification_notes,
        is_phone_verified=user.is_phone_verified or False,
        is_email_verified=user.is_email_verified or False
    )

def convert_car_to_response(car: Car) -> CarResponse:
    """Convert SQLAlchemy Car model to CarResponse dataclass"""
    return CarResponse(
        id=car.id,
        driver_id=car.driver_id,
        verification_status=car.verification_status,
        created_at=car.created_at,
        updated_at=car.updated_at,
        make=car.make or "",
        model=car.model or "",
        license_plate=car.license_plate or "",
        color=car.color or "",
        seats_count=car.seats_count or 4,
        is_default=car.is_default or False,
        year=car.year,
        car_image_url=car.car_image_url,
        features=car.features or [],
        comfort_level=car.comfort_level or "economy",
        admin_verification_notes=car.admin_verification_notes
    )

def convert_trip_to_response(trip: Trip) -> TripResponse:
    """Convert SQLAlchemy Trip model to TripResponse dataclass"""
    driver_response = None
    if hasattr(trip, 'driver') and trip.driver:
        driver_response = convert_user_to_response(trip.driver)
    
    car_response = None
    if hasattr(trip, 'car') and trip.car:
        car_response = convert_car_to_response(trip.car)
    
    return TripResponse(
        id=trip.id,
        driver_id=trip.driver_id,
        car_id=trip.car_id,
        available_seats=trip.available_seats,
        status=trip.status,
        created_at=trip.created_at,
        updated_at=trip.updated_at,
        from_location_text=trip.from_location_text or "",
        to_location_text=trip.to_location_text or "",
        departure_datetime=trip.departure_datetime,
        estimated_arrival_datetime=trip.estimated_arrival_datetime,
        price_per_seat=trip.price_per_seat or 0,
        total_seats_offered=trip.total_seats_offered or 1,
        additional_info=trip.additional_info,
        intermediate_stops=trip.intermediate_stops or [],
        trip_preferences=trip.trip_preferences or {},
        is_recurring=trip.is_recurring or False,
        recurring_pattern=trip.recurring_pattern,
        is_instant_booking=trip.is_instant_booking or False,
        max_detour_km=trip.max_detour_km or 5,
        price_negotiable=trip.price_negotiable or False,
        estimated_distance_km=trip.estimated_distance_km,
        estimated_duration_minutes=trip.estimated_duration_minutes,
        driver=driver_response,
        car=car_response
    )

# --- GET LIST ENDPOINTS ---

@router.get("/verifications/drivers/pending", response_model=List[UserResponse])
async def list_drivers_pending_verification(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return")] = 20
) -> List[UserResponse]:
    logger.info(f"Admin {current_user.id} fetching drivers pending. Skip: {skip}, Limit: {limit}")
    try:
        drivers = await admin_crud.list_drivers_pending_verification(session=db, skip=skip, limit=limit)
        logger.info(f"Found {len(drivers)} pending drivers for admin {current_user.id}.")
        
        # Convert SQLAlchemy objects to UserResponse dataclasses
        return [convert_user_to_response(driver) for driver in drivers]
        
    except HTTPException: 
        raise
    except Exception as e:
        logger.error(f"Error listing pending drivers: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error listing drivers.")

@router.get("/verifications/cars/pending", response_model=List[CarResponse])
async def list_cars_pending_verification(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return")] = 20
) -> List[CarResponse]:
    logger.info(f"Admin {current_user.id} fetching cars pending. Skip: {skip}, Limit: {limit}")
    try:
        cars = await admin_crud.list_cars_pending_verification(session=db, skip=skip, limit=limit)
        logger.info(f"Found {len(cars)} pending cars for admin {current_user.id}.")
        
        # Convert SQLAlchemy objects to CarResponse dataclasses
        return [convert_car_to_response(car) for car in cars]
        
    except HTTPException: 
        raise
    except Exception as e:
        logger.error(f"Error listing pending cars: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error listing cars.")

@router.get("/trips", response_model=List[TripResponse])
async def admin_list_all_trips(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return")] = 20
) -> List[TripResponse]:
    logger.info(f"Admin {current_user.id} listing all trips. Skip: {skip}, Limit: {limit}")
    try:
        trips = await admin_crud.list_all_trips(session=db, skip=skip, limit=limit)
        logger.info(f"Admin {current_user.id} retrieved {len(trips)} trips.")
        
        # Convert SQLAlchemy objects to TripResponse dataclasses
        return [convert_trip_to_response(trip) for trip in trips]
        
    except HTTPException: 
        raise
    except Exception as e:
        logger.error(f"Error listing all trips for admin: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error listing trips.")

# --- WRITE ENDPOINTS ---

@router.post("/verifications/drivers/{driver_id}/approve", response_model=UserResponse)
async def approve_driver_verification(
    driver_id: uuid.UUID, 
    request: AdminUpdateStatusRequest,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserResponse:
    logger.info(f"Admin {current_user.id} approving driver {driver_id}.")
    try:
        driver = await admin_crud.get_driver_user_by_id(session=db, driver_id=driver_id)
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Driver {driver_id} not found or not a driver."
            )
        
        updated_driver = await admin_crud.update_driver_verification_status(
            session=db, 
            driver_to_verify=driver, 
            new_status=UserStatus.ACTIVE, 
            admin_notes=request.admin_notes
        )
        
        logger.info(f"Admin {current_user.id} approved driver {driver_id}.")
        return convert_user_to_response(updated_driver)
        
    except HTTPException: 
        raise
    except Exception as e:
        logger.error(f"Error approving driver {driver_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error approving driver.")

@router.post("/verifications/drivers/{driver_id}/reject", response_model=UserResponse)
async def reject_driver_verification(
    driver_id: uuid.UUID, 
    request: AdminUpdateStatusRequest,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserResponse:
    logger.info(f"Admin {current_user.id} rejecting driver {driver_id}.")
    try:
        driver = await admin_crud.get_driver_user_by_id(session=db, driver_id=driver_id)
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Driver {driver_id} not found or not a driver."
            )
        
        updated_driver = await admin_crud.update_driver_verification_status(
            session=db, 
            driver_to_verify=driver, 
            new_status=UserStatus.BLOCKED, 
            admin_notes=request.admin_notes
        )
        
        logger.info(f"Admin {current_user.id} rejected driver {driver_id}.")
        return convert_user_to_response(updated_driver)
        
    except HTTPException: 
        raise
    except Exception as e:
        logger.error(f"Error rejecting driver {driver_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error rejecting driver.")

@router.post("/verifications/cars/{car_id}/approve", response_model=CarResponse)
async def approve_car_verification(
    car_id: uuid.UUID, 
    request: AdminUpdateStatusRequest,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CarResponse:
    logger.info(f"Admin {current_user.id} approving car {car_id}.")
    try:
        car = await admin_crud.get_car_by_id_simple(session=db, car_id=car_id)
        if not car:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Car {car_id} not found."
            )
        
        updated_car = await admin_crud.update_car_verification_status(
            session=db, 
            car_to_verify=car, 
            new_status=CarVerificationStatus.APPROVED, 
            admin_notes=request.admin_notes
        )
        
        logger.info(f"Admin {current_user.id} approved car {car_id}.")
        return convert_car_to_response(updated_car)
        
    except HTTPException: 
        raise
    except Exception as e:
        logger.error(f"Error approving car {car_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error approving car.")

@router.post("/verifications/cars/{car_id}/reject", response_model=CarResponse)
async def reject_car_verification(
    car_id: uuid.UUID, 
    request: AdminUpdateStatusRequest,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CarResponse:
    logger.info(f"Admin {current_user.id} rejecting car {car_id}.")
    try:
        car = await admin_crud.get_car_by_id_simple(session=db, car_id=car_id)
        if not car:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Car {car_id} not found."
            )
        
        updated_car = await admin_crud.update_car_verification_status(
            session=db, 
            car_to_verify=car, 
            new_status=CarVerificationStatus.REJECTED, 
            admin_notes=request.admin_notes
        )
        
        logger.info(f"Admin {current_user.id} rejected car {car_id}.")
        return convert_car_to_response(updated_car)
        
    except HTTPException: 
        raise
    except Exception as e:
        logger.error(f"Error rejecting car {car_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error rejecting car.")