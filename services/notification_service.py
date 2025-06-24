# File: services/notification_service.py (Production Notification Service)

import asyncio
import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from models import Notification, NotificationType, NotificationStatus
from services.sms_service import sms_service
from services.email_service import email_service
from config import settings

logger = logging.getLogger(__name__)

class NotificationService:
    """Production notification service that handles SMS and email delivery"""
    
    def __init__(self):
        self.sms_service = sms_service
        self.email_service = email_service
        
    async def process_notification(
        self, 
        session: AsyncSession, 
        notification_id: str
    ) -> Dict[str, Any]:
        """
        Process a single notification by sending it via the appropriate channel
        
        Args:
            session: Database session
            notification_id: ID of notification to process
            
        Returns:
            Dict with processing result
        """
        try:
            # Get notification from database
            result = await session.execute(
                select(Notification).where(Notification.id == notification_id)
            )
            notification = result.scalar_one_or_none()
            
            if not notification:
                return {
                    "success": False,
                    "error": f"Notification {notification_id} not found"
                }
            
            # Skip if already sent or being processed
            if notification.status != NotificationStatus.PENDING:
                return {
                    "success": False,
                    "error": f"Notification {notification_id} already processed"
                }
            
            # Mark as being processed
            await session.execute(
                update(Notification)
                .where(Notification.id == notification_id)
                .values(status=NotificationStatus.PENDING)
            )
            await session.commit()
            
            # Process based on notification type
            if notification.notification_type == NotificationType.SMS:
                result = await self._send_sms_notification(session, notification)
            elif notification.notification_type == NotificationType.EMAIL:
                result = await self._send_email_notification(session, notification)
            elif notification.notification_type == NotificationType.PUSH:
                result = await self._send_push_notification(session, notification)
            else:
                result = {
                    "success": False,
                    "error": f"Unsupported notification type: {notification.notification_type}"
                }
            
            # Update notification status based on result
            if result["success"]:
                await session.execute(
                    update(Notification)
                    .where(Notification.id == notification_id)
                    .values(
                        status=NotificationStatus.SENT,
                        sent_at=asyncio.get_event_loop().time()
                    )
                )
            else:
                await session.execute(
                    update(Notification)
                    .where(Notification.id == notification_id)
                    .values(status=NotificationStatus.FAILED)
                )
            
            await session.commit()
            return result
            
        except Exception as e:
            logger.error(f"Error processing notification {notification_id}: {e}", exc_info=True)
            
            # Mark as failed
            try:
                await session.execute(
                    update(Notification)
                    .where(Notification.id == notification_id)
                    .values(status=NotificationStatus.FAILED)
                )
                await session.commit()
            except:
                pass
            
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _send_sms_notification(
        self, 
        session: AsyncSession, 
        notification: Notification
    ) -> Dict[str, Any]:
        """Send SMS notification using SMS service"""
        try:
            phone_number = notification.phone_number
            if not phone_number:
                return {
                    "success": False,
                    "error": "No phone number provided for SMS notification"
                }
            
            # Format message
            message = f"{notification.title}\n\n{notification.content}"
            
            # Send SMS
            result = await self.sms_service.send_sms(phone_number, message)
            
            if result["success"]:
                logger.info(f"SMS notification sent successfully to {phone_number}")
            else:
                logger.error(f"SMS notification failed: {result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending SMS notification: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _send_email_notification(
        self, 
        session: AsyncSession, 
        notification: Notification
    ) -> Dict[str, Any]:
        """Send email notification using email service"""
        try:
            # For email notifications, we need to get the user's email
            # This is a simplified implementation - you might want to store email in the notification
            user_result = await session.execute(
                select(notification.user).where(notification.user.id == notification.user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user or not user.email:
                return {
                    "success": False,
                    "error": "No email address available for user"
                }
            
            # Create HTML content
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>{notification.title}</title>
            </head>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2c3e50;">{notification.title}</h2>
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 5px;">
                        {notification.content.replace('\n', '<br>')}
                    </div>
                    <hr style="margin: 30px 0;">
                    <p style="color: #666; font-size: 12px;">
                        This is an automated message from AutoPort.<br>
                        Please do not reply to this email.
                    </p>
                </div>
            </body>
            </html>
            """
            
            # Send email
            result = await self.email_service.send_email(
                to_email=user.email,
                subject=notification.title,
                html_content=html_content,
                text_content=notification.content
            )
            
            if result["success"]:
                logger.info(f"Email notification sent successfully to {user.email}")
            else:
                logger.error(f"Email notification failed: {result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending email notification: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _send_push_notification(
        self, 
        session: AsyncSession, 
        notification: Notification
    ) -> Dict[str, Any]:
        """Send push notification (placeholder for FCM implementation)"""
        try:
            # TODO: Implement FCM push notification sending
            # For now, log that push notifications are not implemented
            logger.warning(f"Push notification not implemented for notification {notification.id}")
            
            return {
                "success": False,
                "error": "Push notifications not yet implemented"
            }
            
        except Exception as e:
            logger.error(f"Error sending push notification: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def process_pending_notifications(
        self, 
        session: AsyncSession, 
        batch_size: int = 100
    ) -> Dict[str, Any]:
        """
        Process all pending notifications in batches
        
        Args:
            session: Database session
            batch_size: Number of notifications to process in one batch
            
        Returns:
            Dict with processing statistics
        """
        try:
            # Get pending notifications
            result = await session.execute(
                select(Notification)
                .where(Notification.status == NotificationStatus.PENDING)
                .limit(batch_size)
            )
            notifications = result.scalars().all()
            
            if not notifications:
                return {
                    "success": True,
                    "processed": 0,
                    "message": "No pending notifications"
                }
            
            processed = 0
            failed = 0
            
            # Process each notification
            for notification in notifications:
                result = await self.process_notification(session, str(notification.id))
                if result["success"]:
                    processed += 1
                else:
                    failed += 1
            
            logger.info(f"Notification batch processing: {processed} sent, {failed} failed")
            
            return {
                "success": True,
                "processed": processed,
                "failed": failed,
                "total": len(notifications)
            }
            
        except Exception as e:
            logger.error(f"Error processing notification batch: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def send_immediate_sms(
        self, 
        phone_number: str, 
        message: str
    ) -> Dict[str, Any]:
        """Send immediate SMS without storing in database"""
        return await self.sms_service.send_sms(phone_number, message)
    
    async def send_immediate_email(
        self, 
        email: str, 
        subject: str, 
        content: str
    ) -> Dict[str, Any]:
        """Send immediate email without storing in database"""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{subject}</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50;">{subject}</h2>
                <div style="background: #f8f9fa; padding: 20px; border-radius: 5px;">
                    {content.replace('\n', '<br>')}
                </div>
                <hr style="margin: 30px 0;">
                <p style="color: #666; font-size: 12px;">
                    This is an automated message from AutoPort.<br>
                    Please do not reply to this email.
                </p>
            </div>
        </body>
        </html>
        """
        
        return await self.email_service.send_email(
            to_email=email,
            subject=subject,
            html_content=html_content,
            text_content=content
        )

# Global notification service instance
notification_service = NotificationService()

# Helper functions for backward compatibility
async def process_notification(session: AsyncSession, notification_id: str) -> Dict[str, Any]:
    """Process notification - backward compatibility function"""
    return await notification_service.process_notification(session, notification_id)

async def process_pending_notifications(session: AsyncSession, batch_size: int = 100) -> Dict[str, Any]:
    """Process pending notifications - backward compatibility function"""
    return await notification_service.process_pending_notifications(session, batch_size) 