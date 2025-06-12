# File: routers/ratings.py

import logging
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_active_user
from crud import ratings_crud
from database import get_db
from models import User, UserRole
from schemas import (
    RatingCreate, RatingResponse, UserRatingsSummary
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ratings", tags=["ratings"])

@router.post("/", response_model=RatingResponse, status_code=status.HTTP_201_CREATED)
async def create_rating(
    rating_data: RatingCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> RatingResponse:
    """
    Create a rating for another user after a trip.
    Users can only rate each other if they have traveled together.
    """
    try:
        if rating_data.rated_user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot rate yourself."
            )
        
        rating = await ratings_crud.create_rating(
            session=db,
            rater_id=current_user.id,
            rating_data=rating_data
        )
        
        logger.info(f"Rating created by user {current_user.id} for user {rating_data.rated_user_id}")
        return rating
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating rating: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the rating."
        )

@router.get("/my-ratings", response_model=List[RatingResponse])
async def get_my_given_ratings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100)
) -> List[RatingResponse]:
    """
    Get ratings I have given to others.
    """
    try:
        ratings = await ratings_crud.get_given_ratings(
            session=db,
            rater_id=current_user.id,
            skip=skip,
            limit=limit
        )
        logger.info(f"Retrieved {len(ratings)} given ratings for user {current_user.id}")
        return ratings
    except Exception as e:
        logger.error(f"Error getting given ratings for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving your ratings."
        )

@router.get("/received", response_model=List[RatingResponse])
async def get_my_received_ratings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100)
) -> List[RatingResponse]:
    """
    Get ratings I have received from others.
    """
    try:
        ratings = await ratings_crud.get_received_ratings(
            session=db,
            rated_user_id=current_user.id,
            skip=skip,
            limit=limit
        )
        logger.info(f"Retrieved {len(ratings)} received ratings for user {current_user.id}")
        return ratings
    except Exception as e:
        logger.error(f"Error getting received ratings for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving ratings about you."
        )

@router.get("/users/{user_id}/summary", response_model=UserRatingsSummary)
async def get_user_ratings_summary(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserRatingsSummary:
    """
    Get ratings summary for a specific user.
    This is useful for viewing user profiles before booking.
    """
    try:
        summary = await ratings_crud.get_user_ratings_summary(
            session=db,
            user_id=user_id
        )
        logger.info(f"Retrieved ratings summary for user {user_id}")
        return summary
    except Exception as e:
        logger.error(f"Error getting ratings summary for user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving the user's ratings summary."
        )

@router.get("/trips/{trip_id}/pending", response_model=List[dict])
async def get_pending_ratings_for_trip(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[dict]:
    """
    Get users that current user can still rate for a specific trip.
    Shows who you can rate after completing a trip.
    """
    try:
        pending_ratings = await ratings_crud.get_pending_ratings_for_trip(
            session=db,
            trip_id=trip_id,
            user_id=current_user.id
        )
        logger.info(f"Retrieved {len(pending_ratings)} pending ratings for trip {trip_id}")
        return pending_ratings
    except Exception as e:
        logger.error(f"Error getting pending ratings for trip {trip_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving pending ratings."
        )

@router.get("/bookings/{booking_id}/can-rate")
async def check_can_rate_booking(
    booking_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Check if current user can rate others for a specific booking.
    Used to show/hide rating buttons in the UI.
    """
    try:
        can_rate_data = await ratings_crud.can_rate_booking(
            session=db,
            booking_id=booking_id,
            user_id=current_user.id
        )
        return can_rate_data
    except Exception as e:
        logger.error(f"Error checking rating eligibility for booking {booking_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while checking rating eligibility."
        )

@router.get("/users/{user_id}/ratings", response_model=List[RatingResponse])
async def get_user_public_ratings(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=50)
) -> List[RatingResponse]:
    """
    Get public ratings for a user (for viewing profiles).
    Only shows recent ratings with reviews to protect privacy.
    """
    try:
        ratings = await ratings_crud.get_public_ratings(
            session=db,
            user_id=user_id,
            skip=skip,
            limit=limit
        )
        logger.info(f"Retrieved {len(ratings)} public ratings for user {user_id}")
        return ratings
    except Exception as e:
        logger.error(f"Error getting public ratings for user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving public ratings."
        )

@router.delete("/{rating_id}")
async def delete_rating(
    rating_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Delete a rating (only the person who gave it can delete it).
    Can only delete within 24 hours of creation.
    """
    try:
        success = await ratings_crud.delete_rating(
            session=db,
            rating_id=rating_id,
            rater_id=current_user.id
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rating not found, cannot be deleted (24h limit), or you don't have permission."
            )
        
        logger.info(f"Rating {rating_id} deleted by user {current_user.id}")
        return {"message": "Rating deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting rating {rating_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the rating."
        )

@router.get("/stats/drivers", response_model=List[dict])
async def get_top_rated_drivers(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=10, ge=1, le=50)
) -> List[dict]:
    """
    Get top-rated drivers (public endpoint for marketplace).
    Useful for featuring best drivers on the platform.
    """
    try:
        top_drivers = await ratings_crud.get_top_rated_drivers(
            session=db,
            limit=limit
        )
        logger.info(f"Retrieved {len(top_drivers)} top-rated drivers")
        return top_drivers
    except Exception as e:
        logger.error(f"Error getting top-rated drivers: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving top-rated drivers."
        )

@router.patch("/{rating_id}", response_model=RatingResponse)
async def update_rating(
    rating_id: UUID,
    rating_data: RatingCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> RatingResponse:
    """
    Update an existing rating (within 24 hours of creation).
    Allows users to modify their ratings if they change their mind.
    """
    try:
        updated_rating = await ratings_crud.update_rating(
            session=db,
            rating_id=rating_id,
            rater_id=current_user.id,
            rating_data=rating_data
        )
        if not updated_rating:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rating not found, cannot be updated (24h limit), or you don't have permission."
            )
        
        logger.info(f"Rating {rating_id} updated by user {current_user.id}")
        return updated_rating
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating rating {rating_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the rating."
        )

@router.get("/trips/{trip_id}/my-ratings", response_model=List[RatingResponse])
async def get_my_ratings_for_trip(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[RatingResponse]:
    """
    Get all ratings I have given for a specific trip.
    Useful for reviewing what ratings were already given.
    """
    try:
        ratings = await ratings_crud.get_user_ratings_for_trip(
            session=db,
            trip_id=trip_id,
            user_id=current_user.id,
            given_by_user=True
        )
        logger.info(f"Retrieved {len(ratings)} ratings given by user {current_user.id} for trip {trip_id}")
        return ratings
    except Exception as e:
        logger.error(f"Error getting user ratings for trip {trip_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving your ratings for this trip."
        )

@router.get("/trips/{trip_id}/received-ratings", response_model=List[RatingResponse])
async def get_my_received_ratings_for_trip(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[RatingResponse]:
    """
    Get all ratings I have received for a specific trip.
    Useful for drivers to see passenger feedback on their trips.
    """
    try:
        ratings = await ratings_crud.get_user_ratings_for_trip(
            session=db,
            trip_id=trip_id,
            user_id=current_user.id,
            given_by_user=False
        )
        logger.info(f"Retrieved {len(ratings)} ratings received by user {current_user.id} for trip {trip_id}")
        return ratings
    except Exception as e:
        logger.error(f"Error getting received ratings for trip {trip_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving ratings about you for this trip."
        )

@router.get("/stats/my-stats")
async def get_my_rating_stats(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get detailed rating statistics for the current user.
    Includes breakdown by role (driver vs passenger) and time periods.
    """
    try:
        stats = await ratings_crud.get_detailed_user_stats(
            session=db,
            user_id=current_user.id
        )
        logger.info(f"Retrieved detailed rating stats for user {current_user.id}")
        return stats
    except Exception as e:
        logger.error(f"Error getting rating stats for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving your rating statistics."
        )

@router.post("/trips/{trip_id}/rate-all", response_model=List[RatingResponse])
async def rate_multiple_users_for_trip(
    trip_id: UUID,
    ratings_data: List[RatingCreate],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[RatingResponse]:
    """
    Rate multiple users for a single trip in one request.
    Useful for passengers rating driver + other passengers, or driver rating all passengers.
    """
    try:
        if len(ratings_data) > 10:  # Reasonable limit
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot rate more than 10 users in a single request."
            )
        
        # Verify all rated users are different and not the current user
        rated_user_ids = {rating.rated_user_id for rating in ratings_data}
        if current_user.id in rated_user_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot rate yourself."
            )
        
        if len(rated_user_ids) != len(ratings_data):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot rate the same user multiple times in one request."
            )
        
        created_ratings = await ratings_crud.create_multiple_ratings(
            session=db,
            trip_id=trip_id,
            rater_id=current_user.id,
            ratings_data=ratings_data
        )
        
        logger.info(f"Created {len(created_ratings)} ratings by user {current_user.id} for trip {trip_id}")
        return created_ratings
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating multiple ratings for trip {trip_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the ratings."
        )