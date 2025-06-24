# File: services/sms_service.py (Production SMS Service)

import asyncio
import logging
from typing import Optional, Dict, Any
import httpx
from datetime import datetime

from config import settings

logger = logging.getLogger(__name__)

class SMSService:
    """Production SMS service using Eskiz SMS API"""
    
    def __init__(self):
        self.api_url = settings.SMS_API_URL
        self.api_token = settings.SMS_API_TOKEN
        self.from_number = settings.SMS_FROM_NUMBER
        self.timeout = 30.0
        
    async def send_sms(
        self, 
        phone_number: str, 
        message: str,
        callback_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send SMS using Eskiz SMS API
        
        Args:
            phone_number: Phone number in international format (e.g., +998901234567)
            message: SMS message content
            callback_url: Optional callback URL for delivery status
            
        Returns:
            Dict with success status and response data
        """
        if not self.api_token:
            logger.warning("SMS_API_TOKEN not configured - SMS service disabled")
            return {
                "success": False,
                "error": "SMS service not configured",
                "service_disabled": True
            }
            
        # Ensure phone number is in correct format
        phone_number = self._format_phone_number(phone_number)
        
        payload = {
            "mobile_phone": phone_number,
            "message": message,
            "from": self.from_number,
        }
        
        if callback_url:
            payload["callback_url"] = callback_url
            
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/message/sms/send",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"SMS sent successfully to {phone_number}")
                    return {
                        "success": True,
                        "message_id": result.get("id"),
                        "status": result.get("status"),
                        "response": result
                    }
                else:
                    error_msg = f"SMS sending failed: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return {
                        "success": False,
                        "error": error_msg,
                        "status_code": response.status_code
                    }
                    
        except httpx.TimeoutException:
            error_msg = f"SMS sending timeout for {phone_number}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"SMS sending error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "error": error_msg
            }
    
    async def send_otp(self, phone_number: str, otp_code: str) -> Dict[str, Any]:
        """
        Send OTP SMS
        
        Args:
            phone_number: Phone number in international format
            otp_code: 6-digit OTP code
            
        Returns:
            Dict with success status and response data
        """
        message = f"Your AutoPort verification code is: {otp_code}. Do not share this code with anyone. Valid for 5 minutes."
        return await self.send_sms(phone_number, message)
    
    async def send_trip_notification(
        self, 
        phone_number: str, 
        trip_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send trip-related notification SMS"""
        message = self._format_trip_message(trip_info)
        return await self.send_sms(phone_number, message)
    
    async def send_emergency_sms(
        self, 
        phone_number: str, 
        emergency_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send emergency notification SMS"""
        message = self._format_emergency_message(emergency_info)
        return await self.send_sms(phone_number, message)
    
    async def get_message_status(self, message_id: str) -> Dict[str, Any]:
        """Get SMS delivery status"""
        if not self.api_token:
            return {
                "success": False,
                "error": "SMS service not configured"
            }
            
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.api_url}/message/sms/status/{message_id}",
                    headers=headers
                )
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "status": response.json()
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Status check failed: {response.status_code}"
                    }
                    
        except Exception as e:
            logger.error(f"Error checking SMS status: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def _format_phone_number(self, phone_number: str) -> str:
        """Format phone number for Eskiz API"""
        # Remove any non-digit characters except +
        phone_number = ''.join(c for c in phone_number if c.isdigit() or c == '+')
        
        # Ensure it starts with +998 for Uzbekistan
        if not phone_number.startswith('+'):
            if phone_number.startswith('998'):
                phone_number = '+' + phone_number
            elif phone_number.startswith('9') and len(phone_number) == 9:
                phone_number = '+998' + phone_number
            else:
                phone_number = '+998' + phone_number.lstrip('0')
        
        return phone_number
    
    def _format_trip_message(self, trip_info: Dict[str, Any]) -> str:
        """Format trip notification message"""
        return f"AutoPort: {trip_info.get('title', 'Trip Update')} - {trip_info.get('message', '')}"
    
    def _format_emergency_message(self, emergency_info: Dict[str, Any]) -> str:
        """Format emergency notification message"""
        return f"🚨 EMERGENCY: {emergency_info.get('message', 'Emergency alert from AutoPort user')}"

# Global SMS service instance
sms_service = SMSService()

# Helper functions for backward compatibility
async def send_sms(phone_number: str, message: str) -> Dict[str, Any]:
    """Send SMS - backward compatibility function"""
    return await sms_service.send_sms(phone_number, message)

async def send_otp_sms(phone_number: str, otp_code: str) -> Dict[str, Any]:
    """Send OTP SMS - backward compatibility function"""
    return await sms_service.send_otp(phone_number, otp_code) 