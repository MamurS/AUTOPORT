# File: crud/auth_crud.py (Refactored for dependency-level transactions)

import random
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import select, update, and_ # 'update' is used here
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError # Good to catch specific DB errors

from models import User, SMSVerification, UserStatus, UserRole
from schemas import UserCreatePhoneNumber # Not used directly, but was in approved version
from fastapi import HTTPException, status
import logging

logger = logging.getLogger(__name__)

# --- Read operations (get_user_by_phone, get_user_by_id, verify_otp) remain unchanged ---
async def get_user_by_phone(session: AsyncSession, phone_number: str) -> Optional[User]:
    # ... (as before)
    result = await session.execute(select(User).where(User.phone_number == phone_number))
    return result.scalar_one_or_none()

async def get_user_by_id(session: AsyncSession, user_id: str) -> Optional[User]:
    # ... (as before)
    try:
        uuid_obj = UUID(user_id)
    except ValueError:
        return None
    result = await session.execute(select(User).where(User.id == uuid_obj))
    return result.scalar_one_or_none()

async def verify_otp(
    session: AsyncSession, phone_number: str, code: str
) -> Tuple[bool, Optional[SMSVerification]]:
    # ... (as before)
    # This is a read operation, no commit/rollback needed internally.
    # Error handling should already be raising HTTPException for DB issues.
    result = await session.execute(
        select(SMSVerification).where(
            and_(
                SMSVerification.phone_number == phone_number,
                SMSVerification.code == code,
                SMSVerification.is_used == False,
                SMSVerification.expires_at > datetime.utcnow()
            )
        ).order_by(SMSVerification.created_at.desc())
    )
    verification = result.scalar_one_or_none()
    if not verification:
        return False, None
    return True, verification

# --- Write operations (to be modified) ---

async def create_user(session: AsyncSession, phone_number: str) -> User:
    """Create a new user. Caller handles transaction."""
    user = User(phone_number=phone_number) # Defaults for role & status from model
    session.add(user)
    await session.flush() # To get user.id if needed immediately by caller before commit
    await session.refresh(user) # To get DB defaults like created_at after flush
    return user

async def invalidate_old_otps(session: AsyncSession, phone_number: str) -> None:
    """Mark all unused OTPs for a phone number as used. Caller handles transaction."""
    await session.execute(
        update(SMSVerification)
        .where(
            SMSVerification.phone_number == phone_number,
            SMSVerification.is_used == False
        )
        .values(is_used=True)
    )
    # No commit here

async def create_sms_verification(
    session: AsyncSession,
    phone_number: str,
    code: str,
    expires_at: datetime
) -> SMSVerification:
    """Create a new SMS verification record. Caller handles transaction."""
    await invalidate_old_otps(session, phone_number) # This now doesn't commit
    
    verification = SMSVerification(
        phone_number=phone_number,
        code=code,
        expires_at=expires_at
    )
    session.add(verification)
    await session.flush() # To get verification.id
    await session.refresh(verification) # To get DB defaults
    return verification

async def mark_otp_as_used(
    session: AsyncSession,
    verification: SMSVerification
) -> None:
    """Mark an OTP verification record as used. Caller handles transaction."""
    verification.is_used = True
    session.add(verification) # Good to explicitly add modified instance
    # No commit here

async def update_user_profile(
    session: AsyncSession,
    user: User,
    full_name: str
) -> User:
    """Update a user's profile and set their status based on role. Caller handles transaction."""
    user.full_name = full_name
    if user.role == UserRole.DRIVER:
        user.status = UserStatus.PENDING_PROFILE_COMPLETION
    else:
        user.status = UserStatus.ACTIVE
    session.add(user) # Good to explicitly add modified instance
    await session.flush() # Ensure changes are pending before refresh
    await session.refresh(user) # Get updated_at etc.
    return user

async def request_driver_role(session: AsyncSession, user_to_update: User) -> User:
    """
    Updates a user's role to DRIVER and sets their status to PENDING_PROFILE_COMPLETION.
    This function is used when a user applies to become a driver.
    
    Args:
        session: The database session
        user_to_update: The user object to update
        
    Returns:
        The updated user object
        
    Raises:
        HTTPException: If the user is an admin or if there's an error updating the user
    """
    try:
        # Check if user is an admin
        if user_to_update.role == UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admins cannot apply for driver role."
            )
            
        # If user is already a driver and either pending or active, reset to pending
        if user_to_update.role == UserRole.DRIVER and user_to_update.status in [
            UserStatus.PENDING_PROFILE_COMPLETION,
            UserStatus.ACTIVE
        ]:
            user_to_update.status = UserStatus.PENDING_PROFILE_COMPLETION
        else:
            # Set role to DRIVER and status to PENDING_PROFILE_COMPLETION
            user_to_update.role = UserRole.DRIVER
            user_to_update.status = UserStatus.PENDING_PROFILE_COMPLETION
            
        # Clear any previous admin verification notes for re-application
        user_to_update.admin_verification_notes = None
        
        # Add to session and flush
        session.add(user_to_update)
        await session.flush()
        await session.refresh(user_to_update)
        
        return user_to_update
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in request_driver_role: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your driver application."
        )

# --- Utility functions (generate_otp, get_otp_expiry) remain unchanged ---
def generate_otp() -> str:
    # ... (as before)
    return str(random.randint(100000, 999999))

def get_otp_expiry(minutes: int = 5) -> datetime:
    # ... (as before)
    return datetime.utcnow() + timedelta(minutes=minutes)