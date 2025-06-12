# File: routers/notifications.py

import logging
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_active_user, get_current_admin_user
from crud import notifications_crud
from database import get_db
from models import User, NotificationType
from schemas import (
    NotificationCreate, NotificationResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["notifications"])

@router.get("/", response_model=List[NotificationResponse])
async def get_my_notifications(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    notification_type: Optional[NotificationType] = Query(default=None)
) -> List[NotificationResponse]:
    """
    Get notifications for the current user.
    Can filter by notification type (SMS, PUSH, EMAIL).
    """
    try:
        notifications = await notifications_crud.get_user_notifications(
            session=db,
            user_id=current_user.id,
            notification_type=notification_type,
            skip=skip,
            limit=limit
        )
        logger.info(f"Retrieved {len(notifications)} notifications for user {current_user.id}")
        return notifications
    except Exception as e:
        logger.error(f"Error getting notifications for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving notifications."
        )

@router.get("/unread-count")
async def get_unread_notifications_count(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get count of unread notifications for badge display.
    """
    try:
        count = await notifications_crud.get_unread_count(
            session=db,
            user_id=current_user.id
        )
        return {"unread_count": count}
    except Exception as e:
        logger.error(f"Error getting unread count for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while getting unread notification count."
        )

@router.patch("/{notification_id}/mark-read")
async def mark_notification_as_read(
    notification_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Mark a specific notification as read.
    """
    try:
        success = await notifications_crud.mark_as_read(
            session=db,
            notification_id=notification_id,
            user_id=current_user.id
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found or you don't have access to it."
            )
        
        logger.info(f"Notification {notification_id} marked as read by user {current_user.id}")
        return {"message": "Notification marked as read"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking notification as read: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while marking notification as read."
        )

@router.patch("/mark-all-read")
async def mark_all_notifications_as_read(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Mark all notifications as read for the current user.
    """
    try:
        count = await notifications_crud.mark_all_as_read(
            session=db,
            user_id=current_user.id
        )
        logger.info(f"Marked {count} notifications as read for user {current_user.id}")
        return {"marked_count": count, "message": "All notifications marked as read"}
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while marking notifications as read."
        )

@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Delete a specific notification.
    """
    try:
        success = await notifications_crud.delete_notification(
            session=db,
            notification_id=notification_id,
            user_id=current_user.id
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found or you don't have access to it."
            )
        
        logger.info(f"Notification {notification_id} deleted by user {current_user.id}")
        return {"message": "Notification deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting notification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the notification."
        )

@router.patch("/settings/push-token")
async def update_push_token(
    push_token: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Update the user's push notification token.
    Called when the mobile app gets a new FCM/APN token.
    """
    try:
        success = await notifications_crud.update_user_push_token(
            session=db,
            user_id=current_user.id,
            push_token=push_token
        )
        if success:
            logger.info(f"Push token updated for user {current_user.id}")
            return {"message": "Push token updated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update push token"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating push token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating push token."
        )

@router.post("/send-trip-reminder/{trip_id}")
async def send_trip_reminder(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Send reminder notifications to all trip participants.
    Only the driver can send reminders.
    """
    try:
        sent_count = await notifications_crud.send_trip_reminder(
            session=db,
            trip_id=trip_id,
            sender_id=current_user.id
        )
        
        logger.info(f"Trip reminder sent to {sent_count} participants by user {current_user.id}")
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

@router.post("/test-notification")
async def send_test_notification(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    notification_type: NotificationType = Query(default=NotificationType.PUSH)
) -> dict:
    """
    Send a test notification to the current user.
    Useful for testing notification delivery.
    """
    try:
        notification = await notifications_crud.create_notification(
            session=db,
            user_id=current_user.id,
            notification_type=notification_type,
            title="Test Notification",
            content="This is a test notification from AutoPort.",
            data={"test": True}
        )
        
        # Queue for immediate sending
        await notifications_crud.queue_for_sending(
            session=db,
            notification_id=notification.id
        )
        
        logger.info(f"Test notification sent to user {current_user.id}")
        return {
            "message": "Test notification sent",
            "notification_id": notification.id
        }
    except Exception as e:
        logger.error(f"Error sending test notification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while sending test notification."
        )

# --- ADMIN ENDPOINTS ---

@router.post("/admin/send", response_model=NotificationResponse)
async def admin_send_notification(
    notification_data: NotificationCreate,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> NotificationResponse:
    """
    Admin endpoint to send notifications to specific users.
    """
    try:
        notification = await notifications_crud.create_notification(
            session=db,
            user_id=notification_data.user_id,
            notification_type=notification_data.notification_type,
            title=notification_data.title,
            content=notification_data.content,
            data=notification_data.data,
            scheduled_at=notification_data.scheduled_at
        )
        
        # Queue for sending if not scheduled
        if not notification_data.scheduled_at:
            await notifications_crud.queue_for_sending(
                session=db,
                notification_id=notification.id
            )
        
        logger.info(f"Admin notification sent by {current_admin.id} to user {notification_data.user_id}")
        return notification
    except Exception as e:
        logger.error(f"Error sending admin notification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while sending notification."
        )

@router.post("/admin/broadcast")
async def admin_broadcast_notification(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    title: str = Query(..., max_length=200),
    content: str = Query(..., max_length=1000),
    notification_type: NotificationType = Query(default=NotificationType.PUSH),
    user_role: Optional[str] = Query(default=None, regex="^(passenger|driver|admin)$")
) -> dict:
    """
    Admin endpoint to broadcast notifications to all users or specific user types.
    """
    try:
        sent_count = await notifications_crud.broadcast_notification(
            session=db,
            title=title,
            content=content,
            notification_type=notification_type,
            user_role=user_role,
            sender_id=current_admin.id
        )
        
        logger.info(f"Broadcast notification sent to {sent_count} users by admin {current_admin.id}")
        return {
            "message": f"Broadcast sent to {sent_count} users",
            "sent_count": sent_count
        }
    except Exception as e:
        logger.error(f"Error broadcasting notification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while broadcasting notification."
        )

@router.get("/admin/pending", response_model=List[NotificationResponse])
async def admin_get_pending_notifications(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200)
) -> List[NotificationResponse]:
    """
    Admin endpoint to get pending notifications in the queue.
    """
    try:
        notifications = await notifications_crud.get_pending_notifications(
            session=db,
            skip=skip,
            limit=limit
        )
        logger.info(f"Retrieved {len(notifications)} pending notifications for admin {current_admin.id}")
        return notifications
    except Exception as e:
        logger.error(f"Error getting pending notifications: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving pending notifications."
        )

@router.get("/admin/stats")
async def admin_get_notification_stats(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Admin endpoint to get notification delivery statistics.
    """
    try:
        stats = await notifications_crud.get_notification_stats(
            session=db
        )
        logger.info(f"Notification stats retrieved by admin {current_admin.id}")
        return stats
    except Exception as e:
        logger.error(f"Error getting notification stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving notification statistics."
        )

@router.post("/admin/retry-failed")
async def admin_retry_failed_notifications(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    hours_back: int = Query(default=24, ge=1, le=168)  # Max 1 week
) -> dict:
    """
    Admin endpoint to retry failed notifications from the last X hours.
    """
    try:
        retry_count = await notifications_crud.retry_failed_notifications(
            session=db,
            hours_back=hours_back
        )
        
        logger.info(f"Retried {retry_count} failed notifications by admin {current_admin.id}")
        return {
            "message": f"Retried {retry_count} failed notifications",
            "retry_count": retry_count
        }
    except Exception as e:
        logger.error(f"Error retrying failed notifications: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrying failed notifications."
        )

@router.delete("/admin/cleanup")
async def admin_cleanup_old_notifications(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days_old: int = Query(default=30, ge=7, le=365)
) -> dict:
    """
    Admin endpoint to clean up old notifications.
    """
    try:
        deleted_count = await notifications_crud.cleanup_old_notifications(
            session=db,
            days_old=days_old
        )
        
        logger.info(f"Cleaned up {deleted_count} old notifications by admin {current_admin.id}")
        return {
            "message": f"Cleaned up {deleted_count} old notifications",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"Error cleaning up notifications: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while cleaning up notifications."
        )