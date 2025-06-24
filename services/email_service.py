# File: services/email_service.py (Production Email Service)

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.utils import formataddr
from email import encoders
from typing import Optional, List, Dict, Any
from pathlib import Path
import aiosmtplib

from config import settings

logger = logging.getLogger(__name__)

class EmailService:
    """Production email service using SMTP"""
    
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME
        self.use_tls = settings.SMTP_USE_TLS
        
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send email using async SMTP
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email content
            text_content: Plain text email content (optional)
            attachments: List of attachment dicts with 'filename' and 'content' keys
            reply_to: Reply-to email address
            
        Returns:
            Dict with success status and response data
        """
        if not self.smtp_password:
            logger.warning("SMTP_PASSWORD not configured - Email service disabled")
            return {
                "success": False,
                "error": "Email service not configured",
                "service_disabled": True
            }
            
        try:
            # Create message
            message = MIMEMultipart('alternative')
            message['Subject'] = subject
            message['From'] = formataddr((self.from_name, self.from_email))
            message['To'] = to_email
            
            if reply_to:
                message['Reply-To'] = reply_to
            
            # Add text content
            if text_content:
                text_part = MIMEText(text_content, 'plain', 'utf-8')
                message.attach(text_part)
            
            # Add HTML content
            html_part = MIMEText(html_content, 'html', 'utf-8')
            message.attach(html_part)
            
            # Add attachments
            if attachments:
                for attachment in attachments:
                    self._add_attachment(message, attachment)
            
            # Send email
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_username,
                password=self.smtp_password,
                use_tls=self.use_tls,
                timeout=30
            )
            
            logger.info(f"Email sent successfully to {to_email}")
            return {
                "success": True,
                "message": f"Email sent to {to_email}"
            }
            
        except Exception as e:
            error_msg = f"Email sending error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "error": error_msg
            }
    
    async def send_admin_mfa_code(
        self, 
        admin_email: str, 
        admin_name: str, 
        mfa_code: str
    ) -> Dict[str, Any]:
        """Send MFA code to admin"""
        subject = "AutoPort Admin - Your MFA Code"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>AutoPort Admin MFA</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50;">AutoPort Admin Authentication</h2>
                <p>Hello {admin_name},</p>
                <p>Your multi-factor authentication code is:</p>
                <div style="background: #f8f9fa; padding: 20px; border-radius: 5px; text-align: center; margin: 20px 0;">
                    <h1 style="color: #007bff; margin: 0; font-size: 32px; letter-spacing: 5px;">{mfa_code}</h1>
                </div>
                <p><strong>This code will expire in 5 minutes.</strong></p>
                <p>If you didn't request this code, please contact the system administrator immediately.</p>
                <hr style="margin: 30px 0;">
                <p style="color: #666; font-size: 12px;">
                    This is an automated message from AutoPort Admin System.<br>
                    Please do not reply to this email.
                </p>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        AutoPort Admin Authentication
        
        Hello {admin_name},
        
        Your multi-factor authentication code is: {mfa_code}
        
        This code will expire in 5 minutes.
        
        If you didn't request this code, please contact the system administrator immediately.
        """
        
        return await self.send_email(
            to_email=admin_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )
    
    async def send_admin_invitation(
        self,
        email: str,
        invitation_token: str,
        invited_by_name: str,
        role: str
    ) -> Dict[str, Any]:
        """Send admin invitation email"""
        subject = "AutoPort Admin - You're Invited!"
        
        invitation_url = f"{settings.ADMIN_FRONTEND_URL}/accept-invite?token={invitation_token}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>AutoPort Admin Invitation</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50;">Welcome to AutoPort Admin</h2>
                <p>Hello,</p>
                <p>You have been invited by <strong>{invited_by_name}</strong> to join the AutoPort admin team as a <strong>{role}</strong>.</p>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin-top: 0;">What's next?</h3>
                    <ol>
                        <li>Click the invitation link below</li>
                        <li>Set up your admin account and password</li>
                        <li>Enable multi-factor authentication</li>
                        <li>Start managing the AutoPort platform</li>
                    </ol>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{invitation_url}" 
                       style="display: inline-block; background: #007bff; color: white; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; font-weight: bold;">
                        Accept Invitation
                    </a>
                </div>
                
                <p><strong>This invitation will expire in 24 hours.</strong></p>
                
                <p>If the button doesn't work, copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #007bff;">{invitation_url}</p>
                
                <hr style="margin: 30px 0;">
                <p style="color: #666; font-size: 12px;">
                    This invitation was sent to {email}.<br>
                    If you weren't expecting this invitation, you can safely ignore this email.
                </p>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        Welcome to AutoPort Admin
        
        You have been invited by {invited_by_name} to join the AutoPort admin team as a {role}.
        
        To accept this invitation:
        1. Visit: {invitation_url}
        2. Set up your admin account and password
        3. Enable multi-factor authentication
        4. Start managing the AutoPort platform
        
        This invitation will expire in 24 hours.
        
        If you weren't expecting this invitation, you can safely ignore this email.
        """
        
        return await self.send_email(
            to_email=email,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )
    
    async def send_password_reset(
        self,
        email: str,
        name: str,
        reset_token: str
    ) -> Dict[str, Any]:
        """Send password reset email"""
        subject = "AutoPort Admin - Password Reset"
        
        reset_url = f"{settings.ADMIN_FRONTEND_URL}/reset-password?token={reset_token}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>AutoPort Admin Password Reset</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50;">Password Reset Request</h2>
                <p>Hello {name},</p>
                <p>We received a request to reset your AutoPort admin password.</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}" 
                       style="display: inline-block; background: #dc3545; color: white; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; font-weight: bold;">
                        Reset Password
                    </a>
                </div>
                
                <p><strong>This link will expire in 1 hour.</strong></p>
                
                <p>If you didn't request a password reset, please ignore this email or contact support if you're concerned.</p>
                
                <p>If the button doesn't work, copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #007bff;">{reset_url}</p>
                
                <hr style="margin: 30px 0;">
                <p style="color: #666; font-size: 12px;">
                    This is an automated message from AutoPort Admin System.<br>
                    Please do not reply to this email.
                </p>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        Password Reset Request
        
        Hello {name},
        
        We received a request to reset your AutoPort admin password.
        
        To reset your password, visit: {reset_url}
        
        This link will expire in 1 hour.
        
        If you didn't request a password reset, please ignore this email.
        """
        
        return await self.send_email(
            to_email=email,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )
    
    def _add_attachment(self, message: MIMEMultipart, attachment: Dict[str, Any]):
        """Add attachment to email message"""
        try:
            filename = attachment.get('filename', 'attachment')
            content = attachment.get('content')
            
            if isinstance(content, str):
                content = content.encode('utf-8')
            
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(content)
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {filename}'
            )
            message.attach(part)
            
        except Exception as e:
            logger.error(f"Error adding attachment {attachment.get('filename')}: {e}")

# Global email service instance
email_service = EmailService()

# Helper functions for backward compatibility
async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None
) -> Dict[str, Any]:
    """Send email - backward compatibility function"""
    return await email_service.send_email(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
        text_content=text_content
    )

async def send_admin_mfa_email(
    admin_email: str,
    admin_name: str,
    mfa_code: str
) -> Dict[str, Any]:
    """Send admin MFA code - backward compatibility function"""
    return await email_service.send_admin_mfa_code(admin_email, admin_name, mfa_code) 