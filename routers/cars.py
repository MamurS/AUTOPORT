import logging
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_active_user
from crud import car_crud
from database import get_db
from models import User, UserRole
from schemas import CarCreate, CarResponse, CarUpdate

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cars", tags=["cars"])

@router.post(
    "/",
    response_model=CarResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new car",
    description="Add a new car to the authenticated driver's profile."
)
async def add_car(
    car_in: CarCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CarResponse:
    """
    Add a new car to the authenticated driver's profile.
    
    Args:
        car_in: The car data from the request
        current_user: The authenticated user (injected by FastAPI)
        db: The database session (injected by FastAPI)
        
    Returns:
        The created car
        
    Raises:
        HTTPException: If the user is not a driver or if a car with the same license plate exists
    """
    # Check if user is a driver
    if current_user.role != UserRole.DRIVER:
        logger.warning(f"Non-driver user {current_user.id} attempted to add a car")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only drivers can add cars."
        )
    
    try:
        async with db.begin_nested():
            # Create the car
            car = await car_crud.create_driver_car(
                session=db,
                car_in=car_in,
                driver_id=current_user.id
            )
            
            return car
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in add_car: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.get(
    "/",
    response_model=List[CarResponse],
    summary="Get driver's cars",
    description="Get a list of all cars registered by the authenticated driver."
)
async def get_my_cars(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[CarResponse]:
    """
    Get a list of all cars registered by the authenticated driver.
    
    Args:
        current_user: The authenticated user (injected by FastAPI)
        db: The database session (injected by FastAPI)
        
    Returns:
        A list of cars owned by the driver
        
    Raises:
        HTTPException: If the user is not a driver
    """
    # Check if user is a driver
    if current_user.role != UserRole.DRIVER:
        logger.warning(f"Non-driver user {current_user.id} attempted to view cars")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only drivers can view their cars."
        )
    
    try:
        # Get the cars
        cars = await car_crud.get_driver_cars(
            session=db,
            driver_id=current_user.id
        )
        
        return cars
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_my_cars: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.get(
    "/{car_id}",
    response_model=CarResponse,
    summary="Get specific car",
    description="Get details of a specific car owned by the authenticated driver."
)
async def get_my_car(
    car_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CarResponse:
    """
    Get details of a specific car owned by the authenticated driver.
    
    Args:
        car_id: The UUID of the car to fetch
        current_user: The authenticated user (injected by FastAPI)
        db: The database session (injected by FastAPI)
        
    Returns:
        The car details
        
    Raises:
        HTTPException: If the user is not a driver or if the car is not found/not owned by the driver
    """
    # Check if user is a driver
    if current_user.role != UserRole.DRIVER:
        logger.warning(f"Non-driver user {current_user.id} attempted to view car {car_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only drivers can view car details."
        )
    
    try:
        # Get the car
        car = await car_crud.get_driver_car_by_id(
            session=db,
            car_id=car_id,
            driver_id=current_user.id
        )
        
        if not car:
            logger.warning(f"Car {car_id} not found or not owned by driver {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Car not found or not owned by this driver."
            )
        
        return car
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_my_car: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.patch(
    "/{car_id}",
    response_model=CarResponse,
    summary="Update car",
    description="Update details of a specific car owned by the authenticated driver."
)
async def update_my_car(
    car_id: UUID,
    car_in: CarUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CarResponse:
    """
    Update details of a specific car owned by the authenticated driver.
    
    Args:
        car_id: The UUID of the car to update
        car_in: The update data from the request
        current_user: The authenticated user (injected by FastAPI)
        db: The database session (injected by FastAPI)
        
    Returns:
        The updated car details
        
    Raises:
        HTTPException: If the user is not a driver, if the car is not found/not owned by the driver,
                      or if another car with the new license plate exists
    """
    # Check if user is a driver
    if current_user.role != UserRole.DRIVER:
        logger.warning(f"Non-driver user {current_user.id} attempted to update car {car_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only drivers can update car details."
        )
    
    try:
        async with db.begin_nested():
            # Get the car to update
            car = await car_crud.get_driver_car_by_id(
                session=db,
                car_id=car_id,
                driver_id=current_user.id
            )
            
            if not car:
                logger.warning(f"Car {car_id} not found or not owned by driver {current_user.id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Car not found or not owned by this driver."
                )
            
            # Update the car
            updated_car = await car_crud.update_driver_car(
                session=db,
                car_to_update=car,
                car_in=car_in
            )
            
            return updated_car
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_my_car: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.delete(
    "/{car_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete car",
    description="Delete a specific car owned by the authenticated driver."
)
async def delete_my_car(
    car_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    """
    Delete a specific car owned by the authenticated driver.
    
    Args:
        car_id: The UUID of the car to delete
        current_user: The authenticated user (injected by FastAPI)
        db: The database session (injected by FastAPI)
        
    Raises:
        HTTPException: If the user is not a driver or if the car is not found/not owned by the driver
    """
    # Check if user is a driver
    if current_user.role != UserRole.DRIVER:
        logger.warning(f"Non-driver user {current_user.id} attempted to delete car {car_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only drivers can delete cars."
        )
    
    try:
        async with db.begin_nested():
            # Get the car to delete
            car = await car_crud.get_driver_car_by_id(
                session=db,
                car_id=car_id,
                driver_id=current_user.id
            )
            
            if not car:
                logger.warning(f"Car {car_id} not found or not owned by driver {current_user.id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Car not found or not owned by this driver."
                )
            
            # Delete the car
            await car_crud.delete_driver_car(
                session=db,
                car_to_delete=car
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in delete_my_car: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.post(
    "/{car_id}/set-default",
    response_model=CarResponse,
    summary="Set default car",
    description="Set a specific car as the default car for the authenticated driver."
)
async def set_my_default_car(
    car_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> CarResponse:
    """
    Set a specific car as the default car for the authenticated driver.
    
    Args:
        car_id: The UUID of the car to set as default
        current_user: The authenticated user (injected by FastAPI)
        db: The database session (injected by FastAPI)
        
    Returns:
        The updated car details
        
    Raises:
        HTTPException: If the user is not a driver or if the car is not found/not owned by the driver
    """
    # Check if user is a driver
    if current_user.role != UserRole.DRIVER:
        logger.warning(f"Non-driver user {current_user.id} attempted to set default car {car_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only drivers can set default cars."
        )
    
    try:
        async with db.begin_nested():
            # Get the car to set as default
            car = await car_crud.get_driver_car_by_id(
                session=db,
                car_id=car_id,
                driver_id=current_user.id
            )
            
            if not car:
                logger.warning(f"Car {car_id} not found or not owned by driver {current_user.id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Car not found or not owned by this driver."
                )
            
            # Set as default
            updated_car = await car_crud.set_driver_default_car(
                session=db,
                car_to_set_default=car,
                driver_id=current_user.id
            )
            
            return updated_car
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in set_my_default_car: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        ) 