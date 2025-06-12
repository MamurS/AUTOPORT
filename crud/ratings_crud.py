# File: crud/ratings_crud.py

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, and_, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError

from models import (
    Rating, User, Trip, Booking, RatingType, BookingStatus, 
    TripStatus, UserRole
)
from schemas import RatingCreate, UserRatingsSummary

logger = logging.getLogger(__name__)

async def create_rating(
    session: AsyncSession,
    rater_id: UUID,
    rating_data: RatingCreate
) -> Rating:
    """Create a new rating after verifying eligibility."""
    try:
        # Verify the users have traveled together
        trip_connection = await verify_rating_eligibility(
            session=session,
            rater_id=rater_id,
            rated_user_id=rating_data.rated_user_id,
            booking_id=rating_data.booking_id
        )
        
        if not trip_connection:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only rate users you have traveled with."
            )
        
        # Check if rating already exists
        existing_rating = await get_existing_rating(
            session=session,
            rater_id=rater_id,
            rated_user_id=rating_data.rated_user_id,
            trip_id=trip_connection["trip_id"]
        )
        
        if existing_rating:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have already rated this user for this trip."
            )
        
        # Determine rating type
        rating_type = await determine_rating_type(
            session=session,
            rater_id=rater_id,
            rated_user_id=rating_data.rated_user_id,
            trip_id=trip_connection["trip_id"]
        )
        
        # Create the rating
        rating = Rating(
            trip_id=trip_connection["trip_id"],
            booking_id=rating_data.booking_id,
            rater_id=rater_id,
            rated_user_id=rating_data.rated_user_id,
            rating_type=rating_type,
            rating=rating_data.rating,
            review=rating_data.review,
            punctuality=rating_data.punctuality,
            cleanliness=rating_data.cleanliness,
            communication=rating_data.communication,
            driving_quality=rating_data.driving_quality
        )
        
        session.add(rating)
        await session.flush()
        await session.refresh(rating)
        
        # Eager load related data
        result = await session.execute(
            select(Rating)
            .options(
                selectinload(Rating.rater),
                selectinload(Rating.rated_user),
                selectinload(Rating.trip),
                selectinload(Rating.booking)
            )
            .where(Rating.id == rating.id)
        )
        rating_with_relations = result.scalar_one()
        
        logger.info(f"Rating created: {rating.rating} stars from {rater_id} to {rating_data.rated_user_id}")
        return rating_with_relations
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating rating: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating rating."
        )

async def verify_rating_eligibility(
    session: AsyncSession,
    rater_id: UUID,
    rated_user_id: UUID,
    booking_id: Optional[UUID] = None
) -> Optional[Dict[str, Any]]:
    """Verify if rater can rate the rated user."""
    try:
        # If booking_id is provided, verify through booking
        if booking_id:
            result = await session.execute(
                select(Booking, Trip)
                .join(Trip)
                .where(
                    and_(
                        Booking.id == booking_id,
                        or_(
                            and_(Booking.passenger_id == rater_id, Trip.driver_id == rated_user_id),
                            and_(Trip.driver_id == rater_id, Booking.passenger_id == rated_user_id)
                        ),
                        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.CANCELLED_BY_DRIVER]),
                        Trip.status.in_([TripStatus.COMPLETED, TripStatus.CANCELLED_BY_DRIVER])
                    )
                )
            )
            booking_trip = result.first()
            if booking_trip:
                return {"trip_id": booking_trip.Trip.id, "booking_id": booking_id}
        
        # General verification - check if they have traveled together
        result = await session.execute(
            select(Trip.id)
            .join(Booking)
            .where(
                or_(
                    and_(Trip.driver_id == rater_id, Booking.passenger_id == rated_user_id),
                    and_(Trip.driver_id == rated_user_id, Booking.passenger_id == rater_id)
                ),
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.CANCELLED_BY_DRIVER]),
                Trip.status.in_([TripStatus.COMPLETED, TripStatus.CANCELLED_BY_DRIVER])
            )
            .limit(1)
        )
        trip_id = result.scalar_one_or_none()
        
        if trip_id:
            return {"trip_id": trip_id, "booking_id": None}
        
        return None
        
    except Exception as e:
        logger.error(f"Error verifying rating eligibility: {e}", exc_info=True)
        return None

async def get_existing_rating(
    session: AsyncSession,
    rater_id: UUID,
    rated_user_id: UUID,
    trip_id: UUID
) -> Optional[Rating]:
    """Check if rating already exists for this trip."""
    try:
        result = await session.execute(
            select(Rating)
            .where(
                and_(
                    Rating.rater_id == rater_id,
                    Rating.rated_user_id == rated_user_id,
                    Rating.trip_id == trip_id
                )
            )
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking existing rating: {e}", exc_info=True)
        return None

async def determine_rating_type(
    session: AsyncSession,
    rater_id: UUID,
    rated_user_id: UUID,
    trip_id: UUID
) -> RatingType:
    """Determine if this is driver-to-passenger or passenger-to-driver rating."""
    try:
        result = await session.execute(
            select(Trip.driver_id)
            .where(Trip.id == trip_id)
        )
        driver_id = result.scalar_one()
        
        if rater_id == driver_id:
            return RatingType.DRIVER_TO_PASSENGER
        else:
            return RatingType.PASSENGER_TO_DRIVER
            
    except Exception as e:
        logger.error(f"Error determining rating type: {e}", exc_info=True)
        return RatingType.PASSENGER_TO_DRIVER  # Default

async def get_given_ratings(
    session: AsyncSession,
    rater_id: UUID,
    skip: int = 0,
    limit: int = 20
) -> List[Rating]:
    """Get ratings given by a user."""
    try:
        result = await session.execute(
            select(Rating)
            .options(
                selectinload(Rating.rated_user),
                selectinload(Rating.trip),
                selectinload(Rating.booking)
            )
            .where(Rating.rater_id == rater_id)
            .order_by(desc(Rating.created_at))
            .offset(skip)
            .limit(limit)
        )
        ratings = result.scalars().all()
        logger.info(f"Retrieved {len(ratings)} given ratings for user {rater_id}")
        return ratings
    except Exception as e:
        logger.error(f"Error getting given ratings: {e}", exc_info=True)
        return []

async def get_received_ratings(
    session: AsyncSession,
    rated_user_id: UUID,
    skip: int = 0,
    limit: int = 20
) -> List[Rating]:
    """Get ratings received by a user."""
    try:
        result = await session.execute(
            select(Rating)
            .options(
                selectinload(Rating.rater),
                selectinload(Rating.trip),
                selectinload(Rating.booking)
            )
            .where(Rating.rated_user_id == rated_user_id)
            .order_by(desc(Rating.created_at))
            .offset(skip)
            .limit(limit)
        )
        ratings = result.scalars().all()
        logger.info(f"Retrieved {len(ratings)} received ratings for user {rated_user_id}")
        return ratings
    except Exception as e:
        logger.error(f"Error getting received ratings: {e}", exc_info=True)
        return []

async def get_user_ratings_summary(
    session: AsyncSession,
    user_id: UUID
) -> UserRatingsSummary:
    """Get comprehensive rating summary for a user."""
    try:
        # Get basic stats
        result = await session.execute(
            select(
                func.avg(Rating.rating).label('avg_rating'),
                func.count(Rating.id).label('total_ratings'),
                Rating.rating
            )
            .where(Rating.rated_user_id == user_id)
            .group_by(Rating.rating)
        )
        
        rating_data = result.all()
        
        if not rating_data:
            return UserRatingsSummary(
                average_rating=0.0,
                total_ratings=0,
                rating_breakdown={1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                recent_reviews=[]
            )
        
        # Calculate summary
        total_ratings = sum(row.total_ratings for row in rating_data)
        avg_rating = sum(row.avg_rating * row.total_ratings for row in rating_data) / total_ratings if total_ratings > 0 else 0
        
        # Create breakdown
        rating_breakdown = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for row in rating_data:
            rating_breakdown[row.rating] = row.total_ratings
        
        # Get recent reviews
        recent_result = await session.execute(
            select(Rating)
            .options(
                selectinload(Rating.rater),
                selectinload(Rating.trip)
            )
            .where(
                and_(
                    Rating.rated_user_id == user_id,
                    Rating.review.isnot(None),
                    Rating.review != ""
                )
            )
            .order_by(desc(Rating.created_at))
            .limit(5)
        )
        recent_reviews = recent_result.scalars().all()
        
        return UserRatingsSummary(
            average_rating=round(avg_rating, 2),
            total_ratings=total_ratings,
            rating_breakdown=rating_breakdown,
            recent_reviews=recent_reviews
        )
        
    except Exception as e:
        logger.error(f"Error getting user ratings summary: {e}", exc_info=True)
        return UserRatingsSummary(
            average_rating=0.0,
            total_ratings=0,
            rating_breakdown={1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            recent_reviews=[]
        )

async def get_pending_ratings_for_trip(
    session: AsyncSession,
    trip_id: UUID,
    user_id: UUID
) -> List[Dict[str, Any]]:
    """Get users that can still be rated for a trip."""
    try:
        # Get trip details
        trip_result = await session.execute(
            select(Trip)
            .where(Trip.id == trip_id)
        )
        trip = trip_result.scalar_one_or_none()
        if not trip:
            return []
        
        # Check if trip is completed
        if trip.status not in [TripStatus.COMPLETED, TripStatus.CANCELLED_BY_DRIVER]:
            return []
        
        # Get all participants
        participants = []
        
        # Add driver if user is not the driver
        if trip.driver_id != user_id:
            participants.append({
                "user_id": trip.driver_id,
                "role": "driver"
            })
        
        # Add passengers if user is driver or another passenger
        bookings_result = await session.execute(
            select(Booking)
            .options(selectinload(Booking.passenger))
            .where(
                and_(
                    Booking.trip_id == trip_id,
                    Booking.passenger_id != user_id,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.CANCELLED_BY_DRIVER])
                )
            )
        )
        bookings = bookings_result.scalars().all()
        
        for booking in bookings:
            participants.append({
                "user_id": booking.passenger_id,
                "role": "passenger",
                "booking_id": booking.id,
                "user": booking.passenger
            })
        
        # Filter out already rated users
        pending_ratings = []
        for participant in participants:
            existing_rating = await get_existing_rating(
                session=session,
                rater_id=user_id,
                rated_user_id=participant["user_id"],
                trip_id=trip_id
            )
            if not existing_rating:
                pending_ratings.append(participant)
        
        logger.info(f"Found {len(pending_ratings)} pending ratings for trip {trip_id}")
        return pending_ratings
        
    except Exception as e:
        logger.error(f"Error getting pending ratings for trip: {e}", exc_info=True)
        return []

async def can_rate_booking(
    session: AsyncSession,
    booking_id: UUID,
    user_id: UUID
) -> Dict[str, Any]:
    """Check if user can rate for a specific booking."""
    try:
        result = await session.execute(
            select(Booking, Trip)
            .join(Trip)
            .where(Booking.id == booking_id)
        )
        booking_trip = result.first()
        
        if not booking_trip:
            return {"can_rate": False, "reason": "Booking not found"}
        
        booking, trip = booking_trip
        
        # Check if user is involved in this booking
        if user_id not in [booking.passenger_id, trip.driver_id]:
            return {"can_rate": False, "reason": "Not involved in this booking"}
        
        # Check if trip is completed
        if trip.status not in [TripStatus.COMPLETED, TripStatus.CANCELLED_BY_DRIVER]:
            return {"can_rate": False, "reason": "Trip not completed"}
        
        # Check if booking is valid
        if booking.status not in [BookingStatus.CONFIRMED, BookingStatus.CANCELLED_BY_DRIVER]:
            return {"can_rate": False, "reason": "Invalid booking status"}
        
        # Determine who can be rated
        rateable_users = []
        if user_id == trip.driver_id:
            # Driver can rate the passenger
            rateable_users.append({
                "user_id": booking.passenger_id,
                "role": "passenger"
            })
        else:
            # Passenger can rate the driver
            rateable_users.append({
                "user_id": trip.driver_id,
                "role": "driver"
            })
        
        # Check existing ratings
        for rateable_user in rateable_users:
            existing = await get_existing_rating(
                session=session,
                rater_id=user_id,
                rated_user_id=rateable_user["user_id"],
                trip_id=trip.id
            )
            rateable_user["already_rated"] = existing is not None
        
        return {
            "can_rate": True,
            "trip_id": trip.id,
            "rateable_users": rateable_users
        }
        
    except Exception as e:
        logger.error(f"Error checking rating eligibility for booking: {e}", exc_info=True)
        return {"can_rate": False, "reason": "Error checking eligibility"}

async def get_public_ratings(
    session: AsyncSession,
    user_id: UUID,
    skip: int = 0,
    limit: int = 10
) -> List[Rating]:
    """Get public ratings for a user (only those with reviews)."""
    try:
        result = await session.execute(
            select(Rating)
            .options(
                selectinload(Rating.rater),
                selectinload(Rating.trip)
            )
            .where(
                and_(
                    Rating.rated_user_id == user_id,
                    Rating.review.isnot(None),
                    Rating.review != ""
                )
            )
            .order_by(desc(Rating.created_at))
            .offset(skip)
            .limit(limit)
        )
        ratings = result.scalars().all()
        logger.info(f"Retrieved {len(ratings)} public ratings for user {user_id}")
        return ratings
    except Exception as e:
        logger.error(f"Error getting public ratings: {e}", exc_info=True)
        return []

async def delete_rating(
    session: AsyncSession,
    rating_id: UUID,
    rater_id: UUID
) -> bool:
    """Delete a rating (within 24 hours)."""
    try:
        result = await session.execute(
            select(Rating)
            .where(
                and_(
                    Rating.id == rating_id,
                    Rating.rater_id == rater_id,
                    Rating.created_at >= datetime.utcnow() - timedelta(hours=24)
                )
            )
        )
        rating = result.scalar_one_or_none()
        
        if not rating:
            return False
        
        await session.delete(rating)
        await session.flush()
        
        logger.info(f"Rating {rating_id} deleted by user {rater_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting rating: {e}", exc_info=True)
        return False

async def update_rating(
    session: AsyncSession,
    rating_id: UUID,
    rater_id: UUID,
    rating_data: RatingCreate
) -> Optional[Rating]:
    """Update a rating (within 24 hours)."""
    try:
        result = await session.execute(
            select(Rating)
            .where(
                and_(
                    Rating.id == rating_id,
                    Rating.rater_id == rater_id,
                    Rating.created_at >= datetime.utcnow() - timedelta(hours=24)
                )
            )
        )
        rating = result.scalar_one_or_none()
        
        if not rating:
            return None
        
        # Update fields
        rating.rating = rating_data.rating
        rating.review = rating_data.review
        rating.punctuality = rating_data.punctuality
        rating.cleanliness = rating_data.cleanliness
        rating.communication = rating_data.communication
        rating.driving_quality = rating_data.driving_quality
        
        session.add(rating)
        await session.flush()
        await session.refresh(rating)
        
        # Return with relations
        result = await session.execute(
            select(Rating)
            .options(
                selectinload(Rating.rater),
                selectinload(Rating.rated_user),
                selectinload(Rating.trip)
            )
            .where(Rating.id == rating.id)
        )
        updated_rating = result.scalar_one()
        
        logger.info(f"Rating {rating_id} updated by user {rater_id}")
        return updated_rating
        
    except Exception as e:
        logger.error(f"Error updating rating: {e}", exc_info=True)
        return None

async def get_top_rated_drivers(
    session: AsyncSession,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Get top-rated drivers for marketplace display."""
    try:
        result = await session.execute(
            select(
                User,
                func.avg(Rating.rating).label('avg_rating'),
                func.count(Rating.id).label('rating_count')
            )
            .join(Rating, Rating.rated_user_id == User.id)
            .where(
                and_(
                    User.role == UserRole.DRIVER,
                    Rating.rating_type == RatingType.PASSENGER_TO_DRIVER
                )
            )
            .group_by(User.id)
            .having(func.count(Rating.id) >= 5)  # At least 5 ratings
            .order_by(desc('avg_rating'), desc('rating_count'))
            .limit(limit)
        )
        
        top_drivers = []
        for user, avg_rating, rating_count in result:
            top_drivers.append({
                "user": user,
                "average_rating": round(avg_rating, 2),
                "total_ratings": rating_count
            })
        
        logger.info(f"Retrieved {len(top_drivers)} top-rated drivers")
        return top_drivers
        
    except Exception as e:
        logger.error(f"Error getting top-rated drivers: {e}", exc_info=True)
        return []

async def get_user_ratings_for_trip(
    session: AsyncSession,
    trip_id: UUID,
    user_id: UUID,
    given_by_user: bool = True
) -> List[Rating]:
    """Get ratings for a specific trip by or about a user."""
    try:
        if given_by_user:
            # Ratings given by the user for this trip
            condition = Rating.rater_id == user_id
        else:
            # Ratings received by the user for this trip
            condition = Rating.rated_user_id == user_id
        
        result = await session.execute(
            select(Rating)
            .options(
                selectinload(Rating.rater),
                selectinload(Rating.rated_user),
                selectinload(Rating.trip)
            )
            .where(
                and_(
                    Rating.trip_id == trip_id,
                    condition
                )
            )
            .order_by(Rating.created_at)
        )
        ratings = result.scalars().all()
        logger.info(f"Retrieved {len(ratings)} ratings for trip {trip_id}")
        return ratings
    except Exception as e:
        logger.error(f"Error getting user ratings for trip: {e}", exc_info=True)
        return []

async def get_detailed_user_stats(
    session: AsyncSession,
    user_id: UUID
) -> Dict[str, Any]:
    """Get detailed rating statistics for a user."""
    try:
        # Stats as rated user
        received_result = await session.execute(
            select(
                func.avg(Rating.rating).label('avg_rating'),
                func.count(Rating.id).label('total_count'),
                func.avg(Rating.punctuality).label('avg_punctuality'),
                func.avg(Rating.cleanliness).label('avg_cleanliness'),
                func.avg(Rating.communication).label('avg_communication'),
                func.avg(Rating.driving_quality).label('avg_driving')
            )
            .where(Rating.rated_user_id == user_id)
        )
        received_stats = received_result.first()
        
        # Stats as rater
        given_result = await session.execute(
            select(func.count(Rating.id))
            .where(Rating.rater_id == user_id)
        )
        given_count = given_result.scalar() or 0
        
        # Recent activity
        recent_result = await session.execute(
            select(Rating)
            .options(selectinload(Rating.rated_user))
            .where(Rating.rater_id == user_id)
            .order_by(desc(Rating.created_at))
            .limit(5)
        )
        recent_given = recent_result.scalars().all()
        
        stats = {
            "received_ratings": {
                "average_rating": round(received_stats.avg_rating or 0, 2),
                "total_count": received_stats.total_count or 0,
                "average_punctuality": round(received_stats.avg_punctuality or 0, 2),
                "average_cleanliness": round(received_stats.avg_cleanliness or 0, 2),
                "average_communication": round(received_stats.avg_communication or 0, 2),
                "average_driving_quality": round(received_stats.avg_driving or 0, 2)
            },
            "given_ratings_count": given_count,
            "recent_ratings_given": recent_given
        }
        
        logger.info(f"Retrieved detailed stats for user {user_id}")
        return stats
        
    except Exception as e:
        logger.error(f"Error getting detailed user stats: {e}", exc_info=True)
        return {}

async def create_multiple_ratings(
    session: AsyncSession,
    trip_id: UUID,
    rater_id: UUID,
    ratings_data: List[RatingCreate]
) -> List[Rating]:
    """Create multiple ratings for a trip in one transaction."""
    try:
        created_ratings = []
        
        for rating_data in ratings_data:
            # Verify eligibility for each rating
            trip_connection = await verify_rating_eligibility(
                session=session,
                rater_id=rater_id,
                rated_user_id=rating_data.rated_user_id,
                booking_id=rating_data.booking_id
            )
            
            if not trip_connection or trip_connection["trip_id"] != trip_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Cannot rate user {rating_data.rated_user_id} for this trip."
                )
            
            # Check for existing rating
            existing = await get_existing_rating(
                session=session,
                rater_id=rater_id,
                rated_user_id=rating_data.rated_user_id,
                trip_id=trip_id
            )
            
            if existing:
                continue  # Skip already rated users
            
            # Determine rating type
            rating_type = await determine_rating_type(
                session=session,
                rater_id=rater_id,
                rated_user_id=rating_data.rated_user_id,
                trip_id=trip_id
            )
            
            # Create rating
            rating = Rating(
                trip_id=trip_id,
                booking_id=rating_data.booking_id,
                rater_id=rater_id,
                rated_user_id=rating_data.rated_user_id,
                rating_type=rating_type,
                rating=rating_data.rating,
                review=rating_data.review,
                punctuality=rating_data.punctuality,
                cleanliness=rating_data.cleanliness,
                communication=rating_data.communication,
                driving_quality=rating_data.driving_quality
            )
            
            session.add(rating)
            created_ratings.append(rating)
        
        await session.flush()
        
        # Refresh and load relations for all created ratings
        for rating in created_ratings:
            await session.refresh(rating)
        
        # Load relations
        if created_ratings:
            rating_ids = [r.id for r in created_ratings]
            result = await session.execute(
                select(Rating)
                .options(
                    selectinload(Rating.rater),
                    selectinload(Rating.rated_user),
                    selectinload(Rating.trip)
                )
                .where(Rating.id.in_(rating_ids))
            )
            ratings_with_relations = result.scalars().all()
            
            logger.info(f"Created {len(ratings_with_relations)} ratings for trip {trip_id}")
            return ratings_with_relations
        
        return []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating multiple ratings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating multiple ratings."
        )