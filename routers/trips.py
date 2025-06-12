# File: routers/trips.py (Enhanced with all new features)

import logging
from datetime import date, datetime, timedelta
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.dependencies import get_current_active_user
from crud import trip_crud, messaging_crud, negotiations_crud, ratings_crud, preferences_crud
from database import get_db
from models import User, UserRole, Trip, Car
from schemas import (
    TripCreate, TripResponse, TripUpdate, TripSearchFilters,
    PriceRecommendationRequest, PriceRecommendationResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trips", tags=["trips"])

@router.post("/", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def create_trip(
    trip_in: TripCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TripResponse:
    """
    Create a new trip with enhanced features.
    Now supports price negotiation, advanced preferences, and automatic notifications.
    """
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can create trips.")
    
    try:
        created_trip_shell = await trip_crud.create_driver_trip(session=db, trip_in=trip_in, driver_id=current_user.id)
        
        # Re-fetch for response with relationships
        trip_result = await db.execute(
            select(Trip).options(selectinload(Trip.driver), selectinload(Trip.car))
            .where(Trip.id == created_trip_shell.id)
        )
        trip_to_return = trip_result.scalar_one_or_none()
        if not trip_to_return:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve created trip for response.")

        logger.info(f"Successfully created trip {trip_to_return.id} for driver {current_user.id}")
        return trip_to_return
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in create_trip: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.get("/search", response_model=List[TripResponse])
async def search_trips(
    db: Annotated[AsyncSession, Depends(get_db)],
    from_location: Annotated[str, Query(description="Departure location")] = None,
    to_location: Annotated[str, Query(description="Destination location")] = None,
    departure_date: Annotated[date, Query(description="Departure date")] = None,
    seats_needed: Annotated[int, Query(ge=1, description="Number of seats needed")] = 1,
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return")] = 20
) -> List[TripResponse]:
    """
    Search trips with basic filters.
    For advanced preference-based search, use /search-advanced endpoint.
    """
    trips = await trip_crud.search_trips(
        session=db, 
        from_location=from_location, 
        to_location=to_location, 
        departure_date=departure_date, 
        seats_needed=seats_needed, 
        skip=skip, 
        limit=limit
    )
    return trips

@router.post("/search-advanced", response_model=List[TripResponse])
async def search_trips_advanced(
    search_filters: TripSearchFilters,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[TripResponse]:
    """
    Advanced trip search with preference-based matching.
    Finds trips that match user's travel preferences for better compatibility.
    """
    try:
        trips = await preferences_crud.search_trips_by_preferences(
            session=db,
            user_id=current_user.id,
            search_filters=search_filters
        )
        
        logger.info(f"Advanced search returned {len(trips)} trips for user {current_user.id}")
        return trips
    except Exception as e:
        logger.error(f"Error in advanced trip search: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during advanced search."
        )

@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(
    trip_id: UUID, 
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TripResponse:
    """
    Get detailed information about a specific trip.
    """
    trip = await trip_crud.get_trip_by_id(session=db, trip_id=trip_id)
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")
    return trip 

@router.get("/my-created", response_model=List[TripResponse])
async def get_my_created_trips(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return")] = 20
) -> List[TripResponse]:
    """
    Get trips created by the current driver.
    """
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can view their created trips.")
    
    trips = await trip_crud.get_driver_created_trips(session=db, driver_id=current_user.id, skip=skip, limit=limit)
    logger.info(f"Successfully retrieved {len(trips)} trips for driver {current_user.id}")
    return trips 

@router.patch("/{trip_id}", response_model=TripResponse)
async def update_my_trip(
    trip_id: UUID, 
    trip_in: TripUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TripResponse:
    """
    Update trip details.
    Enhanced with automatic notification to booked passengers about changes.
    """
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can update their trips.")
    
    try:
        trip = await trip_crud.get_driver_trip_by_id(session=db, trip_id=trip_id, driver_id=current_user.id)
        if not trip:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found or you do not have permission to update it.")
        
        updated_trip_shell = await trip_crud.update_driver_trip(session=db, trip_to_update=trip, trip_in=trip_in, current_driver_id=current_user.id)
        
        # Re-fetch for response
        trip_result = await db.execute(
            select(Trip).options(selectinload(Trip.driver), selectinload(Trip.car))
            .where(Trip.id == updated_trip_shell.id)
        )
        trip_to_return = trip_result.scalar_one_or_none()
        if not trip_to_return:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve updated trip for response.")

        logger.info(f"Successfully updated trip {trip_to_return.id} for driver {current_user.id}")
        return trip_to_return
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_my_trip: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.post("/{trip_id}/cancel", response_model=TripResponse)
async def cancel_my_trip(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TripResponse:
    """
    Cancel a trip.
    Enhanced with automatic notifications to passengers and emergency contact alerts.
    """
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only drivers can cancel their trips.")
    
    try:
        trip = await trip_crud.get_driver_trip_by_id(session=db, trip_id=trip_id, driver_id=current_user.id)
        if not trip:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found or you do not have permission to cancel it.")
        
        cancelled_trip_shell = await trip_crud.cancel_driver_trip(session=db, trip_to_cancel=trip)
        
        # Re-fetch for response
        trip_result = await db.execute(
            select(Trip).options(selectinload(Trip.driver), selectinload(Trip.car))
            .where(Trip.id == cancelled_trip_shell.id)
        )
        trip_to_return = trip_result.scalar_one_or_none()
        if not trip_to_return:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve cancelled trip for response.")
            
        logger.info(f"Successfully cancelled trip {trip_to_return.id} for driver {current_user.id}")
        return trip_to_return
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in cancel_my_trip: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

# --- NEW ENHANCED FEATURES ---

@router.post("/{trip_id}/start-conversation", response_model=dict)
async def start_trip_conversation(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Start a group conversation for all trip participants.
    Creates a message thread between driver and all passengers.
    """
    try:
        thread = await messaging_crud.create_trip_thread(
            session=db,
            trip_id=trip_id,
            initiator_id=current_user.id
        )
        
        logger.info(f"Trip conversation started for trip {trip_id} by user {current_user.id}")
        return {
            "message": "Trip conversation started successfully",
            "thread_id": thread.id,
            "participants_count": len(thread.participants)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting trip conversation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while starting the conversation."
        )

@router.get("/{trip_id}/negotiations", response_model=List[dict])
async def get_trip_negotiations(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[dict]:
    """
    Get all price negotiations for this trip (driver only).
    Shows pending offers and negotiation history.
    """
    try:
        if current_user.role != UserRole.DRIVER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only drivers can view trip negotiations."
            )
        
        negotiations = await negotiations_crud.get_trip_negotiations(
            session=db,
            trip_id=trip_id,
            user_id=current_user.id
        )
        
        return [
            {
                "id": neg.id,
                "passenger_name": neg.passenger.full_name,
                "passenger_id": neg.passenger_id,
                "original_price": neg.original_price,
                "proposed_price": neg.proposed_price,
                "final_price": neg.final_price,
                "seats_requested": neg.seats_requested,
                "status": neg.status.value,
                "message": neg.message,
                "created_at": neg.created_at,
                "expires_at": neg.expires_at,
                "response_message": neg.response_message
            }
            for neg in negotiations
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trip negotiations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving negotiations."
        )

@router.post("/{trip_id}/price-recommendation", response_model=PriceRecommendationResponse)
async def get_trip_price_recommendation(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> PriceRecommendationResponse:
    """
    Get AI-powered price recommendations for a trip.
    Helps drivers set competitive prices and passengers make fair offers.
    """
    try:
        # Get trip details
        trip = await trip_crud.get_trip_by_id(session=db, trip_id=trip_id)
        if not trip:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")
        
        # Create recommendation request
        recommendation_request = PriceRecommendationRequest(
            from_location=trip.from_location_text,
            to_location=trip.to_location_text,
            distance_km=trip.estimated_distance_km,
            estimated_duration_minutes=trip.estimated_duration_minutes,
            departure_datetime=trip.departure_datetime,
            comfort_level=getattr(trip, 'comfort_level', 'economy')
        )
        
        recommendation = await negotiations_crud.get_price_recommendation(
            session=db,
            user_id=current_user.id,
            recommendation_request=recommendation_request
        )
        
        logger.info(f"Price recommendation generated for trip {trip_id}")
        return recommendation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting price recommendation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating price recommendation."
        )

@router.get("/{trip_id}/compatibility/{user_id}")
async def check_trip_compatibility(
    trip_id: UUID,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Check compatibility between a user and trip participants.
    Helps assess travel compatibility before booking.
    """
    try:
        # Get trip details
        trip = await trip_crud.get_trip_by_id(session=db, trip_id=trip_id)
        if not trip:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")
        
        # Check compatibility with driver
        driver_compatibility = await preferences_crud.check_user_compatibility(
            session=db,
            user1_id=current_user.id,
            user2_id=trip.driver_id
        )
        
        # If checking specific user, get their compatibility too
        user_compatibility = None
        if user_id != trip.driver_id:
            user_compatibility = await preferences_crud.check_user_compatibility(
                session=db,
                user1_id=current_user.id,
                user2_id=user_id
            )
        
        return {
            "trip_id": trip_id,
            "driver_compatibility": driver_compatibility,
            "user_compatibility": user_compatibility,
            "overall_score": (driver_compatibility.get("compatibility_score", 0) + 
                            (user_compatibility.get("compatibility_score", 0) if user_compatibility else 0)) / 2
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking trip compatibility: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while checking compatibility."
        )

@router.get("/{trip_id}/ratings", response_model=List[dict])
async def get_trip_ratings(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[dict]:
    """
    Get all ratings and reviews for a trip.
    Shows feedback from all participants after trip completion.
    """
    try:
        # Verify user has access to this trip
        trip_access = await messaging_crud.verify_trip_access(
            session=db,
            trip_id=trip_id,
            user_id=current_user.id
        )
        if not trip_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to view ratings for this trip."
            )
        
        # Get ratings given by current user
        my_ratings = await ratings_crud.get_user_ratings_for_trip(
            session=db,
            trip_id=trip_id,
            user_id=current_user.id,
            given_by_user=True
        )
        
        # Get ratings received by current user
        received_ratings = await ratings_crud.get_user_ratings_for_trip(
            session=db,
            trip_id=trip_id,
            user_id=current_user.id,
            given_by_user=False
        )
        
        return {
            "trip_id": trip_id,
            "ratings_given": [
                {
                    "id": rating.id,
                    "rated_user": rating.rated_user.full_name,
                    "rating": rating.rating,
                    "review": rating.review,
                    "punctuality": rating.punctuality,
                    "cleanliness": rating.cleanliness,
                    "communication": rating.communication,
                    "driving_quality": rating.driving_quality,
                    "created_at": rating.created_at
                }
                for rating in my_ratings
            ],
            "ratings_received": [
                {
                    "id": rating.id,
                    "rater": rating.rater.full_name,
                    "rating": rating.rating,
                    "review": rating.review,
                    "punctuality": rating.punctuality,
                    "cleanliness": rating.cleanliness,
                    "communication": rating.communication,
                    "driving_quality": rating.driving_quality,
                    "created_at": rating.created_at
                }
                for rating in received_ratings
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trip ratings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving trip ratings."
        )

@router.post("/{trip_id}/share-location")
async def share_trip_location(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Share live trip location with emergency contacts.
    Important safety feature for trip participants.
    """
    try:
        from crud import emergency_crud
        
        success = await emergency_crud.share_trip_location(
            session=db,
            trip_id=trip_id,
            user_id=current_user.id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot share location for this trip or no emergency contacts found."
            )
        
        logger.info(f"Live location shared for trip {trip_id} by user {current_user.id}")
        return {"message": "Live location shared with emergency contacts"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sharing trip location: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while sharing location."
        )

@router.post("/{trip_id}/arrived-safely")
async def mark_arrived_safely(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Mark that user has arrived safely.
    Sends confirmation to emergency contacts who were tracking the trip.
    """
    try:
        from crud import emergency_crud
        
        success = await emergency_crud.mark_trip_completed_safely(
            session=db,
            trip_id=trip_id,
            user_id=current_user.id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot mark trip as safely completed."
            )
        
        logger.info(f"Trip {trip_id} marked as safely completed by user {current_user.id}")
        return {"message": "Safe arrival notification sent to emergency contacts"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking trip as safe: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while confirming safe arrival."
        )

@router.get("/{trip_id}/analytics")
async def get_trip_analytics(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get analytics for a specific trip (driver only).
    Shows booking patterns, negotiations, ratings, and performance metrics.
    """
    try:
        if current_user.role != UserRole.DRIVER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only drivers can view trip analytics."
            )
        
        # Verify trip ownership
        trip = await trip_crud.get_driver_trip_by_id(session=db, trip_id=trip_id, driver_id=current_user.id)
        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found or you don't have permission to view analytics."
            )
        
        # Get various analytics
        analytics = {
            "trip_id": trip_id,
            "basic_info": {
                "route": f"{trip.from_location_text} → {trip.to_location_text}",
                "departure_datetime": trip.departure_datetime,
                "status": trip.status.value,
                "total_seats": trip.total_seats_offered,
                "available_seats": trip.available_seats,
                "price_per_seat": trip.price_per_seat,
                "estimated_revenue": trip.price_per_seat * (trip.total_seats_offered - trip.available_seats)
            }
        }
        
        # Add more analytics data here (bookings, negotiations, ratings)
        # This would involve calling various CRUD functions to get comprehensive data
        
        logger.info(f"Trip analytics retrieved for trip {trip_id} by driver {current_user.id}")
        return analytics
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trip analytics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving trip analytics."
        )

@router.post("/{trip_id}/duplicate")
async def duplicate_trip(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    departure_datetime: datetime = Query(..., description="New departure date and time")
) -> TripResponse:
    """
    Duplicate an existing trip with a new departure time.
    Useful for recurring routes and regular trips.
    """
    try:
        if current_user.role != UserRole.DRIVER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only drivers can duplicate trips."
            )
        
        # Get original trip
        original_trip = await trip_crud.get_driver_trip_by_id(session=db, trip_id=trip_id, driver_id=current_user.id)
        if not original_trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Original trip not found or you don't have permission to duplicate it."
            )
        
        # Create new trip with same details but new departure time
        trip_data = TripCreate(
            car_id=original_trip.car_id,
            from_location_text=original_trip.from_location_text,
            to_location_text=original_trip.to_location_text,
            departure_datetime=departure_datetime,
            estimated_arrival_datetime=departure_datetime + timedelta(
                minutes=original_trip.estimated_duration_minutes or 60
            ) if original_trip.estimated_duration_minutes else None,
            price_per_seat=original_trip.price_per_seat,
            total_seats_offered=original_trip.total_seats_offered,
            additional_info=original_trip.additional_info,
            intermediate_stops=original_trip.intermediate_stops,
            trip_preferences=original_trip.trip_preferences,
            is_instant_booking=original_trip.is_instant_booking,
            max_detour_km=original_trip.max_detour_km,
            price_negotiable=original_trip.price_negotiable,
            estimated_distance_km=original_trip.estimated_distance_km,
            estimated_duration_minutes=original_trip.estimated_duration_minutes
        )
        
        new_trip = await trip_crud.create_driver_trip(session=db, trip_in=trip_data, driver_id=current_user.id)
        
        # Re-fetch with relationships
        trip_result = await db.execute(
            select(Trip).options(selectinload(Trip.driver), selectinload(Trip.car))
            .where(Trip.id == new_trip.id)
        )
        duplicated_trip = trip_result.scalar_one()
        
        logger.info(f"Trip {trip_id} duplicated as {new_trip.id} by driver {current_user.id}")
        return duplicated_trip
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error duplicating trip: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while duplicating the trip."
        )

@router.post("/{trip_id}/send-reminder")
async def send_trip_reminder(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Send reminder notifications to all trip participants.
    Only the driver can send reminders about upcoming trips.
    """
    try:
        if current_user.role != UserRole.DRIVER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only drivers can send trip reminders."
            )
        
        from crud import notifications_crud
        
        sent_count = await notifications_crud.send_trip_reminder(
            session=db,
            trip_id=trip_id,
            sender_id=current_user.id
        )
        
        logger.info(f"Trip reminder sent to {sent_count} participants by driver {current_user.id}")
        return {
            "message": f"Reminder sent to {sent_count} participants",
            "sent_count": sent_count
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending trip reminder: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while sending trip reminder."
        )

# --- SMART RECOMMENDATIONS ---

@router.get("/recommendations/for-me")
async def get_recommended_trips(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=10, ge=1, le=50)
) -> dict:
    """
    Get AI-powered trip recommendations based on user's history and preferences.
    Suggests trips that match user's travel patterns and compatibility.
    """
    try:
        if current_user.role != UserRole.PASSENGER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Trip recommendations are only available for passengers."
            )
        
        # This would involve complex ML-based recommendations
        # For now, return a placeholder structure
        recommendations = {
            "user_id": current_user.id,
            "recommendation_count": 0,
            "recommended_trips": [],
            "based_on": {
                "travel_history": "Recent trip patterns",
                "preferences": "User travel preferences",
                "compatibility": "High compatibility matches"
            },
            "message": "Recommendation engine coming soon"
        }
        
        logger.info(f"Trip recommendations generated for user {current_user.id}")
        return recommendations
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trip recommendations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating recommendations."
        )