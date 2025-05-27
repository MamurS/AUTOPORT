# File: crud/admin_crud.py (Refactored for router-level transactions)

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError

from models import User, Car, UserStatus, UserRole, CarVerificationStatus, Trip # Trip for list_all_trips

logger = logging.getLogger(__name__)

async def get_driver_user_by_id(
    session: AsyncSession,
    driver_id: UUID
) -> Optional[User]:
    """
    Get a user by ID, ensuring they are a driver.
    """
    try:
        result = await session.execute(
            select(User).where(
                User.id == driver_id,
                User.role == UserRole.DRIVER
            )
        )
        driver = result.scalar_one_or_none()
        
        if driver:
            logger.info(f"Found driver {driver_id}")
        else:
            logger.info(f"Driver {driver_id} not found or is not a driver")
        return driver
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching driver {driver_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching the driver.")
    except Exception as e:
        logger.error(f"Unexpected error fetching driver {driver_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching the driver.")


async def get_car_by_id_simple(
    session: AsyncSession,
    car_id: UUID
) -> Optional[Car]:
    """
    Get a car by ID without ownership check.
    """
    try:
        result = await session.execute(
            select(Car).where(Car.id == car_id)
        )
        car = result.scalar_one_or_none()
        
        if car:
            logger.info(f"Found car {car_id}")
        else:
            logger.info(f"Car {car_id} not found")
        return car
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching car {car_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching the car.")
    except Exception as e:
        logger.error(f"Unexpected error fetching car {car_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching the car.")


async def list_drivers_pending_verification(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 20
) -> List[User]:
    """
    Get a list of drivers pending verification.
    """
    try:
        query = (
            select(User)
            .where(
                User.role == UserRole.DRIVER,
                User.status == UserStatus.PENDING_PROFILE_COMPLETION
            )
            .offset(skip)
            .limit(limit)
            .order_by(User.created_at.asc()) # Added an order for consistency
        )
        result = await session.execute(query)
        drivers = result.scalars().all()
        logger.info(f"Found {len(drivers)} drivers pending verification")
        return drivers
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching pending drivers: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching pending drivers.")
    except Exception as e:
        logger.error(f"Unexpected error fetching pending drivers: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching pending drivers.")


async def update_driver_verification_status(
    session: AsyncSession,
    driver_to_verify: User,
    new_status: UserStatus,
    admin_notes: Optional[str] = None
) -> User:
    """
    Prepare update for a driver's verification status. Caller handles transaction.
    """
    driver_to_verify.status = new_status
    if admin_notes is not None:
        driver_to_verify.admin_verification_notes = admin_notes
            
    session.add(driver_to_verify) # Mark as dirty/to be persisted
    
    try:
        await session.flush() # Send changes to DB, check constraints, but don't commit transaction
        await session.refresh(driver_to_verify) # Get updated state (e.g., updated_at)
    except SQLAlchemyError as e:
        logger.error(f"Database error during driver status update flush/refresh for driver {driver_to_verify.id}: {e}", exc_info=True)
        # Let router's transaction block handle rollback if it was an IntegrityError, etc.
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error finalizing driver status update.")
    except Exception as e: # Catch any other unexpected error during flush/refresh
        logger.error(f"Unexpected error during driver status update flush/refresh for driver {driver_to_verify.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error finalizing driver status update.")

    logger.info(f"Driver {driver_to_verify.id} status prepared to be updated to {new_status}")
    return driver_to_verify


async def list_cars_pending_verification(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 20
) -> List[Car]:
    """
    Get a list of cars pending verification, with driver eagerly loaded.
    """
    try:
        query = (
            select(Car)
            .options(selectinload(Car.driver))
            .where(Car.verification_status == CarVerificationStatus.PENDING_VERIFICATION)
            .offset(skip)
            .limit(limit)
            .order_by(Car.created_at.asc()) # Added an order for consistency
        )
        result = await session.execute(query)
        cars = result.scalars().all()
        logger.info(f"Found {len(cars)} cars pending verification")
        return cars
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching pending cars: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching pending cars.")
    except Exception as e:
        logger.error(f"Unexpected error fetching pending cars: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while fetching pending cars.")


async def update_car_verification_status(
    session: AsyncSession,
    car_to_verify: Car,
    new_status: CarVerificationStatus,
    admin_notes: Optional[str] = None
) -> Car:
    """
    Prepare update for a car's verification status. Caller handles transaction.
    """
    car_to_verify.verification_status = new_status
    if admin_notes is not None:
        car_to_verify.admin_verification_notes = admin_notes
            
    session.add(car_to_verify)
    
    try:
        await session.flush()
        await session.refresh(car_to_verify)
    except SQLAlchemyError as e:
        logger.error(f"Database error during car status update flush/refresh for car {car_to_verify.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error finalizing car status update.")
    except Exception as e:
        logger.error(f"Unexpected error during car status update flush/refresh for car {car_to_verify.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error finalizing car status update.")
        
    logger.info(f"Car {car_to_verify.id} verification status prepared to be updated to {new_status}")
    return car_to_verify


async def list_all_trips(
    session: AsyncSession, 
    skip: int = 0, 
    limit: int = 20
) -> List[Trip]:
    """
    Retrieve all trips with pagination, ordered by departure time, with eager loading.
    """
    try:
        stmt = (
            select(Trip)
            .options(
                selectinload(Trip.driver),
                selectinload(Trip.car)
            )
            .order_by(Trip.departure_datetime.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        trips = result.scalars().all()
        logger.info(f"Retrieved {len(trips)} trips for admin listing. Skip: {skip}, Limit: {limit}")
        return trips
    except SQLAlchemyError as e:
        logger.error(f"Database error while listing all trips: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while retrieving trips.")
    except Exception as e:
        logger.error(f"Unexpected error while listing all trips: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while retrieving trips.")