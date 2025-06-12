# File: crud/emergency_crud.py

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, update, delete, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError

from models import (
    EmergencyContact, EmergencyAlert, User, Trip, Booking,
    EmergencyType, UserStatus, NotificationType
)
from schemas import (
    EmergencyContactCreate, EmergencyContactUpdate, EmergencyAlertCreate
)
from crud import notifications_crud

logger = logging.getLogger(__name__)

# --- EMERGENCY CONTACTS CRUD ---

async def create_emergency_contact(
    session: AsyncSession,
    user_id: UUID,
    contact_data: EmergencyContactCreate
) -> EmergencyContact:
    """Create a new emergency contact for a user."""
    try:
        # Check if user already has maximum contacts (5)
        existing_count_result = await session.execute(
            select(func.count(EmergencyContact.id))
            .where(EmergencyContact.user_id == user_id)
        )
        existing_count = existing_count_result.scalar() or 0
        
        if existing_count >= 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum of 5 emergency contacts allowed per user."
            )
        
        # Check for duplicate phone numbers for this user
        existing_contact_result = await session.execute(
            select(EmergencyContact)
            .where(
                and_(
                    EmergencyContact.user_id == user_id,
                    EmergencyContact.phone_number == contact_data.phone_number
                )
            )
        )
        existing_contact = existing_contact_result.scalar_one_or_none()
        
        if existing_contact:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Emergency contact with this phone number already exists."
            )
        
        # If this is the first contact or is_primary is True, handle primary logic
        if contact_data.is_primary or existing_count == 0:
            # Unset any existing primary contact
            await session.execute(
                update(EmergencyContact)
                .where(
                    and_(
                        EmergencyContact.user_id == user_id,
                        EmergencyContact.is_primary == True
                    )
                )
                .values(is_primary=False)
            )
            contact_data.is_primary = True
        
        contact = EmergencyContact(
            user_id=user_id,
            name=contact_data.name,
            phone_number=contact_data.phone_number,
            relationship=contact_data.relationship,
            is_primary=contact_data.is_primary
        )
        
        session.add(contact)
        await session.flush()
        await session.refresh(contact)
        
        logger.info(f"Emergency contact created for user {user_id}: {contact_data.name}")
        return contact
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating emergency contact: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating emergency contact."
        )

async def get_user_emergency_contacts(
    session: AsyncSession,
    user_id: UUID
) -> List[EmergencyContact]:
    """Get all emergency contacts for a user."""
    try:
        result = await session.execute(
            select(EmergencyContact)
            .where(EmergencyContact.user_id == user_id)
            .order_by(desc(EmergencyContact.is_primary), EmergencyContact.name)
        )
        contacts = result.scalars().all()
        logger.info(f"Retrieved {len(contacts)} emergency contacts for user {user_id}")
        return contacts
    except Exception as e:
        logger.error(f"Error getting emergency contacts: {e}", exc_info=True)
        return []

async def update_emergency_contact(
    session: AsyncSession,
    contact_id: UUID,
    user_id: UUID,
    contact_data: EmergencyContactUpdate
) -> Optional[EmergencyContact]:
    """Update an emergency contact."""
    try:
        result = await session.execute(
            select(EmergencyContact)
            .where(
                and_(
                    EmergencyContact.id == contact_id,
                    EmergencyContact.user_id == user_id
                )
            )
        )
        contact = result.scalar_one_or_none()
        
        if not contact:
            return None
        
        # Check for duplicate phone number if phone is being updated
        update_data = contact_data.model_dump(exclude_unset=True)
        if "phone_number" in update_data and update_data["phone_number"] != contact.phone_number:
            existing_result = await session.execute(
                select(EmergencyContact)
                .where(
                    and_(
                        EmergencyContact.user_id == user_id,
                        EmergencyContact.phone_number == update_data["phone_number"],
                        EmergencyContact.id != contact_id
                    )
                )
            )
            if existing_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Emergency contact with this phone number already exists."
                )
        
        # Handle primary contact logic
        if "is_primary" in update_data and update_data["is_primary"]:
            # Unset other primary contacts
            await session.execute(
                update(EmergencyContact)
                .where(
                    and_(
                        EmergencyContact.user_id == user_id,
                        EmergencyContact.id != contact_id,
                        EmergencyContact.is_primary == True
                    )
                )
                .values(is_primary=False)
            )
        
        # Apply updates
        for field, value in update_data.items():
            setattr(contact, field, value)
        
        session.add(contact)
        await session.flush()
        await session.refresh(contact)
        
        logger.info(f"Emergency contact {contact_id} updated for user {user_id}")
        return contact
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating emergency contact: {e}", exc_info=True)
        return None

async def delete_emergency_contact(
    session: AsyncSession,
    contact_id: UUID,
    user_id: UUID
) -> bool:
    """Delete an emergency contact."""
    try:
        result = await session.execute(
            select(EmergencyContact)
            .where(
                and_(
                    EmergencyContact.id == contact_id,
                    EmergencyContact.user_id == user_id
                )
            )
        )
        contact = result.scalar_one_or_none()
        
        if not contact:
            return False
        
        was_primary = contact.is_primary
        await session.delete(contact)
        await session.flush()
        
        # If we deleted the primary contact, make another one primary
        if was_primary:
            remaining_result = await session.execute(
                select(EmergencyContact)
                .where(EmergencyContact.user_id == user_id)
                .order_by(EmergencyContact.created_at)
                .limit(1)
            )
            remaining_contact = remaining_result.scalar_one_or_none()
            if remaining_contact:
                remaining_contact.is_primary = True
                session.add(remaining_contact)
                await session.flush()
        
        logger.info(f"Emergency contact {contact_id} deleted for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting emergency contact: {e}", exc_info=True)
        return False

async def set_primary_emergency_contact(
    session: AsyncSession,
    contact_id: UUID,
    user_id: UUID
) -> Optional[EmergencyContact]:
    """Set an emergency contact as primary."""
    try:
        result = await session.execute(
            select(EmergencyContact)
            .where(
                and_(
                    EmergencyContact.id == contact_id,
                    EmergencyContact.user_id == user_id
                )
            )
        )
        contact = result.scalar_one_or_none()
        
        if not contact:
            return None
        
        # Unset all other primary contacts for this user
        await session.execute(
            update(EmergencyContact)
            .where(
                and_(
                    EmergencyContact.user_id == user_id,
                    EmergencyContact.id != contact_id
                )
            )
            .values(is_primary=False)
        )
        
        # Set this contact as primary
        contact.is_primary = True
        session.add(contact)
        await session.flush()
        await session.refresh(contact)
        
        logger.info(f"Emergency contact {contact_id} set as primary for user {user_id}")
        return contact
        
    except Exception as e:
        logger.error(f"Error setting primary emergency contact: {e}", exc_info=True)
        return None

# --- EMERGENCY ALERTS CRUD ---

async def create_emergency_alert(
    session: AsyncSession,
    user_id: UUID,
    alert_data: EmergencyAlertCreate,
    is_quick_sos: bool = False
) -> EmergencyAlert:
    """Create an emergency alert and notify emergency contacts."""
    try:
        # Verify user exists
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found."
            )
        
        # Verify trip exists if trip_id provided
        if alert_data.trip_id:
            trip_result = await session.execute(
                select(Trip).where(Trip.id == alert_data.trip_id)
            )
            trip = trip_result.scalar_one_or_none()
            if not trip:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Trip not found."
                )
        
        alert = EmergencyAlert(
            user_id=user_id,
            trip_id=alert_data.trip_id,
            emergency_type=alert_data.emergency_type,
            description=alert_data.description,
            location_lat=alert_data.location_lat,
            location_lng=alert_data.location_lng,
            location_address=alert_data.location_address
        )
        
        session.add(alert)
        await session.flush()
        await session.refresh(alert)
        
        # Notify emergency contacts immediately
        await notify_emergency_contacts(
            session=session,
            user_id=user_id,
            alert=alert,
            is_quick_sos=is_quick_sos
        )
        
        # Notify admins for serious emergencies
        if alert.emergency_type in [EmergencyType.SOS, EmergencyType.HARASSMENT]:
            await notify_admins_of_emergency(
                session=session,
                alert=alert,
                user=user
            )
        
        logger.info(f"Emergency alert {alert.id} created for user {user_id}, type: {alert.emergency_type}")
        return alert
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating emergency alert: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating emergency alert."
        )

async def notify_emergency_contacts(
    session: AsyncSession,
    user_id: UUID,
    alert: EmergencyAlert,
    is_quick_sos: bool = False
):
    """Send notifications to all emergency contacts."""
    try:
        # Get user's emergency contacts
        contacts_result = await session.execute(
            select(EmergencyContact)
            .where(EmergencyContact.user_id == user_id)
            .order_by(desc(EmergencyContact.is_primary))
        )
        contacts = contacts_result.scalars().all()
        
        if not contacts:
            logger.warning(f"No emergency contacts found for user {user_id}")
            return
        
        # Get user details
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one()
        
        # Create emergency notification message
        if is_quick_sos:
            title = "🚨 EMERGENCY SOS ALERT"
            message = f"URGENT: {user.full_name} has triggered an emergency SOS alert!"
        else:
            title = f"🚨 Emergency Alert - {alert.emergency_type.value.title()}"
            message = f"Emergency Alert: {user.full_name} has reported a {alert.emergency_type.value}."
        
        if alert.description:
            message += f" Details: {alert.description}"
        
        if alert.location_address:
            message += f" Location: {alert.location_address}"
        elif alert.location_lat and alert.location_lng:
            message += f" Coordinates: {alert.location_lat}, {alert.location_lng}"
        
        message += f" Time: {alert.created_at.strftime('%H:%M on %B %d, %Y')}"
        
        # Send SMS to all emergency contacts
        for contact in contacts:
            # Create SMS notification
            notification = await notifications_crud.create_notification(
                session=session,
                user_id=user_id,  # This is a bit unusual - we're creating notifications for the emergency user
                notification_type=NotificationType.SMS,
                title=title,
                content=message,
                phone_number=contact.phone_number,
                data={
                    "emergency_alert_id": str(alert.id),
                    "emergency_type": alert.emergency_type.value,
                    "contact_name": contact.name,
                    "contact_relationship": contact.relationship,
                    "is_primary_contact": contact.is_primary,
                    "location_lat": float(alert.location_lat) if alert.location_lat else None,
                    "location_lng": float(alert.location_lng) if alert.location_lng else None
                }
            )
            
            if notification:
                await notifications_crud.queue_for_sending(session, notification.id)
        
        logger.info(f"Emergency notifications sent to {len(contacts)} contacts for alert {alert.id}")
        
    except Exception as e:
        logger.error(f"Error notifying emergency contacts: {e}", exc_info=True)

async def notify_admins_of_emergency(
    session: AsyncSession,
    alert: EmergencyAlert,
    user: User
):
    """Notify admins of serious emergencies."""
    try:
        # Get all admin users
        admins_result = await session.execute(
            select(User)
            .where(
                and_(
                    User.role == "admin",
                    User.status == UserStatus.ACTIVE
                )
            )
        )
        admins = admins_result.scalars().all()
        
        title = f"🚨 Admin Alert - {alert.emergency_type.value.upper()}"
        message = f"URGENT: User {user.full_name} ({user.phone_number}) has triggered a {alert.emergency_type.value} emergency alert."
        
        if alert.description:
            message += f" Details: {alert.description}"
        
        if alert.location_address:
            message += f" Location: {alert.location_address}"
        
        message += f" Alert ID: {alert.id}"
        
        for admin in admins:
            notification = await notifications_crud.create_notification(
                session=session,
                user_id=admin.id,
                notification_type=NotificationType.PUSH,
                title=title,
                content=message,
                data={
                    "emergency_alert_id": str(alert.id),
                    "emergency_user_id": str(user.id),
                    "emergency_type": alert.emergency_type.value,
                    "requires_admin_action": True,
                    "action": "view_emergency"
                }
            )
            
            if notification:
                await notifications_crud.queue_for_sending(session, notification.id)
        
        logger.info(f"Admin notifications sent for emergency alert {alert.id}")
        
    except Exception as e:
        logger.error(f"Error notifying admins of emergency: {e}", exc_info=True)

async def get_user_emergency_alerts(
    session: AsyncSession,
    user_id: UUID,
    skip: int = 0,
    limit: int = 20
) -> List[EmergencyAlert]:
    """Get emergency alerts for a user."""
    try:
        result = await session.execute(
            select(EmergencyAlert)
            .where(EmergencyAlert.user_id == user_id)
            .order_by(desc(EmergencyAlert.created_at))
            .offset(skip)
            .limit(limit)
        )
        alerts = result.scalars().all()
        logger.info(f"Retrieved {len(alerts)} emergency alerts for user {user_id}")
        return alerts
    except Exception as e:
        logger.error(f"Error getting user emergency alerts: {e}", exc_info=True)
        return []

async def get_emergency_alert_by_id(
    session: AsyncSession,
    alert_id: UUID,
    user_id: UUID
) -> Optional[EmergencyAlert]:
    """Get a specific emergency alert by ID."""
    try:
        result = await session.execute(
            select(EmergencyAlert)
            .where(
                and_(
                    EmergencyAlert.id == alert_id,
                    EmergencyAlert.user_id == user_id
                )
            )
        )
        alert = result.scalar_one_or_none()
        if alert:
            logger.info(f"Retrieved emergency alert {alert_id} for user {user_id}")
        return alert
    except Exception as e:
        logger.error(f"Error getting emergency alert: {e}", exc_info=True)
        return None

async def resolve_emergency_alert(
    session: AsyncSession,
    alert_id: UUID,
    user_id: UUID,
    resolved_by: UUID
) -> Optional[EmergencyAlert]:
    """Resolve an emergency alert."""
    try:
        result = await session.execute(
            select(EmergencyAlert)
            .where(
                and_(
                    EmergencyAlert.id == alert_id,
                    EmergencyAlert.user_id == user_id,
                    EmergencyAlert.is_resolved == False
                )
            )
        )
        alert = result.scalar_one_or_none()
        
        if not alert:
            return None
        
        alert.is_resolved = True
        alert.resolved_at = datetime.utcnow()
        alert.resolved_by = resolved_by
        
        session.add(alert)
        await session.flush()
        await session.refresh(alert)
        
        # Notify emergency contacts that the situation is resolved
        await notify_emergency_resolution(
            session=session,
            alert=alert,
            user_id=user_id
        )
        
        logger.info(f"Emergency alert {alert_id} resolved by user {resolved_by}")
        return alert
        
    except Exception as e:
        logger.error(f"Error resolving emergency alert: {e}", exc_info=True)
        return None

async def notify_emergency_resolution(
    session: AsyncSession,
    alert: EmergencyAlert,
    user_id: UUID
):
    """Notify emergency contacts that situation is resolved."""
    try:
        # Get user and emergency contacts
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one()
        
        contacts_result = await session.execute(
            select(EmergencyContact)
            .where(EmergencyContact.user_id == user_id)
        )
        contacts = contacts_result.scalars().all()
        
        title = "✅ Emergency Resolved"
        message = f"Good news! {user.full_name}'s emergency situation has been resolved safely. Time: {alert.resolved_at.strftime('%H:%M on %B %d, %Y')}"
        
        for contact in contacts:
            notification = await notifications_crud.create_notification(
                session=session,
                user_id=user_id,
                notification_type=NotificationType.SMS,
                title=title,
                content=message,
                phone_number=contact.phone_number,
                data={
                    "emergency_alert_id": str(alert.id),
                    "resolution_status": "resolved",
                    "resolved_at": alert.resolved_at.isoformat()
                }
            )
            
            if notification:
                await notifications_crud.queue_for_sending(session, notification.id)
        
        logger.info(f"Resolution notifications sent for emergency alert {alert.id}")
        
    except Exception as e:
        logger.error(f"Error notifying emergency resolution: {e}", exc_info=True)

async def update_emergency_location(
    session: AsyncSession,
    alert_id: UUID,
    user_id: UUID,
    location_lat: float,
    location_lng: float,
    location_address: Optional[str] = None
) -> bool:
    """Update location for an active emergency alert."""
    try:
        result = await session.execute(
            select(EmergencyAlert)
            .where(
                and_(
                    EmergencyAlert.id == alert_id,
                    EmergencyAlert.user_id == user_id,
                    EmergencyAlert.is_resolved == False
                )
            )
        )
        alert = result.scalar_one_or_none()
        
        if not alert:
            return False
        
        alert.location_lat = Decimal(str(location_lat))
        alert.location_lng = Decimal(str(location_lng))
        if location_address:
            alert.location_address = location_address
        
        session.add(alert)
        await session.flush()
        
        # Notify emergency contacts of location update
        await notify_location_update(
            session=session,
            alert=alert,
            user_id=user_id
        )
        
        logger.info(f"Emergency location updated for alert {alert_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating emergency location: {e}", exc_info=True)
        return False

async def notify_location_update(
    session: AsyncSession,
    alert: EmergencyAlert,
    user_id: UUID
):
    """Notify emergency contacts of location update."""
    try:
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one()
        
        contacts_result = await session.execute(
            select(EmergencyContact)
            .where(
                and_(
                    EmergencyContact.user_id == user_id,
                    EmergencyContact.is_primary == True
                )
            )
        )
        primary_contact = contacts_result.scalar_one_or_none()
        
        # Only notify primary contact to avoid spam
        if primary_contact:
            title = "📍 Location Update"
            message = f"Location update for {user.full_name}'s emergency:"
            
            if alert.location_address:
                message += f" {alert.location_address}"
            else:
                message += f" Coordinates: {alert.location_lat}, {alert.location_lng}"
            
            notification = await notifications_crud.create_notification(
                session=session,
                user_id=user_id,
                notification_type=NotificationType.SMS,
                title=title,
                content=message,
                phone_number=primary_contact.phone_number,
                data={
                    "emergency_alert_id": str(alert.id),
                    "location_update": True,
                    "location_lat": float(alert.location_lat),
                    "location_lng": float(alert.location_lng)
                }
            )
            
            if notification:
                await notifications_crud.queue_for_sending(session, notification.id)
        
        logger.info(f"Location update notification sent for alert {alert.id}")
        
    except Exception as e:
        logger.error(f"Error notifying location update: {e}", exc_info=True)

# --- TRIP SAFETY FEATURES ---

async def share_trip_location(
    session: AsyncSession,
    trip_id: UUID,
    user_id: UUID
) -> bool:
    """Share live trip location with emergency contacts."""
    try:
        # Verify trip access
        trip_result = await session.execute(
            select(Trip)
            .options(selectinload(Trip.driver))
            .where(Trip.id == trip_id)
        )
        trip = trip_result.scalar_one_or_none()
        
        if not trip:
            return False
        
        # Check if user is involved in this trip
        is_driver = trip.driver_id == user_id
        is_passenger = False
        
        if not is_driver:
            booking_result = await session.execute(
                select(Booking)
                .where(
                    and_(
                        Booking.trip_id == trip_id,
                        Booking.passenger_id == user_id
                    )
                )
            )
            is_passenger = booking_result.scalar_one_or_none() is not None
        
        if not (is_driver or is_passenger):
            return False
        
        # Get emergency contacts
        contacts_result = await session.execute(
            select(EmergencyContact)
            .where(EmergencyContact.user_id == user_id)
        )
        contacts = contacts_result.scalars().all()
        
        if not contacts:
            return False
        
        # Get user details
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one()
        
        title = "🚗 Trip Location Sharing"
        message = f"{user.full_name} has started sharing their live location for a trip from {trip.from_location_text} to {trip.to_location_text}. Departure: {trip.departure_datetime.strftime('%H:%M on %B %d')}"
        
        for contact in contacts:
            notification = await notifications_crud.create_notification(
                session=session,
                user_id=user_id,
                notification_type=NotificationType.SMS,
                title=title,
                content=message,
                phone_number=contact.phone_number,
                data={
                    "trip_id": str(trip_id),
                    "trip_sharing": True,
                    "trip_from": trip.from_location_text,
                    "trip_to": trip.to_location_text,
                    "departure_time": trip.departure_datetime.isoformat()
                }
            )
            
            if notification:
                await notifications_crud.queue_for_sending(session, notification.id)
        
        logger.info(f"Trip location sharing initiated for trip {trip_id} by user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error sharing trip location: {e}", exc_info=True)
        return False

async def mark_trip_completed_safely(
    session: AsyncSession,
    trip_id: UUID,
    user_id: UUID
) -> bool:
    """Mark trip as completed safely and notify emergency contacts."""
    try:
        # Get trip and user details
        trip_result = await session.execute(
            select(Trip).where(Trip.id == trip_id)
        )
        trip = trip_result.scalar_one_or_none()
        
        if not trip:
            return False
        
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one()
        
        # Get emergency contacts
        contacts_result = await session.execute(
            select(EmergencyContact)
            .where(EmergencyContact.user_id == user_id)
        )
        contacts = contacts_result.scalars().all()
        
        title = "✅ Safe Arrival"
        message = f"{user.full_name} has arrived safely at {trip.to_location_text}. Trip completed at {datetime.utcnow().strftime('%H:%M on %B %d, %Y')}"
        
        for contact in contacts:
            notification = await notifications_crud.create_notification(
                session=session,
                user_id=user_id,
                notification_type=NotificationType.SMS,
                title=title,
                content=message,
                phone_number=contact.phone_number,
                data={
                    "trip_id": str(trip_id),
                    "safe_arrival": True,
                    "arrival_time": datetime.utcnow().isoformat()
                }
            )
            
            if notification:
                await notifications_crud.queue_for_sending(session, notification.id)
        
        logger.info(f"Safe arrival notification sent for trip {trip_id} by user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error marking trip as safely completed: {e}", exc_info=True)
        return False

async def test_emergency_notifications(
    session: AsyncSession,
    user_id: UUID
) -> bool:
    """Send test notifications to emergency contacts."""
    try:
        contacts_result = await session.execute(
            select(EmergencyContact)
            .where(EmergencyContact.user_id == user_id)
        )
        contacts = contacts_result.scalars().all()
        
        if not contacts:
            return False
        
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one()
        
        title = "🔔 Emergency System Test"
        message = f"This is a test message from {user.full_name}'s AutoPort emergency system. If you receive this, the emergency notification system is working correctly."
        
        for contact in contacts:
            notification = await notifications_crud.create_notification(
                session=session,
                user_id=user_id,
                notification_type=NotificationType.SMS,
                title=title,
                content=message,
                phone_number=contact.phone_number,
                data={
                    "test_notification": True,
                    "contact_name": contact.name
                }
            )
            
            if notification:
                await notifications_crud.queue_for_sending(session, notification.id)
        
        logger.info(f"Test emergency notifications sent for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error testing emergency notifications: {e}", exc_info=True)
        return False

# --- ADMIN EMERGENCY MANAGEMENT ---

async def get_all_emergency_alerts(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    unresolved_only: bool = True
) -> List[EmergencyAlert]:
    """Get all emergency alerts for admin monitoring."""
    try:
        query = select(EmergencyAlert).options(
            selectinload(EmergencyAlert.user),
            selectinload(EmergencyAlert.trip)
        )
        
        if unresolved_only:
            query = query.where(EmergencyAlert.is_resolved == False)
        
        query = query.order_by(desc(EmergencyAlert.created_at)).offset(skip).limit(limit)
        
        result = await session.execute(query)
        alerts = result.scalars().all()
        
        logger.info(f"Retrieved {len(alerts)} emergency alerts for admin")
        return alerts
        
    except Exception as e:
        logger.error(f"Error getting admin emergency alerts: {e}", exc_info=True)
        return []

async def admin_resolve_emergency_alert(
    session: AsyncSession,
    alert_id: UUID,
    resolved_by: UUID
) -> Optional[EmergencyAlert]:
    """Admin resolve emergency alert."""
    try:
        result = await session.execute(
            select(EmergencyAlert)
            .where(
                and_(
                    EmergencyAlert.id == alert_id,
                    EmergencyAlert.is_resolved == False
                )
            )
        )
        alert = result.scalar_one_or_none()
        
        if not alert:
            return None
        
        alert.is_resolved = True
        alert.resolved_at = datetime.utcnow()
        alert.resolved_by = resolved_by
        
        session.add(alert)
        await session.flush()
        await session.refresh(alert)
        
        # Notify emergency contacts of admin resolution
        await notify_admin_resolution(
            session=session,
            alert=alert
        )
        
        logger.info(f"Emergency alert {alert_id} resolved by admin {resolved_by}")
        return alert
        
    except Exception as e:
        logger.error(f"Error admin resolving emergency alert: {e}", exc_info=True)
        return None

async def notify_admin_resolution(
    session: AsyncSession,
    alert: EmergencyAlert
):
    """Notify emergency contacts that admin resolved the situation."""
    try:
        user_result = await session.execute(
            select(User).where(User.id == alert.user_id)
        )
        user = user_result.scalar_one()
        
        contacts_result = await session.execute(
            select(EmergencyContact)
            .where(EmergencyContact.user_id == alert.user_id)
        )
        contacts = contacts_result.scalars().all()
        
        title = "🛡️ Emergency Resolved by Support"
        message = f"AutoPort support has resolved {user.full_name}'s emergency situation. Time: {alert.resolved_at.strftime('%H:%M on %B %d, %Y')}"
        
        for contact in contacts:
            notification = await notifications_crud.create_notification(
                session=session,
                user_id=alert.user_id,
                notification_type=NotificationType.SMS,
                title=title,
                content=message,
                phone_number=contact.phone_number,
                data={
                    "emergency_alert_id": str(alert.id),
                    "admin_resolved": True,
                    "resolved_at": alert.resolved_at.isoformat()
                }
            )
            
            if notification:
                await notifications_crud.queue_for_sending(session, notification.id)
        
        logger.info(f"Admin resolution notifications sent for alert {alert.id}")
        
    except Exception as e:
        logger.error(f"Error notifying admin resolution: {e}", exc_info=True)

async def get_emergency_stats(
    session: AsyncSession
) -> Dict[str, Any]:
    """Get emergency system statistics."""
    try:
        # Total alerts by type
        type_stats_result = await session.execute(
            select(
                EmergencyAlert.emergency_type,
                func.count(EmergencyAlert.id).label('count')
            )
            .group_by(EmergencyAlert.emergency_type)
        )
        type_stats = {row.emergency_type.value: row.count for row in type_stats_result}
        
        # Alerts in last 24 hours
        recent_result = await session.execute(
            select(func.count(EmergencyAlert.id))
            .where(EmergencyAlert.created_at >= datetime.utcnow() - timedelta(hours=24))
        )
        recent_count = recent_result.scalar() or 0
        
        # Unresolved alerts
        unresolved_result = await session.execute(
            select(func.count(EmergencyAlert.id))
            .where(EmergencyAlert.is_resolved == False)
        )
        unresolved_count = unresolved_result.scalar() or 0
        
        # Average resolution time (for resolved alerts)
        resolution_result = await session.execute(
            select(
                func.avg(
                    func.extract('epoch', EmergencyAlert.resolved_at - EmergencyAlert.created_at)
                ).label('avg_resolution_seconds')
            )
            .where(EmergencyAlert.is_resolved == True)
        )
        avg_resolution_seconds = resolution_result.scalar() or 0
        avg_resolution_minutes = avg_resolution_seconds / 60 if avg_resolution_seconds else 0
        
        # Users with emergency contacts
        users_with_contacts_result = await session.execute(
            select(func.count(func.distinct(EmergencyContact.user_id)))
        )
        users_with_contacts = users_with_contacts_result.scalar() or 0
        
        stats = {
            "total_by_type": type_stats,
            "last_24_hours": recent_count,
            "unresolved_alerts": unresolved_count,
            "average_resolution_minutes": round(avg_resolution_minutes, 2),
            "users_with_emergency_contacts": users_with_contacts
        }
        
        logger.info("Emergency stats retrieved")
        return stats
        
    except Exception as e:
        logger.error(f"Error getting emergency stats: {e}", exc_info=True)
        return {}

async def send_emergency_broadcast(
    session: AsyncSession,
    title: str,
    message: str,
    sender_id: UUID
) -> int:
    """Send emergency broadcast to all active users."""
    try:
        # Use the notification broadcast system
        sent_count = await notifications_crud.broadcast_notification(
            session=session,
            title=title,
            content=message,
            notification_type=NotificationType.SMS,
            sender_id=sender_id
        )
        
        # Also send as push notification
        push_count = await notifications_crud.broadcast_notification(
            session=session,
            title=title,
            content=message,
            notification_type=NotificationType.PUSH,
            sender_id=sender_id
        )
        
        total_sent = sent_count + push_count
        logger.info(f"Emergency broadcast sent to {total_sent} notifications")
        return total_sent
        
    except Exception as e:
        logger.error(f"Error sending emergency broadcast: {e}", exc_info=True)
        return 0

async def get_active_emergencies_summary(
    session: AsyncSession
) -> Dict[str, Any]:
    """Get summary of currently active emergencies."""
    try:
        # Get unresolved alerts by type
        active_by_type_result = await session.execute(
            select(
                EmergencyAlert.emergency_type,
                func.count(EmergencyAlert.id).label('count')
            )
            .where(EmergencyAlert.is_resolved == False)
            .group_by(EmergencyAlert.emergency_type)
        )
        active_by_type = {row.emergency_type.value: row.count for row in active_by_type_result}
        
        # Get critical alerts (SOS and harassment)
        critical_result = await session.execute(
            select(func.count(EmergencyAlert.id))
            .where(
                and_(
                    EmergencyAlert.is_resolved == False,
                    EmergencyAlert.emergency_type.in_([EmergencyType.SOS, EmergencyType.HARASSMENT])
                )
            )
        )
        critical_count = critical_result.scalar() or 0
        
        # Get recent alerts (last 4 hours)
        recent_critical_result = await session.execute(
            select(EmergencyAlert)
            .options(selectinload(EmergencyAlert.user))
            .where(
                and_(
                    EmergencyAlert.is_resolved == False,
                    EmergencyAlert.emergency_type.in_([EmergencyType.SOS, EmergencyType.HARASSMENT]),
                    EmergencyAlert.created_at >= datetime.utcnow() - timedelta(hours=4)
                )
            )
            .order_by(desc(EmergencyAlert.created_at))
            .limit(10)
        )
        recent_critical = recent_critical_result.scalars().all()
        
        summary = {
            "total_active": sum(active_by_type.values()),
            "active_by_type": active_by_type,
            "critical_alerts": critical_count,
            "recent_critical_alerts": [
                {
                    "id": str(alert.id),
                    "user_name": alert.user.full_name,
                    "type": alert.emergency_type.value,
                    "created_at": alert.created_at.isoformat(),
                    "location": alert.location_address or "No address provided"
                }
                for alert in recent_critical
            ]
        }
        
        logger.info("Active emergencies summary retrieved")
        return summary
        
    except Exception as e:
        logger.error(f"Error getting active emergencies summary: {e}", exc_info=True)
        return {}