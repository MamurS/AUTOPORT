import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from auth.dependencies import get_current_active_user
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