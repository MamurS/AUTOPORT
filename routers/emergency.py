# File: routers/emergency.py

import logging
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_active_user, get_current_admin_user
from crud import emergency_crud
from database import get_db
from models import User
from schemas import (
    EmergencyContactCreate, EmergencyContactUpdate, EmergencyContactResponse,
    EmergencyAlertCreate, EmergencyAlertResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/emergency", tags=["emergency"])

# --- EMERGENCY CONTACTS ---

@router.post("/contacts", response_model=EmergencyContactResponse, status_code=status.HTTP_201_CREATED)
async def add_emergency_contact(
    contact_data: EmergencyContactCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> EmergencyContactResponse:
    """
    Add a new emergency contact.
    Users can add up to 5 emergency contacts for safety.
    """
    try:
        contact = await emergency_crud.create_emergency_contact(
            session=db,
            user_id=current_user.id,
            contact_data=contact_data
        )
        
        logger.info(f"Emergency contact added by user {current_user.id}")
        return contact
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding emergency contact: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while adding the emergency contact."
        )

@router.get("/contacts", response_model=List[EmergencyContactResponse])
async def get_my_emergency_contacts(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[EmergencyContactResponse]:
    """
    Get all emergency contacts for the current user.
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

@router.patch("/contacts/{contact_id}", response_model=EmergencyContactResponse)
async def update_emergency_contact(
    contact_id: UUID,
    contact_data: EmergencyContactUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> EmergencyContactResponse:
    """
    Update an emergency contact.
    """
    try:
        contact = await emergency_crud.update_emergency_contact(
            session=db,
            contact_id=contact_id,
            user_id=current_user.id,
            contact_data=contact_data
        )
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Emergency contact not found or you don't have permission to update it."
            )
        
        logger.info(f"Emergency contact {contact_id} updated by user {current_user.id}")
        return contact
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating emergency contact: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the emergency contact."
        )

@router.delete("/contacts/{contact_id}")
async def delete_emergency_contact(
    contact_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Delete an emergency contact.
    """
    try:
        success = await emergency_crud.delete_emergency_contact(
            session=db,
            contact_id=contact_id,
            user_id=current_user.id
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Emergency contact not found or you don't have permission to delete it."
            )
        
        logger.info(f"Emergency contact {contact_id} deleted by user {current_user.id}")
        return {"message": "Emergency contact deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting emergency contact: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the emergency contact."
        )

@router.post("/contacts/{contact_id}/set-primary", response_model=EmergencyContactResponse)
async def set_primary_emergency_contact(
    contact_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> EmergencyContactResponse:
    """
    Set an emergency contact as primary.
    Only one contact can be primary at a time.
    """
    try:
        contact = await emergency_crud.set_primary_emergency_contact(
            session=db,
            contact_id=contact_id,
            user_id=current_user.id
        )
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Emergency contact not found or you don't have permission to modify it."
            )
        
        logger.info(f"Emergency contact {contact_id} set as primary by user {current_user.id}")
        return contact
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting primary emergency contact: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while setting the primary emergency contact."
        )

# --- EMERGENCY ALERTS ---

@router.post("/alerts", response_model=EmergencyAlertResponse, status_code=status.HTTP_201_CREATED)
async def create_emergency_alert(
    alert_data: EmergencyAlertCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> EmergencyAlertResponse:
    """
    Create an emergency alert (SOS).
    This will automatically notify emergency contacts and relevant authorities.
    """
    try:
        alert = await emergency_crud.create_emergency_alert(
            session=db,
            user_id=current_user.id,
            alert_data=alert_data
        )
        
        logger.info(f"Emergency alert created by user {current_user.id}, type: {alert_data.emergency_type}")
        return alert
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating emergency alert: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the emergency alert."
        )

@router.get("/alerts", response_model=List[EmergencyAlertResponse])
async def get_my_emergency_alerts(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100)
) -> List[EmergencyAlertResponse]:
    """
    Get emergency alerts for the current user.
    """
    try:
        alerts = await emergency_crud.get_user_emergency_alerts(
            session=db,
            user_id=current_user.id,
            skip=skip,
            limit=limit
        )
        logger.info(f"Retrieved {len(alerts)} emergency alerts for user {current_user.id}")
        return alerts
    except Exception as e:
        logger.error(f"Error getting emergency alerts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving emergency alerts."
        )

@router.get("/alerts/{alert_id}", response_model=EmergencyAlertResponse)
async def get_emergency_alert(
    alert_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> EmergencyAlertResponse:
    """
    Get a specific emergency alert.
    """
    try:
        alert = await emergency_crud.get_emergency_alert_by_id(
            session=db,
            alert_id=alert_id,
            user_id=current_user.id
        )
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Emergency alert not found or you don't have permission to view it."
            )
        
        return alert
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting emergency alert: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving the emergency alert."
        )

@router.patch("/alerts/{alert_id}/resolve", response_model=EmergencyAlertResponse)
async def resolve_emergency_alert(
    alert_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> EmergencyAlertResponse:
    """
    Mark an emergency alert as resolved.
    """
    try:
        alert = await emergency_crud.resolve_emergency_alert(
            session=db,
            alert_id=alert_id,
            user_id=current_user.id,
            resolved_by=current_user.id
        )
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Emergency alert not found or you don't have permission to resolve it."
            )
        
        logger.info(f"Emergency alert {alert_id} resolved by user {current_user.id}")
        return alert
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving emergency alert: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resolving the emergency alert."
        )

@router.post("/alerts/{alert_id}/update-location")
async def update_emergency_location(
    alert_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    location_lat: float = Query(..., ge=-90, le=90),
    location_lng: float = Query(..., ge=-180, le=180),
    location_address: Optional[str] = Query(default=None)
) -> dict:
    """
    Update location for an active emergency alert.
    This helps emergency contacts track the user's movement during an emergency.
    """
    try:
        success = await emergency_crud.update_emergency_location(
            session=db,
            alert_id=alert_id,
            user_id=current_user.id,
            location_lat=location_lat,
            location_lng=location_lng,
            location_address=location_address
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Emergency alert not found or cannot update location."
            )
        
        logger.info(f"Emergency location updated for alert {alert_id}")
        return {"message": "Emergency location updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating emergency location: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating emergency location."
        )

@router.post("/quick-sos", response_model=EmergencyAlertResponse)
async def quick_sos_alert(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    location_lat: Optional[float] = Query(default=None, ge=-90, le=90),
    location_lng: Optional[float] = Query(default=None, ge=-180, le=180),
    location_address: Optional[str] = Query(default=None),
    trip_id: Optional[UUID] = Query(default=None)
) -> EmergencyAlertResponse:
    """
    Quick SOS button - immediately creates an emergency alert and notifies contacts.
    This is the main emergency button in the mobile app.
    """
    try:
        alert_data = EmergencyAlertCreate(
            emergency_type="sos",
            description="Emergency SOS alert triggered",
            location_lat=location_lat,
            location_lng=location_lng,
            location_address=location_address,
            trip_id=trip_id
        )
        
        alert = await emergency_crud.create_emergency_alert(
            session=db,
            user_id=current_user.id,
            alert_data=alert_data,
            is_quick_sos=True
        )
        
        logger.info(f"Quick SOS alert triggered by user {current_user.id}")
        return alert
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating quick SOS alert: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the SOS alert."
        )

@router.post("/test-emergency-system")
async def test_emergency_system(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Test the emergency notification system.
    Sends a test notification to all emergency contacts.
    """
    try:
        success = await emergency_crud.test_emergency_notifications(
            session=db,
            user_id=current_user.id
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No emergency contacts found or error testing system."
            )
        
        logger.info(f"Emergency system tested by user {current_user.id}")
        return {"message": "Test notifications sent to all emergency contacts"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing emergency system: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while testing the emergency system."
        )

# --- TRIP SAFETY FEATURES ---

@router.post("/trips/{trip_id}/share-live-location")
async def share_live_location_with_contacts(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Share live location with emergency contacts during a trip.
    This provides real-time tracking for safety.
    """
    try:
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
        logger.error(f"Error sharing live location: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while sharing live location."
        )

@router.post("/trips/{trip_id}/arrived-safely")
async def mark_arrived_safely(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Mark that user has arrived safely.
    This sends confirmation to emergency contacts who were tracking the trip.
    """
    try:
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
        return {"message": "Arrival confirmation sent to emergency contacts"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking trip as safe: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while confirming safe arrival."
        )

# --- ADMIN ENDPOINTS ---

@router.get("/admin/alerts", response_model=List[EmergencyAlertResponse])
async def admin_get_all_emergency_alerts(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    unresolved_only: bool = Query(default=True)
) -> List[EmergencyAlertResponse]:
    """
    Admin endpoint to view all emergency alerts.
    """
    try:
        alerts = await emergency_crud.get_all_emergency_alerts(
            session=db,
            skip=skip,
            limit=limit,
            unresolved_only=unresolved_only
        )
        logger.info(f"Admin {current_admin.id} retrieved {len(alerts)} emergency alerts")
        return alerts
    except Exception as e:
        logger.error(f"Error getting admin emergency alerts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving emergency alerts."
        )

@router.patch("/admin/alerts/{alert_id}/resolve", response_model=EmergencyAlertResponse)
async def admin_resolve_emergency_alert(
    alert_id: UUID,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> EmergencyAlertResponse:
    """
    Admin endpoint to resolve emergency alerts.
    """
    try:
        alert = await emergency_crud.admin_resolve_emergency_alert(
            session=db,
            alert_id=alert_id,
            resolved_by=current_admin.id
        )
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Emergency alert not found."
            )
        
        logger.info(f"Emergency alert {alert_id} resolved by admin {current_admin.id}")
        return alert
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving emergency alert as admin: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resolving the emergency alert."
        )

@router.get("/admin/stats")
async def admin_get_emergency_stats(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get emergency system statistics for admin dashboard.
    """
    try:
        stats = await emergency_crud.get_emergency_stats(
            session=db
        )
        logger.info(f"Emergency stats retrieved by admin {current_admin.id}")
        return stats
    except Exception as e:
        logger.error(f"Error getting emergency stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving emergency statistics."
        )

@router.post("/admin/emergency-broadcast")
async def admin_emergency_broadcast(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    title: str = Query(..., max_length=200),
    message: str = Query(..., max_length=1000)
) -> dict:
    """
    Send emergency broadcast to all active users.
    Used for system-wide emergencies, natural disasters, etc.
    """
    try:
        sent_count = await emergency_crud.send_emergency_broadcast(
            session=db,
            title=title,
            message=message,
            sender_id=current_admin.id
        )
        
        logger.info(f"Emergency broadcast sent to {sent_count} users by admin {current_admin.id}")
        return {
            "message": f"Emergency broadcast sent to {sent_count} users",
            "sent_count": sent_count
        }
    except Exception as e:
        logger.error(f"Error sending emergency broadcast: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while sending emergency broadcast."
        )

@router.get("/admin/active-emergencies")
async def admin_get_active_emergencies(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get count and details of currently active emergencies.
    Critical for admin monitoring dashboard.
    """
    try:
        active_emergencies = await emergency_crud.get_active_emergencies_summary(
            session=db
        )
        logger.info(f"Active emergencies summary retrieved by admin {current_admin.id}")
        return active_emergencies
    except Exception as e:
        logger.error(f"Error getting active emergencies: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving active emergencies."
        )