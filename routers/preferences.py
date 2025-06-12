# File: routers/preferences.py

import logging
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_active_user
from crud import preferences_crud
from database import get_db
from models import User
from schemas import (
    TravelPreferenceCreate, TravelPreferenceUpdate, TravelPreferenceResponse,
    UserSettingsUpdate, UserSettingsResponse, UserProfileUpdate, UserResponse,
    TripSearchFilters, TripResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/preferences", tags=["preferences"])

# --- TRAVEL PREFERENCES ---

@router.post("/travel", response_model=TravelPreferenceResponse, status_code=status.HTTP_201_CREATED)
async def create_travel_preferences(
    preferences_data: TravelPreferenceCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TravelPreferenceResponse:
    """
    Create or update travel preferences for the current user.
    These preferences help match with compatible drivers/passengers.
    """
    try:
        preferences = await preferences_crud.create_or_update_travel_preferences(
            session=db,
            user_id=current_user.id,
            preferences_data=preferences_data
        )
        
        logger.info(f"Travel preferences created/updated for user {current_user.id}")
        return preferences
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating travel preferences: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating travel preferences."
        )

@router.get("/travel", response_model=TravelPreferenceResponse)
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

@router.patch("/travel", response_model=TravelPreferenceResponse)
async def update_travel_preferences(
    preferences_data: TravelPreferenceUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TravelPreferenceResponse:
    """
    Update travel preferences for the current user.
    """
    try:
        preferences = await preferences_crud.update_travel_preferences(
            session=db,
            user_id=current_user.id,
            preferences_data=preferences_data
        )
        if not preferences:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Travel preferences not found. Please create them first."
            )
        
        logger.info(f"Travel preferences updated for user {current_user.id}")
        return preferences
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating travel preferences: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating travel preferences."
        )

@router.delete("/travel")
async def delete_travel_preferences(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Delete travel preferences for the current user.
    This will reset to default matching behavior.
    """
    try:
        success = await preferences_crud.delete_travel_preferences(
            session=db,
            user_id=current_user.id
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Travel preferences not found."
            )
        
        logger.info(f"Travel preferences deleted for user {current_user.id}")
        return {"message": "Travel preferences deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting travel preferences: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting travel preferences."
        )

# --- USER SETTINGS ---

@router.get("/settings", response_model=UserSettingsResponse)
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

@router.patch("/settings", response_model=UserSettingsResponse)
async def update_my_settings(
    settings_data: UserSettingsUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserSettingsResponse:
    """
    Update application settings for the current user.
    """
    try:
        settings = await preferences_crud.update_user_settings(
            session=db,
            user_id=current_user.id,
            settings_data=settings_data
        )
        
        logger.info(f"User settings updated for user {current_user.id}")
        return settings
    except Exception as e:
        logger.error(f"Error updating user settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating settings."
        )

# --- PROFILE PREFERENCES ---

@router.patch("/profile", response_model=UserResponse)
async def update_profile_preferences(
    profile_data: UserProfileUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserResponse:
    """
    Update profile preferences (language, bio, etc.) for the current user.
    """
    try:
        updated_user = await preferences_crud.update_user_profile_preferences(
            session=db,
            user_id=current_user.id,
            profile_data=profile_data
        )
        
        logger.info(f"Profile preferences updated for user {current_user.id}")
        return updated_user
    except Exception as e:
        logger.error(f"Error updating profile preferences: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating profile preferences."
        )

# --- PREFERENCE-BASED SEARCH ---

@router.post("/search-compatible-trips", response_model=List[TripResponse])
async def search_compatible_trips(
    search_filters: TripSearchFilters,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[TripResponse]:
    """
    Search for trips that match user's travel preferences.
    This provides intelligent matching based on compatibility.
    """
    try:
        trips = await preferences_crud.search_trips_by_preferences(
            session=db,
            user_id=current_user.id,
            search_filters=search_filters
        )
        
        logger.info(f"Found {len(trips)} compatible trips for user {current_user.id}")
        return trips
    except Exception as e:
        logger.error(f"Error searching compatible trips: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while searching for compatible trips."
        )

@router.get("/compatibility/{user_id}")
async def check_user_compatibility(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Check compatibility between current user and another user.
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

# --- LANGUAGE AND LOCALIZATION ---

@router.get("/languages")
async def get_supported_languages() -> dict:
    """
    Get list of supported languages for the application.
    Important for the multilingual Uzbekistan market.
    """
    return {
        "supported_languages": [
            {"code": "uz", "name": "O'zbek", "name_english": "Uzbek", "script": "latin"},
            {"code": "ru", "name": "Русский", "name_english": "Russian", "script": "cyrillic"},
            {"code": "en", "name": "English", "name_english": "English", "script": "latin"}
        ],
        "default_language": "uz",
        "currency_options": [
            {"code": "UZS", "name": "Uzbek Som", "symbol": "so'm"},
            {"code": "USD", "name": "US Dollar", "symbol": "$"},
            {"code": "EUR", "name": "Euro", "symbol": "€"}
        ]
    }

@router.patch("/language")
async def update_language_preference(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    language: str = Query(..., regex="^(uz|ru|en)$")
) -> dict:
    """
    Update language preference for the current user.
    """
    try:
        success = await preferences_crud.update_user_language(
            session=db,
            user_id=current_user.id,
            language=language
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update language preference."
            )
        
        logger.info(f"Language preference updated to {language} for user {current_user.id}")
        return {"message": f"Language updated to {language}", "language": language}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating language preference: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating language preference."
        )

# --- SAVED ROUTES AND FAVORITES ---

@router.post("/routes/save")
async def save_frequent_route(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_location: str = Query(..., min_length=3, max_length=200),
    to_location: str = Query(..., min_length=3, max_length=200),
    route_name: Optional[str] = Query(default=None, max_length=100)
) -> dict:
    """
    Save a frequently used route for quick access.
    """
    try:
        success = await preferences_crud.save_frequent_route(
            session=db,
            user_id=current_user.id,
            from_location=from_location,
            to_location=to_location,
            route_name=route_name
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Route already saved or maximum routes reached."
            )
        
        logger.info(f"Route saved for user {current_user.id}: {from_location} to {to_location}")
        return {"message": "Route saved successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving frequent route: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while saving the route."
        )

@router.get("/routes/saved")
async def get_saved_routes(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get all saved frequent routes for the current user.
    """
    try:
        routes = await preferences_crud.get_saved_routes(
            session=db,
            user_id=current_user.id
        )
        return {"saved_routes": routes}
    except Exception as e:
        logger.error(f"Error getting saved routes: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving saved routes."
        )

@router.delete("/routes/{route_id}")
async def delete_saved_route(
    route_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Delete a saved route.
    """
    try:
        success = await preferences_crud.delete_saved_route(
            session=db,
            route_id=route_id,
            user_id=current_user.id
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Saved route not found or you don't have permission to delete it."
            )
        
        logger.info(f"Saved route {route_id} deleted for user {current_user.id}")
        return {"message": "Saved route deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting saved route: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the saved route."
        )

# --- PREFERENCE RECOMMENDATIONS ---

@router.get("/recommendations/preferences")
async def get_preference_recommendations(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get intelligent preference recommendations based on user's trip history.
    """
    try:
        recommendations = await preferences_crud.get_preference_recommendations(
            session=db,
            user_id=current_user.id
        )
        return recommendations
    except Exception as e:
        logger.error(f"Error getting preference recommendations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating preference recommendations."
        )

@router.post("/onboarding/complete")
async def complete_preference_onboarding(
    travel_preferences: TravelPreferenceCreate,
    settings: UserSettingsUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    language: str = Query(default="uz", regex="^(uz|ru|en)$")
) -> dict:
    """
    Complete the preference onboarding process for new users.
    Sets up travel preferences, app settings, and language in one go.
    """
    try:
        success = await preferences_crud.complete_onboarding(
            session=db,
            user_id=current_user.id,
            travel_preferences=travel_preferences,
            settings=settings,
            language=language
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to complete onboarding setup."
            )
        
        logger.info(f"Preference onboarding completed for user {current_user.id}")
        return {"message": "Onboarding completed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing preference onboarding: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while completing onboarding."
        )

# --- PRIVACY AND VISIBILITY SETTINGS ---

@router.patch("/privacy/visibility")
async def update_profile_visibility(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    show_phone_to_driver: Optional[bool] = Query(default=None),
    show_profile_picture: Optional[bool] = Query(default=None),
    allow_contact_from_passengers: Optional[bool] = Query(default=None)
) -> dict:
    """
    Update profile visibility and privacy settings.
    Important for user safety and privacy control.
    """
    try:
        updated_settings = await preferences_crud.update_privacy_settings(
            session=db,
            user_id=current_user.id,
            show_phone_to_driver=show_phone_to_driver,
            show_profile_picture=show_profile_picture,
            allow_contact_from_passengers=allow_contact_from_passengers
        )
        
        logger.info(f"Privacy settings updated for user {current_user.id}")
        return {
            "message": "Privacy settings updated successfully",
            "settings": updated_settings
        }
    except Exception as e:
        logger.error(f"Error updating privacy settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating privacy settings."
        )

@router.get("/recommendations/matches")
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

# --- PREFERENCE ANALYTICS ---

@router.get("/analytics/my-preferences")
async def get_preference_analytics(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get analytics about user's travel patterns and preferences.
    Helps users understand their travel behavior.
    """
    try:
        analytics = await preferences_crud.get_user_preference_analytics(
            session=db,
            user_id=current_user.id
        )
        return analytics
    except Exception as e:
        logger.error(f"Error getting preference analytics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating preference analytics."
        )

@router.post("/feedback/preferences")
async def submit_preference_feedback(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    feedback_type: str = Query(..., regex="^(helpful|not_helpful|suggestion)$"),
    feedback_text: Optional[str] = Query(default=None, max_length=500)
) -> dict:
    """
    Submit feedback about the preference matching system.
    Helps improve the matching algorithm.
    """
    try:
        success = await preferences_crud.submit_preference_feedback(
            session=db,
            user_id=current_user.id,
            feedback_type=feedback_type,
            feedback_text=feedback_text
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to submit feedback."
            )
        
        logger.info(f"Preference feedback submitted by user {current_user.id}")
        return {"message": "Feedback submitted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting preference feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while submitting feedback."
        )