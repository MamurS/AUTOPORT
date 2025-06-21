# File: routers/users.py (Enhanced with comprehensive user management - FIXED)

import logging
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_active_user, get_current_admin_user
from crud import (
    auth_crud, preferences_crud, emergency_crud, ratings_crud, 
    notifications_crud, messaging_crud
)
from database import get_db
from models import User, UserRole
from schemas import (
    UserResponse, UserProfileUpdate, TravelPreferenceResponse,
    EmergencyContactResponse, UserRatingsSummary, UserSettingsResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])

# --- HELPER FUNCTION FOR SERIALIZATION ---

def convert_user_to_response(user: User) -> UserResponse:
    """Convert SQLAlchemy User model to Pydantic UserResponse"""
    return UserResponse(
        id=user.id,
        phone_number=user.phone_number,
        full_name=user.full_name,
        role=user.role,
        status=user.status,
        admin_verification_notes=user.admin_verification_notes,
        profile_image_url=user.profile_image_url,
        date_of_birth=user.date_of_birth,
        gender=user.gender,
        spoken_languages=user.spoken_languages or ["uz"],
        bio=user.bio,
        is_phone_verified=user.is_phone_verified or False,
        is_email_verified=user.is_email_verified or False,
        email=user.email,
        preferred_language=user.preferred_language or "uz",
        currency_preference=user.currency_preference or "UZS",
        created_at=user.created_at,
        updated_at=user.updated_at
    )

# --- BASIC USER PROFILE ---

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> UserResponse:
    """
    Get the complete profile of the currently authenticated user.
    
    This endpoint requires a valid JWT token in the Authorization header.
    """
    return convert_user_to_response(current_user)

@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
    profile_data: UserProfileUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserResponse:
    """
    Update the current user's profile information.
    Enhanced with preference integration and automatic notifications.
    """
    try:
        updated_user = await preferences_crud.update_user_profile_preferences(
            session=db,
            user_id=current_user.id,
            profile_data=profile_data
        )
        
        logger.info(f"Profile updated for user {current_user.id}")
        return convert_user_to_response(updated_user)
    except Exception as e:
        logger.error(f"Error updating user profile: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating your profile."
        )

@router.post("/me/apply-driver", response_model=UserResponse)
async def apply_to_become_driver(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserResponse:
    """
    Apply to become a driver.
    
    This endpoint allows an authenticated user to apply for the driver role.
    Upon successful application, the user's role will be set to DRIVER and
    their status will be set to PENDING_PROFILE_COMPLETION, requiring admin verification.
    
    This endpoint requires a valid JWT token in the Authorization header.
    """
    try:
        updated_user = await auth_crud.request_driver_role(db, current_user)
        return convert_user_to_response(updated_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in apply_to_become_driver: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your driver application."
        )

# --- USER PREFERENCES & SETTINGS ---

@router.get("/me/preferences", response_model=TravelPreferenceResponse)
async def get_my_travel_preferences(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TravelPreferenceResponse:
    """
    Get travel preferences for the current user.
    """
    try:
        preferences = await preferences_crud.get_user_travel_preferences(
            session=db,
            user_id=current_user.id
        )
        if not preferences:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Travel preferences not found. Please create them first."
            )
        
        return preferences
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting travel preferences: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving travel preferences."
        )

@router.get("/me/settings", response_model=UserSettingsResponse)
async def get_my_settings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserSettingsResponse:
    """
    Get application settings for the current user.
    """
    try:
        settings = await preferences_crud.get_user_settings(
            session=db,
            user_id=current_user.id
        )
        return settings
    except Exception as e:
        logger.error(f"Error getting user settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving settings."
        )

# --- EMERGENCY CONTACTS ---

@router.get("/me/emergency-contacts", response_model=List[EmergencyContactResponse])
async def get_my_emergency_contacts(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[EmergencyContactResponse]:
    """
    Get all emergency contacts for the current user.
    Important for safety features and emergency response.
    """
    try:
        contacts = await emergency_crud.get_user_emergency_contacts(
            session=db,
            user_id=current_user.id
        )
        logger.info(f"Retrieved {len(contacts)} emergency contacts for user {current_user.id}")
        return contacts
    except Exception as e:
        logger.error(f"Error getting emergency contacts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving emergency contacts."
        )

# --- USER RATINGS & REPUTATION ---

@router.get("/me/ratings-summary", response_model=UserRatingsSummary)
async def get_my_ratings_summary(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserRatingsSummary:
    """
    Get comprehensive rating summary for the current user.
    Shows overall reputation, average ratings, and recent reviews.
    """
    try:
        summary = await ratings_crud.get_user_ratings_summary(
            session=db,
            user_id=current_user.id
        )
        logger.info(f"Rating summary retrieved for user {current_user.id}")
        return summary
    except Exception as e:
        logger.error(f"Error getting ratings summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving your ratings summary."
        )

@router.get("/me/ratings/given")
async def get_my_given_ratings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100)
) -> dict:
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
        
        return {
            "ratings_given": [
                {
                    "id": rating.id,
                    "rated_user": rating.rated_user.full_name,
                    "trip_route": f"{rating.trip.from_location_text} → {rating.trip.to_location_text}",
                    "rating": rating.rating,
                    "review": rating.review,
                    "created_at": rating.created_at
                }
                for rating in ratings
            ],
            "total_count": len(ratings),
            "pagination": {"skip": skip, "limit": limit}
        }
    except Exception as e:
        logger.error(f"Error getting given ratings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving your ratings."
        )

@router.get("/me/ratings/received")
async def get_my_received_ratings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100)
) -> dict:
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
        
        return {
            "ratings_received": [
                {
                    "id": rating.id,
                    "rater": rating.rater.full_name,
                    "trip_route": f"{rating.trip.from_location_text} → {rating.trip.to_location_text}",
                    "rating": rating.rating,
                    "review": rating.review,
                    "punctuality": rating.punctuality,
                    "cleanliness": rating.cleanliness,
                    "communication": rating.communication,
                    "driving_quality": rating.driving_quality,
                    "created_at": rating.created_at
                }
                for rating in ratings
            ],
            "total_count": len(ratings),
            "pagination": {"skip": skip, "limit": limit}
        }
    except Exception as e:
        logger.error(f"Error getting received ratings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving ratings about you."
        )

# --- USER ANALYTICS & INSIGHTS ---

@router.get("/me/analytics")
async def get_my_user_analytics(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get comprehensive analytics for the current user.
    Includes travel patterns, preferences, ratings, and performance metrics.
    """
    try:
        # Get rating stats
        rating_stats = await ratings_crud.get_detailed_user_stats(
            session=db,
            user_id=current_user.id
        )
        
        # Get negotiation stats
        negotiation_stats = await get_user_negotiation_analytics(
            session=db,
            user_id=current_user.id
        )
        
        # Get preference analytics
        preference_analytics = await preferences_crud.get_user_preference_analytics(
            session=db,
            user_id=current_user.id
        )
        
        # Get message stats
        unread_count = await messaging_crud.get_unread_message_count(
            session=db,
            user_id=current_user.id
        )
        
        analytics = {
            "user_id": current_user.id,
            "user_role": current_user.role.value,
            "account_created": current_user.created_at,
            "rating_statistics": rating_stats,
            "negotiation_statistics": negotiation_stats,
            "preference_analytics": preference_analytics,
            "communication": {
                "unread_messages": unread_count
            },
            "safety": {
                "emergency_contacts_count": len(await emergency_crud.get_user_emergency_contacts(db, current_user.id))
            }
        }
        
        logger.info(f"User analytics retrieved for user {current_user.id}")
        return analytics
    except Exception as e:
        logger.error(f"Error getting user analytics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving your analytics."
        )

# --- TRAVEL HISTORY ---

@router.get("/me/travel-history")
async def get_my_travel_history(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    role_filter: Optional[str] = Query(default=None, regex="^(driver|passenger)$")
) -> dict:
    """
    Get comprehensive travel history for the current user.
    Shows both trips as driver and bookings as passenger.
    """
    try:
        history = {
            "user_id": current_user.id,
            "travel_summary": {},
            "recent_trips": []
        }
        
        if current_user.role == UserRole.DRIVER and (not role_filter or role_filter == "driver"):
            # Get trips as driver
            from crud import trip_crud
            driver_trips = await trip_crud.get_driver_created_trips(
                session=db,
                driver_id=current_user.id,
                skip=skip,
                limit=limit
            )
            
            history["driver_trips"] = [
                {
                    "trip_id": trip.id,
                    "route": f"{trip.from_location_text} → {trip.to_location_text}",
                    "departure_datetime": trip.departure_datetime,
                    "status": trip.status.value,
                    "seats_offered": trip.total_seats_offered,
                    "seats_booked": trip.total_seats_offered - trip.available_seats,
                    "price_per_seat": trip.price_per_seat,
                    "estimated_revenue": trip.price_per_seat * (trip.total_seats_offered - trip.available_seats)
                }
                for trip in driver_trips
            ]
        
        if not role_filter or role_filter == "passenger":
            # Get bookings as passenger
            from crud import booking_crud
            passenger_bookings = await booking_crud.get_passenger_bookings(
                session=db,
                passenger_id=current_user.id,
                skip=skip,
                limit=limit
            )
            
            history["passenger_bookings"] = [
                {
                    "booking_id": booking.id,
                    "trip_id": booking.trip_id,
                    "route": f"{booking.trip.from_location_text} → {booking.trip.to_location_text}",
                    "departure_datetime": booking.trip.departure_datetime,
                    "driver_name": booking.trip.driver.full_name,
                    "seats_booked": booking.seats_booked,
                    "total_price": booking.total_price,
                    "status": booking.status.value,
                    "booking_time": booking.booking_time
                }
                for booking in passenger_bookings
            ]
        
        logger.info(f"Travel history retrieved for user {current_user.id}")
        return history
    except Exception as e:
        logger.error(f"Error getting travel history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving your travel history."
        )

# --- SOCIAL FEATURES ---

@router.get("/me/connections")
async def get_my_connections(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100)
) -> dict:
    """
    Get users I have traveled with (my travel network).
    Shows people I've shared trips with for easy rebooking.
    """
    try:
        # This would involve complex queries to find users who have been trip companions
        # For now, return a structure placeholder
        connections = {
            "user_id": current_user.id,
            "total_connections": 0,
            "travel_partners": [],
            "frequent_routes_partners": [],
            "recent_connections": []
        }
        
        # In a real implementation, this would query bookings and trips to find:
        # 1. Users who booked my trips (if I'm a driver)
        # 2. Drivers whose trips I've booked (if I'm a passenger)
        # 3. Other passengers I've traveled with
        
        logger.info(f"Travel connections retrieved for user {current_user.id}")
        return connections
    except Exception as e:
        logger.error(f"Error getting travel connections: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving your travel connections."
        )

@router.get("/me/compatible-users")
async def get_compatible_users(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=10, ge=1, le=50)
) -> dict:
    """
    Get users with high compatibility for future trip matching.
    Useful for building a network of preferred travel partners.
    """
    try:
        matches = await preferences_crud.get_compatible_users(
            session=db,
            user_id=current_user.id,
            limit=limit
        )
        return {"compatible_users": matches}
    except Exception as e:
        logger.error(f"Error getting compatible users: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while finding compatible users."
        )

# --- NOTIFICATION & COMMUNICATION ---

@router.get("/me/notifications")
async def get_my_notifications(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100)
) -> dict:
    """
    Get recent notifications for the current user.
    """
    try:
        notifications = await notifications_crud.get_user_notifications(
            session=db,
            user_id=current_user.id,
            skip=skip,
            limit=limit
        )
        
        unread_count = await notifications_crud.get_unread_count(
            session=db,
            user_id=current_user.id
        )
        
        return {
            "notifications": [
                {
                    "id": notif.id,
                    "type": notif.notification_type.value,
                    "title": notif.title,
                    "content": notif.content,
                    "status": notif.status.value,
                    "created_at": notif.created_at,
                    "delivered_at": notif.delivered_at
                }
                for notif in notifications
            ],
            "unread_count": unread_count,
            "pagination": {"skip": skip, "limit": limit}
        }
    except Exception as e:
        logger.error(f"Error getting user notifications: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving notifications."
        )

@router.get("/me/message-threads")
async def get_my_message_threads(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100)
) -> dict:
    """
    Get message threads for the current user.
    """
    try:
        threads = await messaging_crud.get_user_threads(
            session=db,
            user_id=current_user.id,
            skip=skip,
            limit=limit
        )
        
        unread_count = await messaging_crud.get_unread_message_count(
            session=db,
            user_id=current_user.id
        )
        
        return {
            "message_threads": [
                {
                    "thread_id": thread.id,
                    "trip_id": thread.trip_id,
                    "trip_route": f"{thread.trip.from_location_text} → {thread.trip.to_location_text}" if thread.trip else "Direct Message",
                    "participants_count": len(thread.participants),
                    "last_message_time": thread.messages[0].created_at if thread.messages else thread.created_at,
                    "unread_messages": sum(1 for msg in thread.messages if not msg.is_read and msg.sender_id != current_user.id)
                }
                for thread in threads
            ],
            "total_unread_messages": unread_count,
            "pagination": {"skip": skip, "limit": limit}
        }
    except Exception as e:
        logger.error(f"Error getting message threads: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving message threads."
        )

# --- PUBLIC USER PROFILES ---

@router.get("/{user_id}/public-profile")
async def get_public_user_profile(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get public profile information for another user.
    Shows only information that the user has made public.
    """
    try:
        # Get user basic info
        from sqlalchemy import select
        user_result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found."
            )
        
        # Get user settings to check privacy preferences
        user_settings = await preferences_crud.get_user_settings(
            session=db,
            user_id=user_id
        )
        
        # Get public ratings
        public_ratings = await ratings_crud.get_public_ratings(
            session=db,
            user_id=user_id,
            limit=5
        )
        
        # Get ratings summary
        ratings_summary = await ratings_crud.get_user_ratings_summary(
            session=db,
            user_id=user_id
        )
        
        # Build public profile based on privacy settings
        public_profile = {
            "user_id": user_id,
            "full_name": user.full_name,
            "role": user.role.value,
            "member_since": user.created_at,
            "profile_image_url": user.profile_image_url if user_settings.show_profile_picture else None,
            "bio": user.bio,
            "spoken_languages": user.spoken_languages,
            "ratings_summary": {
                "average_rating": ratings_summary.average_rating,
                "total_ratings": ratings_summary.total_ratings,
                "rating_breakdown": ratings_summary.rating_breakdown
            },
            "recent_reviews": [
                {
                    "rating": rating.rating,
                    "review": rating.review,
                    "created_at": rating.created_at,
                    "rater_name": rating.rater.full_name
                }
                for rating in public_ratings
            ]
        }
        
        # Add phone number only if user allows it
        if user_settings.show_phone_to_driver:
            public_profile["phone_number"] = user.phone_number
        
        logger.info(f"Public profile retrieved for user {user_id}")
        return public_profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting public user profile: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving user profile."
        )

@router.get("/{user_id}/compatibility")
async def check_compatibility_with_user(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Check travel compatibility with another user.
    Useful for evaluating potential trip partners.
    """
    try:
        if user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot check compatibility with yourself."
            )
        
        compatibility = await preferences_crud.check_user_compatibility(
            session=db,
            user1_id=current_user.id,
            user2_id=user_id
        )
        
        return compatibility
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking user compatibility: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while checking compatibility."
        )

# --- ACCOUNT MANAGEMENT ---

@router.post("/me/deactivate")
async def deactivate_my_account(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    reason: Optional[str] = Query(default=None, max_length=500)
) -> dict:
    """
    Deactivate the current user's account.
    This will cancel all future trips and bookings.
    """
    try:
        # In a real implementation, this would:
        # 1. Cancel all future trips and bookings
        # 2. Notify affected users
        # 3. Set user status to inactive
        # 4. Log the deactivation reason
        
        logger.info(f"Account deactivation requested for user {current_user.id}")
        return {
            "message": "Account deactivation initiated. You will receive confirmation within 24 hours.",
            "support_contact": "support@autoport.uz"
        }
    except Exception as e:
        logger.error(f"Error deactivating account: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing account deactivation."
        )

@router.post("/me/export-data")
async def export_my_data(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Export all user data (GDPR compliance).
    Generates a comprehensive export of all user information.
    """
    try:
        # In a real implementation, this would:
        # 1. Gather all user data from all tables
        # 2. Create a downloadable file
        # 3. Send download link via email
        # 4. Schedule file deletion after 30 days
        
        logger.info(f"Data export requested for user {current_user.id}")
        return {
            "message": "Data export initiated. You will receive a download link via email within 24 hours.",
            "estimated_completion": "24 hours",
            "file_retention": "30 days"
        }
    except Exception as e:
        logger.error(f"Error exporting user data: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while initiating data export."
        )

# --- ADMIN USER MANAGEMENT ---

@router.get("/search", dependencies=[Depends(get_current_admin_user)])
async def admin_search_users(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search_query: Optional[str] = Query(default=None, min_length=3),
    role_filter: Optional[str] = Query(default=None, regex="^(passenger|driver|admin)$"),
    status_filter: Optional[str] = Query(default=None, regex="^(active|blocked|pending)$"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200)
) -> dict:
    """
    Admin endpoint to search and filter users.
    """
    try:
        # This would involve complex user search functionality
        # For now, return a placeholder structure
        users = {
            "search_query": search_query,
            "filters": {
                "role": role_filter,
                "status": status_filter
            },
            "results": [],
            "total_count": 0,
            "pagination": {"skip": skip, "limit": limit}
        }
        
        logger.info(f"Admin user search performed by {current_admin.id}")
        return users
    except Exception as e:
        logger.error(f"Error in admin user search: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while searching users."
        )

@router.get("/{user_id}/admin-details", dependencies=[Depends(get_current_admin_user)])
async def admin_get_user_details(
    user_id: UUID,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Admin endpoint to get comprehensive user details.
    """
    try:
        # Get user basic info
        from sqlalchemy import select
        user_result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found."
            )
        
        # Get comprehensive user data for admin
        user_details = {
            "user_info": {
                "id": user.id,
                "phone_number": user.phone_number,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role.value,
                "status": user.status.value,
                "created_at": user.created_at,
                "updated_at": user.updated_at
            },
            "ratings_summary": await ratings_crud.get_user_ratings_summary(db, user_id),
            "emergency_contacts_count": len(await emergency_crud.get_user_emergency_contacts(db, user_id)),
            "settings": await preferences_crud.get_user_settings(db, user_id)
        }
        
        logger.info(f"Admin user details retrieved for user {user_id} by admin {current_admin.id}")
        return user_details
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting admin user details: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving user details."
        )

# --- HELPER FUNCTIONS ---

async def get_user_negotiation_analytics(session: AsyncSession, user_id: UUID) -> dict:
    """Get negotiation analytics for a user."""
    try:
        # Import here to avoid circular imports
        from crud import negotiations_crud
        return await negotiations_crud.get_user_negotiation_analytics(session, user_id)
    except Exception as e:
        logger.error(f"Error getting negotiation analytics: {e}", exc_info=True)
        return {"error": "Unable to retrieve negotiation analytics"}