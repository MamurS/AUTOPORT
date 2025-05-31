import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_active_user
from crud.auth_crud import request_driver_role
from database import get_db
from models import User
from schemas import UserResponse

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> User:
    """
    Get the profile of the currently authenticated user.
    
    This endpoint requires a valid JWT token in the Authorization header.
    """
    return current_user

@router.post("/me/apply-driver", response_model=UserResponse)
async def apply_to_become_driver(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    """
    Apply to become a driver.
    
    This endpoint allows an authenticated user to apply for the driver role.
    Upon successful application, the user's role will be set to DRIVER and
    their status will be set to PENDING_PROFILE_COMPLETION, requiring admin verification.
    
    This endpoint requires a valid JWT token in the Authorization header.
    """
    try:
        updated_user = await request_driver_role(db, current_user)
        return updated_user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in apply_to_become_driver: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your driver application."
        ) 