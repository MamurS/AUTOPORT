# File: routers/auth.py (Refactored for dependency-level transactions)

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status # status might be used by HTTPExceptions
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload # For re-fetching with relationships for response

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
from database import get_db
from models import User, UserRole, UserStatus # Added User, UserRole for re-fetch if needed by UserResponse
from schemas import (
    SMSVerificationRequest,
    TokenResponse,
    UserCreatePhoneNumber,
    UserVerifyOTPAndSetProfileRequest,
    UserResponse # For re-fetch type hint
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/register/request-otp", status_code=200)
async def request_otp(
    user_data: UserCreatePhoneNumber,
    db: Annotated[AsyncSession, Depends(get_db)] # Renamed session to db for consistency
) -> dict:
    try:
        # CRUD functions no longer commit/rollback; get_db handles it.
        # No db.begin_nested() needed here.
        existing_user = await get_user_by_phone(db, user_data.phone_number)
        
        if existing_user:
            if existing_user.status == UserStatus.ACTIVE:
                raise HTTPException(status_code=400, detail="User with this phone number already exists and is active.")
            logger.info(f"Resending OTP for existing user: {user_data.phone_number}")
        else:
            # create_user will add to session and flush
            await create_user(db, user_data.phone_number)
            logger.info(f"Created new user: {user_data.phone_number}")

        otp_code = generate_otp()
        expires_at = get_otp_expiry()
        # create_sms_verification will add to session and flush (also calls invalidate_old_otps which flushes)
        await create_sms_verification(
            session=db, # Keep session for CRUD param name
            phone_number=user_data.phone_number,
            code=otp_code,
            expires_at=expires_at
        )
        logger.info(f"OTP for {user_data.phone_number}: {otp_code}")
        # The commit will happen in get_db if no exceptions are raised here.
        return {"message": f"SMS OTP sent successfully to {user_data.phone_number}"}

    except HTTPException:
        raise # Will be caught by get_db for rollback
    except Exception as e:
        logger.error(f"Error in request_otp: {e}", exc_info=True)
        # Will be caught by get_db for rollback
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.post("/register/verify-otp", response_model=TokenResponse)
async def verify_otp_and_set_profile(
    request_data: UserVerifyOTPAndSetProfileRequest,
    db: Annotated[AsyncSession, Depends(get_db)] # Renamed session to db
) -> TokenResponse:
    try:
        # No db.begin_nested() needed here.
        is_valid, verification = await verify_otp(db, request_data.phone_number, request_data.code)
        if not is_valid or not verification:
            raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
        
        user_from_db = await get_user_by_phone(db, request_data.phone_number) # Renamed to user_from_db
        if not user_from_db or user_from_db.status == UserStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="User not found or in invalid state for OTP verification.")
        
        await mark_otp_as_used(db, verification)
        updated_user_shell = await update_user_profile(db, user_from_db, request_data.full_name)
        
        # All operations above are part of the transaction managed by get_db.
        # If we reach here, get_db will commit.
        # Now, ensure the returned user object for TokenResponse is fully loaded as Pydantic expects.
        # UserResponse doesn't have complex nested relationships directly, uses UserBase.
        # The updated_user_shell from CRUD (after refresh) should be sufficient.

        access_token = create_access_token(user_id=updated_user_shell.id, role=updated_user_shell.role.value)
        # We need to return an actual UserResponse, Pydantic will build it from updated_user_shell
        # If UserResponse required relationships not loaded by refresh, we'd re-select here.
        # For UserResponse, which inherits UserBase and adds id, status, notes, created_at, updated_at,
        # the refreshed 'updated_user_shell' should be fine.
        
        logger.info(f"User {updated_user_shell.phone_number} successfully registered and profile set.")
        return TokenResponse(access_token=access_token, token_type="bearer", user=updated_user_shell)

    except HTTPException:
        raise # Will be caught by get_db for rollback
    except Exception as e:
        logger.error(f"Error in verify_otp_and_set_profile: {e}", exc_info=True)
        # Will be caught by get_db for rollback
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.post("/login/request-otp", status_code=200)
async def request_login_otp(
    user_data: UserCreatePhoneNumber,
    db: Annotated[AsyncSession, Depends(get_db)] # Renamed session to db
) -> dict:
    try:
        # No db.begin_nested() needed here.
        user = await get_user_by_phone(db, user_data.phone_number)
        if not user or user.status != UserStatus.ACTIVE:
            raise HTTPException(status_code=404, detail="Active user with this phone number not found. Please register or complete your registration.")

        otp_code = generate_otp()
        expires_at = get_otp_expiry()
        await create_sms_verification(
            session=db, # CRUD param name
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
    db: Annotated[AsyncSession, Depends(get_db)] # Renamed session to db
) -> TokenResponse:
    try:
        # No db.begin_nested() needed here.
        is_valid, verification = await verify_otp(db, request_data.phone_number, request_data.code)
        if not is_valid or not verification:
            raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
        
        user_for_token = await get_user_by_phone(db, request_data.phone_number) # Renamed to user_for_token
        if not user_for_token or user_for_token.status != UserStatus.ACTIVE:
            raise HTTPException(status_code=404, detail="User not found or not active.")
        
        await mark_otp_as_used(db, verification)
        # The user object (user_for_token) is already loaded and its state is correct for the token response.
        
        logger.info(f"User {user_for_token.phone_number} successfully logged in.")
        access_token = create_access_token(user_id=user_for_token.id, role=user_for_token.role.value)
        return TokenResponse(access_token=access_token, token_type="bearer", user=user_for_token)
        
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
        
        # Generate access token
        access_token = create_access_token(user_id=updated_driver.id, role=updated_driver.role.value)
        
        logger.info(f"Driver registration completed for {updated_driver.phone_number}")
        return TokenResponse(access_token=access_token, token_type="bearer", user=updated_driver)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in complete_driver_registration_endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )