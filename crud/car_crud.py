# File: crud/car_crud.py (Refactored for router-level transactions)

import logging
from typing import Optional, List
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, desc, and_, update # update is used in set_driver_default_car
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError # For specific error catching

from models import Car # CarCreate and CarUpdate are schemas
from schemas import CarCreate, CarUpdate

logger = logging.getLogger(__name__)

async def get_car_by_license_plate(
    session: AsyncSession,
    license_plate: str
) -> Optional[Car]:
    """Get a car by its license plate."""
    try:
        query = select(Car).where(Car.license_plate == license_plate)
        result = await session.execute(query)
        return result.scalar_one_or_none()
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching car by license plate {license_plate}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching car details.")
    except Exception as e:
        logger.error(f"Unexpected error fetching car by license plate {license_plate}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching car details.")


async def create_driver_car(
    session: AsyncSession,
    car_in: CarCreate,
    driver_id: UUID
) -> Car:
    """Prepare a new car for a driver. Caller handles transaction."""
    existing_car = await get_car_by_license_plate(session, car_in.license_plate)
    if existing_car:
        logger.warning(f"Attempt to create car with duplicate license plate: {car_in.license_plate}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Car with this license plate already exists."
        )
    
    car = Car(
        driver_id=driver_id,
        make=car_in.make,
        model=car_in.model,
        license_plate=car_in.license_plate,
        color=car_in.color,
        seats_count=car_in.seats_count if car_in.seats_count is not None else 4, # Use Pydantic default if available
        is_default=car_in.is_default if car_in.is_default is not None else False # Use Pydantic default
    )
    
    session.add(car)
    try:
        await session.flush()
        await session.refresh(car)
    except SQLAlchemyError as e:
        logger.error(f"Database error during car creation flush/refresh for driver {driver_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error finalizing car creation.")
    except Exception as e:
        logger.error(f"Unexpected error during car creation flush/refresh for driver {driver_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error finalizing car creation.")

    logger.info(f"Car {car.license_plate} prepared for driver {driver_id}")
    return car


async def get_driver_cars(
    session: AsyncSession,
    driver_id: UUID,
    skip: int = 0, # Added skip/limit as they were missing in your pasted version
    limit: int = 20
) -> List[Car]:
    """Get all cars for a specific driver."""
    # ... (This is a read operation, no transaction changes needed here.
    #      The version in your response #124 was correct for this.)
    try:
        query = (
            select(Car)
            .where(Car.driver_id == driver_id)
            .order_by(desc(Car.is_default), desc(Car.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(query)
        cars = result.scalars().all()
        logger.info(f"Retrieved {len(cars)} cars for driver {driver_id}")
        return cars
    except SQLAlchemyError as e:
        logger.error(f"Database error retrieving cars for driver {driver_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while retrieving the cars.")
    except Exception as e:
        logger.error(f"Unexpected error retrieving cars for driver {driver_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while retrieving the cars.")


async def get_driver_car_by_id(
    session: AsyncSession,
    car_id: UUID,
    driver_id: UUID
) -> Optional[Car]:
    """Get a specific car owned by a driver."""
    # ... (This is a read operation, no transaction changes needed here.
    #      The version in your response #124 was correct for this.)
    try:
        query = (
            select(Car)
            .where(
                and_(
                    Car.id == car_id,
                    Car.driver_id == driver_id
                )
            )
        )
        result = await session.execute(query)
        car = result.scalar_one_or_none()
        if car:
            logger.info(f"Retrieved car {car_id} for driver {driver_id}")
        else:
            logger.info(f"Car {car_id} not found or not owned by driver {driver_id}")
        return car
    except SQLAlchemyError as e:
        logger.error(f"Database error retrieving car {car_id} for driver {driver_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while retrieving the car.")
    except Exception as e:
        logger.error(f"Unexpected error retrieving car {car_id} for driver {driver_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while retrieving the car.")


async def update_driver_car(
    session: AsyncSession,
    car_to_update: Car,
    car_in: CarUpdate
) -> Car:
    """Update a car's details. Caller handles transaction."""
    if car_in.license_plate is not None and car_in.license_plate != car_to_update.license_plate:
        existing_car = await get_car_by_license_plate(session, car_in.license_plate)
        if existing_car and existing_car.id != car_to_update.id:
            logger.warning(f"Attempt to update car {car_to_update.id} with duplicate license plate: {car_in.license_plate}")
            raise HTTPException(status_code=400, detail="Another car with this license plate already exists.")
        
    update_data = car_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(car_to_update, field, value)
    
    session.add(car_to_update)
    try:
        await session.flush()
        await session.refresh(car_to_update)
    except SQLAlchemyError as e:
        logger.error(f"Database error during car update flush/refresh for car {car_to_update.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error finalizing car update.")
    except Exception as e:
        logger.error(f"Unexpected error during car update flush/refresh for car {car_to_update.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error finalizing car update.")
        
    logger.info(f"Car {car_to_update.id} details prepared for update by driver {car_to_update.driver_id}")
    return car_to_update


async def delete_driver_car(
    session: AsyncSession,
    car_to_delete: Car
) -> None:
    """Delete a car. Caller handles transaction."""
    await session.delete(car_to_delete)
    try:
        await session.flush() # Ensure delete is part of the UOW to be committed
    except SQLAlchemyError as e:
        logger.error(f"Database error during car deletion flush for car {car_to_delete.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error finalizing car deletion.")
    except Exception as e:
        logger.error(f"Unexpected error during car deletion flush for car {car_to_delete.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error finalizing car deletion.")
    logger.info(f"Car {car_to_delete.id} prepared for deletion by driver {car_to_delete.driver_id}")
    # No return value for delete


async def set_driver_default_car(
    session: AsyncSession,
    car_to_set_default: Car,
    driver_id: UUID
) -> Car:
    """Set a car as the default for a driver. Caller handles transaction."""
    # Unset other default car(s) for this driver
    await session.execute(
        update(Car)
        .where(
            and_(
                Car.driver_id == driver_id,
                Car.id != car_to_set_default.id,
                Car.is_default == True
            )
        )
        .values(is_default=False)
    )
    
    car_to_set_default.is_default = True
    session.add(car_to_set_default)
    
    try:
        await session.flush()
        await session.refresh(car_to_set_default)
        # Also refresh other cars if their 'is_default' status might be part of the response context,
        # though unlikely needed for returning just the car_to_set_default.
    except SQLAlchemyError as e:
        logger.error(f"Database error during set default car flush/refresh for car {car_to_set_default.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error finalizing default car setting.")
    except Exception as e:
        logger.error(f"Unexpected error during set default car flush/refresh for car {car_to_set_default.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error finalizing default car setting.")

    logger.info(f"Car {car_to_set_default.id} prepared to be set as default for driver {driver_id}")
    return car_to_set_default