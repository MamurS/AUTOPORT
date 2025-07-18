# File: routers/auth.py (Fixed serialization issues)

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.jwt_handler import create_access_token
from crud.auth_crud import (
    create_sms_verification,
    create_user,
    generate_otp,
    get_otp_expiry,
    get_user_by_phone,
    mark_otp_as_used,
    update_user_profile,
    verify_otp,
    complete_driver_registration,
)
from services.sms_service import send_otp_sms
from database import get_db
from config import settings
from models import User, UserRole, UserStatus
from schemas import (
    SMSVerificationRequest,
    TokenResponse,
    UserCreatePhoneNumber,
    UserVerifyOTPAndSetProfileRequest,
    UserResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])

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

@router.post("/register/request-otp", status_code=200)
async def request_otp(
    user_data: UserCreatePhoneNumber,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    try:
        existing_user = await get_user_by_phone(db, user_data.phone_number)
        
        if existing_user:
            if existing_user.status == UserStatus.ACTIVE:
                raise HTTPException(status_code=400, detail="User with this phone number already exists and is active.")
            logger.info(f"Resending OTP for existing user: {user_data.phone_number}")
        else:
            await create_user(db, user_data.phone_number)
            logger.info(f"Created new user: {user_data.phone_number}")

        otp_code = generate_otp()
        expires_at = get_otp_expiry()
        await create_sms_verification(
            session=db,
            phone_number=user_data.phone_number,
            code=otp_code,
            expires_at=expires_at
        )
        
        # Send OTP via SMS service
        sms_result = await send_otp_sms(user_data.phone_number, otp_code)
        if sms_result["success"]:
            logger.info(f"OTP sent successfully to {user_data.phone_number}")
            return {"message": f"SMS OTP sent successfully to {user_data.phone_number}"}
        elif sms_result.get("service_disabled"):
            logger.warning(f"SMS service disabled - OTP logged instead: {otp_code}")
            return {
                "message": f"SMS OTP sent successfully to {user_data.phone_number}",
                "dev_note": "SMS service not configured - check logs for OTP code" if not settings.is_production else None
            }
        else:
            logger.error(f"Failed to send OTP to {user_data.phone_number}: {sms_result.get('error')}")
            # Still return success to avoid revealing SMS service issues
            return {"message": f"SMS OTP sent successfully to {user_data.phone_number}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in request_otp: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.post("/register/verify-otp", response_model=TokenResponse)
async def verify_otp_and_set_profile(
    request_data: UserVerifyOTPAndSetProfileRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TokenResponse:
    try:
        is_valid, verification = await verify_otp(db, request_data.phone_number, request_data.code)
        if not is_valid or not verification:
            raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
        
        user_from_db = await get_user_by_phone(db, request_data.phone_number)
        if not user_from_db or user_from_db.status == UserStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="User not found or in invalid state for OTP verification.")
        
        await mark_otp_as_used(db, verification)
        updated_user_shell = await update_user_profile(db, user_from_db, request_data.full_name)
        
        # FIXED: Convert SQLAlchemy model to Pydantic model
        user_response = convert_user_to_response(updated_user_shell)
        
        access_token = create_access_token(user_id=updated_user_shell.id, role=updated_user_shell.role.value)
        
        logger.info(f"User {updated_user_shell.phone_number} successfully registered and profile set.")
        return TokenResponse(access_token=access_token, token_type="bearer", user=user_response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in verify_otp_and_set_profile: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.post("/login/request-otp", status_code=200)
async def request_login_otp(
    user_data: UserCreatePhoneNumber,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    try:
        user = await get_user_by_phone(db, user_data.phone_number)
        if not user or user.status != UserStatus.ACTIVE:
            raise HTTPException(status_code=404, detail="Active user with this phone number not found. Please register or complete your registration.")

        otp_code = generate_otp()
        expires_at = get_otp_expiry()
        await create_sms_verification(
            session=db,
            phone_number=user_data.phone_number,
            code=otp_code,
            expires_at=expires_at
        )
        logger.info(f"Login OTP for {user_data.phone_number}: {otp_code}")
        return {"message": f"Login OTP sent successfully to {user_data.phone_number}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in request_login_otp: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.post("/login/verify-otp", response_model=TokenResponse)
async def verify_login_otp(
    request_data: SMSVerificationRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TokenResponse:
    try:
        is_valid, verification = await verify_otp(db, request_data.phone_number, request_data.code)
        if not is_valid or not verification:
            raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
        
        user_for_token = await get_user_by_phone(db, request_data.phone_number)
        if not user_for_token or user_for_token.status != UserStatus.ACTIVE:
            raise HTTPException(status_code=404, detail="User not found or not active.")
        
        await mark_otp_as_used(db, verification)
        
        # FIXED: Convert SQLAlchemy model to Pydantic model
        user_response = convert_user_to_response(user_for_token)
        
        logger.info(f"User {user_for_token.phone_number} successfully logged in.")
        access_token = create_access_token(user_id=user_for_token.id, role=user_for_token.role.value)
        return TokenResponse(access_token=access_token, token_type="bearer", user=user_response)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in verify_login_otp: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.post("/register/driver", response_model=TokenResponse)
async def complete_driver_registration_endpoint(
    request_data: UserVerifyOTPAndSetProfileRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TokenResponse:
    """
    Complete the driver registration process after OTP verification.
    This endpoint is used to set up a new driver account with their full name.
    """
    try:
        # Verify OTP first
        is_valid, verification = await verify_otp(db, request_data.phone_number, request_data.code)
        if not is_valid or not verification:
            raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
        
        # Get the user
        user = await get_user_by_phone(db, request_data.phone_number)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
            
        # Check if user is already a driver
        if user.role == UserRole.DRIVER:
            if user.status == UserStatus.ACTIVE:
                raise HTTPException(status_code=400, detail="Driver account is already active.")
            if user.status == UserStatus.PENDING_PROFILE_COMPLETION:
                raise HTTPException(status_code=400, detail="Driver registration is already pending admin review.")
        
        # Mark OTP as used
        await mark_otp_as_used(db, verification)
        
        # Complete driver registration
        updated_driver = await complete_driver_registration(db, user, request_data.full_name)
        
        # FIXED: Convert SQLAlchemy model to Pydantic model
        user_response = convert_user_to_response(updated_driver)
        
        # Generate access token
        access_token = create_access_token(user_id=updated_driver.id, role=updated_driver.role.value)
        
        logger.info(f"Driver registration completed for {updated_driver.phone_number}")
        return TokenResponse(access_token=access_token, token_type="bearer", user=user_response)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in complete_driver_registration_endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )