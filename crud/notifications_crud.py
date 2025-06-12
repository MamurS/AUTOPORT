# File: crud/notifications_crud.py

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update, delete, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError

from models import (
    Notification, User, Trip, Booking, UserSettings, 
    NotificationType, NotificationStatus, UserRole, UserStatus,
    TripStatus, BookingStatus
)

logger = logging.getLogger(__name__)

async def create_notification(
    session: AsyncSession,
    user_id: UUID,
    notification_type: NotificationType,
    title: str,
    content: str,
    data: Optional[Dict[str, Any]] = None,
    scheduled_at: Optional[datetime] = None,
    phone_number: Optional[str] = None,
    push_token: Optional[str] = None
) -> Notification:
    """Create a new notification."""
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
        
        # Get user's notification preferences
        settings_result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        user_settings = settings_result.scalar_one_or_none()
        
        # Check if user allows this type of notification
        if user_settings:
            if (notification_type == NotificationType.SMS and not user_settings.sms_notifications) or \
               (notification_type == NotificationType.PUSH and not user_settings.push_notifications) or \
               (notification_type == NotificationType.EMAIL and not user_settings.email_notifications):
                logger.info(f"Notification blocked by user {user_id} preferences for type {notification_type}")
                return None
        
        # Use user's phone if not provided
        if notification_type == NotificationType.SMS and not phone_number:
            phone_number = user.phone_number
        
        notification = Notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            content=content,
            data=data,
            scheduled_at=scheduled_at,
            phone_number=phone_number,
            push_token=push_token
        )
        
        session.add(notification)
        await session.flush()
        await session.refresh(notification)
        
        logger.info(f"Notification created for user {user_id}, type: {notification_type}")
        return notification
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating notification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating notification."
        )

async def get_user_notifications(
    session: AsyncSession,
    user_id: UUID,
    notification_type: Optional[NotificationType] = None,
    skip: int = 0,
    limit: int = 20
) -> List[Notification]:
    """Get notifications for a user."""
    try:
        query = select(Notification).where(Notification.user_id == user_id)
        
        if notification_type:
            query = query.where(Notification.notification_type == notification_type)
        
        query = query.order_by(desc(Notification.created_at)).offset(skip).limit(limit)
        
        result = await session.execute(query)
        notifications = result.scalars().all()
        
        logger.info(f"Retrieved {len(notifications)} notifications for user {user_id}")
        return notifications
        
    except Exception as e:
        logger.error(f"Error getting user notifications: {e}", exc_info=True)
        return []

async def get_unread_count(
    session: AsyncSession,
    user_id: UUID
) -> int:
    """Get count of unread notifications for a user."""
    try:
        # For notifications, we consider them "unread" if they are sent but not marked as delivered
        # or if they are recent and pending
        result = await session.execute(
            select(func.count(Notification.id))
            .where(
                and_(
                    Notification.user_id == user_id,
                    or_(
                        and_(
                            Notification.status == NotificationStatus.SENT,
                            Notification.delivered_at.is_(None)
                        ),
                        and_(
                            Notification.status == NotificationStatus.PENDING,
                            Notification.created_at >= datetime.utcnow() - timedelta(hours=24)
                        )
                    )
                )
            )
        )
        count = result.scalar() or 0
        logger.info(f"User {user_id} has {count} unread notifications")
        return count
        
    except Exception as e:
        logger.error(f"Error getting unread count: {e}", exc_info=True)
        return 0

async def mark_as_read(
    session: AsyncSession,
    notification_id: UUID,
    user_id: UUID
) -> bool:
    """Mark a notification as read (delivered)."""
    try:
        result = await session.execute(
            select(Notification)
            .where(
                and_(
                    Notification.id == notification_id,
                    Notification.user_id == user_id
                )
            )
        )
        notification = result.scalar_one_or_none()
        
        if not notification:
            return False
        
        # Mark as delivered if not already
        if not notification.delivered_at:
            notification.delivered_at = datetime.utcnow()
            if notification.status == NotificationStatus.SENT:
                notification.status = NotificationStatus.DELIVERED
            
            session.add(notification)
            await session.flush()
        
        logger.info(f"Notification {notification_id} marked as read")
        return True
        
    except Exception as e:
        logger.error(f"Error marking notification as read: {e}", exc_info=True)
        return False

async def mark_all_as_read(
    session: AsyncSession,
    user_id: UUID
) -> int:
    """Mark all notifications as read for a user."""
    try:
        result = await session.execute(
            update(Notification)
            .where(
                and_(
                    Notification.user_id == user_id,
                    Notification.delivered_at.is_(None)
                )
            )
            .values(
                delivered_at=datetime.utcnow(),
                status=NotificationStatus.DELIVERED
            )
        )
        
        marked_count = result.rowcount
        logger.info(f"Marked {marked_count} notifications as read for user {user_id}")
        return marked_count
        
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {e}", exc_info=True)
        return 0

async def delete_notification(
    session: AsyncSession,
    notification_id: UUID,
    user_id: UUID
) -> bool:
    """Delete a notification."""
    try:
        result = await session.execute(
            select(Notification)
            .where(
                and_(
                    Notification.id == notification_id,
                    Notification.user_id == user_id
                )
            )
        )
        notification = result.scalar_one_or_none()
        
        if not notification:
            return False
        
        await session.delete(notification)
        await session.flush()
        
        logger.info(f"Notification {notification_id} deleted")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting notification: {e}", exc_info=True)
        return False

async def update_user_push_token(
    session: AsyncSession,
    user_id: UUID,
    push_token: str
) -> bool:
    """Update user's push notification token."""
    try:
        # For now, we could store this in user settings or a separate table
        # For this implementation, we'll update any pending push notifications
        # In a real implementation, you'd want a separate user_devices table
        
        # Update any pending push notifications for this user
        await session.execute(
            update(Notification)
            .where(
                and_(
                    Notification.user_id == user_id,
                    Notification.notification_type == NotificationType.PUSH,
                    Notification.status == NotificationStatus.PENDING
                )
            )
            .values(push_token=push_token)
        )
        
        logger.info(f"Push token updated for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating push token: {e}", exc_info=True)
        return False

async def queue_for_sending(
    session: AsyncSession,
    notification_id: UUID
) -> bool:
    """Queue a notification for immediate sending."""
    try:
        await session.execute(
            update(Notification)
            .where(Notification.id == notification_id)
            .values(
                scheduled_at=datetime.utcnow(),
                status=NotificationStatus.PENDING
            )
        )
        
        logger.info(f"Notification {notification_id} queued for sending")
        return True
        
    except Exception as e:
        logger.error(f"Error queuing notification: {e}", exc_info=True)
        return False

async def send_trip_reminder(
    session: AsyncSession,
    trip_id: UUID,
    sender_id: UUID
) -> int:
    """Send reminder notifications to all trip participants."""
    try:
        # Verify sender is the driver
        trip_result = await session.execute(
            select(Trip)
            .where(Trip.id == trip_id)
        )
        trip = trip_result.scalar_one_or_none()
        
        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found."
            )
        
        if trip.driver_id != sender_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the driver can send trip reminders."
            )
        
        # Get all confirmed passengers
        bookings_result = await session.execute(
            select(Booking)
            .where(
                and_(
                    Booking.trip_id == trip_id,
                    Booking.status == BookingStatus.CONFIRMED
                )
            )
        )
        bookings = bookings_result.scalars().all()
        
        sent_count = 0
        reminder_content = f"Reminder: Your trip from {trip.from_location_text} to {trip.to_location_text} is scheduled for {trip.departure_datetime.strftime('%B %d at %H:%M')}"
        
        for booking in bookings:
            # Create SMS notification
            sms_notification = await create_notification(
                session=session,
                user_id=booking.passenger_id,
                notification_type=NotificationType.SMS,
                title="Trip Reminder",
                content=reminder_content,
                data={
                    "trip_id": str(trip_id),
                    "booking_id": str(booking.id),
                    "reminder_type": "trip_departure"
                }
            )
            
            if sms_notification:
                await queue_for_sending(session, sms_notification.id)
                sent_count += 1
            
            # Create push notification
            push_notification = await create_notification(
                session=session,
                user_id=booking.passenger_id,
                notification_type=NotificationType.PUSH,
                title="Trip Reminder",
                content=reminder_content,
                data={
                    "trip_id": str(trip_id),
                    "booking_id": str(booking.id),
                    "reminder_type": "trip_departure",
                    "action": "view_trip"
                }
            )
            
            if push_notification:
                await queue_for_sending(session, push_notification.id)
                sent_count += 1
        
        logger.info(f"Trip reminder sent to {len(bookings)} passengers")
        return sent_count
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending trip reminder: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error sending trip reminder."
        )

async def broadcast_notification(
    session: AsyncSession,
    title: str,
    content: str,
    notification_type: NotificationType = NotificationType.PUSH,
    user_role: Optional[str] = None,
    sender_id: Optional[UUID] = None
) -> int:
    """Broadcast notification to all users or specific user types."""
    try:
        # Build user query
        user_query = select(User).where(User.status == UserStatus.ACTIVE)
        
        if user_role:
            if user_role == "passenger":
                user_query = user_query.where(User.role == UserRole.PASSENGER)
            elif user_role == "driver":
                user_query = user_query.where(User.role == UserRole.DRIVER)
            elif user_role == "admin":
                user_query = user_query.where(User.role == UserRole.ADMIN)
        
        users_result = await session.execute(user_query)
        users = users_result.scalars().all()
        
        sent_count = 0
        for user in users:
            notification = await create_notification(
                session=session,
                user_id=user.id,
                notification_type=notification_type,
                title=title,
                content=content,
                data={
                    "broadcast": True,
                    "sender_id": str(sender_id) if sender_id else None,
                    "target_role": user_role
                }
            )
            
            if notification:
                await queue_for_sending(session, notification.id)
                sent_count += 1
        
        logger.info(f"Broadcast notification sent to {sent_count} users")
        return sent_count
        
    except Exception as e:
        logger.error(f"Error broadcasting notification: {e}", exc_info=True)
        return 0

async def get_pending_notifications(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 50
) -> List[Notification]:
    """Get pending notifications for processing."""
    try:
        result = await session.execute(
            select(Notification)
            .options(selectinload(Notification.user))
            .where(
                and_(
                    Notification.status == NotificationStatus.PENDING,
                    or_(
                        Notification.scheduled_at.is_(None),
                        Notification.scheduled_at <= datetime.utcnow()
                    )
                )
            )
            .order_by(Notification.created_at)
            .offset(skip)
            .limit(limit)
        )
        notifications = result.scalars().all()
        
        logger.info(f"Retrieved {len(notifications)} pending notifications")
        return notifications
        
    except Exception as e:
        logger.error(f"Error getting pending notifications: {e}", exc_info=True)
        return []

async def update_notification_status(
    session: AsyncSession,
    notification_id: UUID,
    status: NotificationStatus,
    sent_at: Optional[datetime] = None,
    delivered_at: Optional[datetime] = None
) -> bool:
    """Update notification status after sending attempt."""
    try:
        update_values = {"status": status}
        
        if sent_at:
            update_values["sent_at"] = sent_at
        if delivered_at:
            update_values["delivered_at"] = delivered_at
        
        await session.execute(
            update(Notification)
            .where(Notification.id == notification_id)
            .values(**update_values)
        )
        
        logger.info(f"Notification {notification_id} status updated to {status}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating notification status: {e}", exc_info=True)
        return False

async def get_notification_stats(
    session: AsyncSession
) -> Dict[str, Any]:
    """Get notification delivery statistics."""
    try:
        # Total counts by status
        status_result = await session.execute(
            select(
                Notification.status,
                func.count(Notification.id).label('count')
            )
            .group_by(Notification.status)
        )
        status_stats = {row.status.value: row.count for row in status_result}
        
        # Total counts by type
        type_result = await session.execute(
            select(
                Notification.notification_type,
                func.count(Notification.id).label('count')
            )
            .group_by(Notification.notification_type)
        )
        type_stats = {row.notification_type.value: row.count for row in type_result}
        
        # Recent activity (last 24 hours)
        recent_result = await session.execute(
            select(func.count(Notification.id))
            .where(Notification.created_at >= datetime.utcnow() - timedelta(hours=24))
        )
        recent_count = recent_result.scalar() or 0
        
        # Failed notifications (last 7 days)
        failed_result = await session.execute(
            select(func.count(Notification.id))
            .where(
                and_(
                    Notification.status == NotificationStatus.FAILED,
                    Notification.created_at >= datetime.utcnow() - timedelta(days=7)
                )
            )
        )
        failed_count = failed_result.scalar() or 0
        
        stats = {
            "total_by_status": status_stats,
            "total_by_type": type_stats,
            "last_24_hours": recent_count,
            "failed_last_7_days": failed_count
        }
        
        logger.info("Notification stats retrieved")
        return stats
        
    except Exception as e:
        logger.error(f"Error getting notification stats: {e}", exc_info=True)
        return {}

async def retry_failed_notifications(
    session: AsyncSession,
    hours_back: int = 24
) -> int:
    """Retry failed notifications from the last X hours."""
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        
        result = await session.execute(
            update(Notification)
            .where(
                and_(
                    Notification.status == NotificationStatus.FAILED,
                    Notification.created_at >= cutoff_time
                )
            )
            .values(
                status=NotificationStatus.PENDING,
                scheduled_at=datetime.utcnow()
            )
        )
        
        retry_count = result.rowcount
        logger.info(f"Retried {retry_count} failed notifications")
        return retry_count
        
    except Exception as e:
        logger.error(f"Error retrying failed notifications: {e}", exc_info=True)
        return 0

async def cleanup_old_notifications(
    session: AsyncSession,
    days_old: int = 30
) -> int:
    """Clean up old notifications."""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        result = await session.execute(
            delete(Notification)
            .where(
                and_(
                    Notification.created_at < cutoff_date,
                    Notification.status.in_([
                        NotificationStatus.DELIVERED,
                        NotificationStatus.FAILED
                    ])
                )
            )
        )
        
        deleted_count = result.rowcount
        logger.info(f"Cleaned up {deleted_count} old notifications")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Error cleaning up notifications: {e}", exc_info=True)
        return 0

# --- AUTOMATED NOTIFICATION HELPERS ---

async def send_booking_confirmation(
    session: AsyncSession,
    booking_id: UUID
) -> bool:
    """Send booking confirmation notifications."""
    try:
        # Get booking details
        booking_result = await session.execute(
            select(Booking)
            .options(
                selectinload(Booking.trip).options(
                    selectinload(Trip.driver)
                ),
                selectinload(Booking.passenger)
            )
            .where(Booking.id == booking_id)
        )
        booking = booking_result.scalar_one_or_none()
        
        if not booking:
            return False
        
        trip = booking.trip
        passenger = booking.passenger
        driver = trip.driver
        
        # Send confirmation to passenger
        passenger_content = f"Your booking is confirmed! Trip from {trip.from_location_text} to {trip.to_location_text} on {trip.departure_datetime.strftime('%B %d at %H:%M')}. Driver: {driver.full_name}"
        
        passenger_notification = await create_notification(
            session=session,
            user_id=passenger.id,
            notification_type=NotificationType.SMS,
            title="Booking Confirmed",
            content=passenger_content,
            data={
                "booking_id": str(booking_id),
                "trip_id": str(trip.id),
                "action": "view_booking"
            }
        )
        
        if passenger_notification:
            await queue_for_sending(session, passenger_notification.id)
        
        # Send notification to driver
        driver_content = f"New booking! {passenger.full_name} booked {booking.seats_booked} seat(s) for your trip on {trip.departure_datetime.strftime('%B %d at %H:%M')}"
        
        driver_notification = await create_notification(
            session=session,
            user_id=driver.id,
            notification_type=NotificationType.PUSH,
            title="New Booking",
            content=driver_content,
            data={
                "booking_id": str(booking_id),
                "trip_id": str(trip.id),
                "passenger_id": str(passenger.id),
                "action": "view_trip"
            }
        )
        
        if driver_notification:
            await queue_for_sending(session, driver_notification.id)
        
        logger.info(f"Booking confirmation notifications sent for booking {booking_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending booking confirmation: {e}", exc_info=True)
        return False

async def send_trip_status_update(
    session: AsyncSession,
    trip_id: UUID,
    new_status: TripStatus
) -> int:
    """Send trip status update notifications to all participants."""
    try:
        # Get trip and all confirmed bookings
        trip_result = await session.execute(
            select(Trip)
            .options(selectinload(Trip.driver))
            .where(Trip.id == trip_id)
        )
        trip = trip_result.scalar_one_or_none()
        
        if not trip:
            return 0
        
        bookings_result = await session.execute(
            select(Booking)
            .options(selectinload(Booking.passenger))
            .where(
                and_(
                    Booking.trip_id == trip_id,
                    Booking.status == BookingStatus.CONFIRMED
                )
            )
        )
        bookings = bookings_result.scalars().all()
        
        # Determine notification content based on status
        if new_status == TripStatus.CANCELLED_BY_DRIVER:
            title = "Trip Cancelled"
            content = f"Unfortunately, your trip from {trip.from_location_text} to {trip.to_location_text} scheduled for {trip.departure_datetime.strftime('%B %d at %H:%M')} has been cancelled by the driver."
        elif new_status == TripStatus.IN_PROGRESS:
            title = "Trip Started"
            content = f"Your trip from {trip.from_location_text} to {trip.to_location_text} has started!"
        elif new_status == TripStatus.COMPLETED:
            title = "Trip Completed"
            content = f"Your trip from {trip.from_location_text} to {trip.to_location_text} has been completed. Please rate your experience!"
        else:
            return 0
        
        sent_count = 0
        for booking in bookings:
            notification = await create_notification(
                session=session,
                user_id=booking.passenger_id,
                notification_type=NotificationType.PUSH,
                title=title,
                content=content,
                data={
                    "trip_id": str(trip_id),
                    "booking_id": str(booking.id),
                    "trip_status": new_status.value,
                    "action": "view_trip"
                }
            )
            
            if notification:
                await queue_for_sending(session, notification.id)
                sent_count += 1
        
        logger.info(f"Trip status update notifications sent to {sent_count} passengers")
        return sent_count
        
    except Exception as e:
        logger.error(f"Error sending trip status update: {e}", exc_info=True)
        return 0