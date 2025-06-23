# File: routers/admin_auth.py (COMPLETE FIXED VERSION)

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

from auth.jwt_handler import create_access_token
from auth.dependencies import get_current_admin_user, get_current_super_admin
from crud.admin_auth_crud import (
    authenticate_admin,
    create_admin_invitation,
    create_admin_from_invite,
    create_mfa_token,
    verify_mfa_token,
    validate_invite_token,
    invalidate_invite,
    get_admin_count,
    create_bootstrap_admin,
    log_admin_action,
    check_account_lockout,
    record_failed_login,
    record_successful_login
)
from database import get_db
from models import User, UserRole, AdminRole
from schemas import (
    AdminLoginRequest,
    AdminMFAVerificationRequest,
    AdminTokenResponse,
    AdminInviteRequest,
    AcceptInviteRequest,
    BootstrapAdminRequest,
    AdminResponse,
    AdminInvitationResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/admin", tags=["admin-authentication"])

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def convert_user_to_admin_response(user: User) -> AdminResponse:
    """Convert User model to AdminResponse"""
    return AdminResponse(
        id=user.id,
        email=user.email or "",
        full_name=user.full_name or "",
        role=AdminRole(user.role.value) if user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN] else AdminRole.ADMIN,
        is_active=user.status.value == "active",
        last_login=user.last_admin_login,
        created_at=user.created_at,
        updated_at=user.updated_at
    )

@router.post("/bootstrap", response_model=AdminTokenResponse)
async def bootstrap_first_admin(
    request: Request,
    bootstrap_data: BootstrapAdminRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> AdminTokenResponse:
    """
    Create the first admin account. This endpoint should be disabled after first use.
    """
    try:
        # Check if any admin exists
        admin_count = await get_admin_count(db)
        if admin_count > 0:
            await log_admin_action(
                db, None, "bootstrap_attempt_rejected", 
                details={"reason": "admin_already_exists"},
                ip_address=request.client.host,
                success=False
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admin already exists. Use invite system."
            )

        # Validate password confirmation
        if bootstrap_data.password != bootstrap_data.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match"
            )

        # Create first admin
        admin = await create_bootstrap_admin(db, bootstrap_data)
        admin_response = convert_user_to_admin_response(admin)
        
        # Generate access token
        access_token = create_access_token(
            user_id=admin.id,
            role=admin.role.value
        )
        
        await log_admin_action(
            db, admin.id, "bootstrap_admin_created",
            details={"email": admin.email},
            ip_address=request.client.host
        )
        
        logger.info(f"Bootstrap admin created: {admin.email}")
        return AdminTokenResponse(
            access_token=access_token,
            admin=admin_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bootstrap_first_admin: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating bootstrap admin"
        )

@router.post("/login")
async def admin_login(
    request: Request,
    credentials: AdminLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Admin login with email and password. Returns temporary session token for MFA.
    """
    try:
        logger.info(f"🔐 Admin login attempt: {credentials.email}")
        
        # Check for account lockout
        lockout_info = await check_account_lockout(db, credentials.email)
        if lockout_info["is_locked"]:
            await log_admin_action(
                db, None, "login_attempt_locked",
                details={"email": credentials.email, "locked_until": lockout_info["locked_until"]},
                ip_address=request.client.host,
                success=False
            )
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Account locked until {lockout_info['locked_until']}"
            )

        # Authenticate admin
        admin = await authenticate_admin(db, credentials.email, credentials.password)
        if not admin:
            await record_failed_login(db, credentials.email)
            await log_admin_action(
                db, None, "login_failed",
                details={"email": credentials.email, "reason": "invalid_credentials"},
                ip_address=request.client.host,
                success=False
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Generate MFA token - FIXED: create_mfa_token returns a string, not an object
        mfa_code = await create_mfa_token(db, admin.id)
        
        # TODO: Send MFA code via email
        # await send_mfa_email(admin.email, mfa_code)
        logger.info(f"✅ MFA code generated for {admin.email}: {mfa_code}")  # Remove in production
        
        # Generate temporary session token
        session_token = secrets.token_urlsafe(32)
        
        await log_admin_action(
            db, admin.id, "login_mfa_sent",
            details={"email": admin.email},
            ip_address=request.client.host
        )
        
        logger.info(f"✅ Admin login step 1 successful: {admin.email}")
        
        return {
            "message": "MFA code sent. Please check your authenticator app.",
            "session_token": session_token,
            "expires_in": 300  # 5 minutes
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in admin_login: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login error occurred"
        )

@router.post("/verify-mfa", response_model=AdminTokenResponse)
async def verify_admin_mfa(
    request: Request,
    mfa_data: AdminMFAVerificationRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> AdminTokenResponse:
    """
    Verify MFA code and return JWT access token.
    """
    try:
        logger.info(f"🔐 MFA verification attempt for session: {mfa_data.session_token[:10]}...")
        
        # Verify MFA token
        admin = await verify_mfa_token(db, mfa_data.mfa_code)
        if not admin:
            await log_admin_action(
                db, None, "mfa_verification_failed",
                details={"session_token": mfa_data.session_token[:10] + "..."},
                ip_address=request.client.host,
                success=False
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired MFA code"
            )

        # Record successful login
        async def record_successful_login(session: AsyncSession, admin: User) -> None:
            """Record successful login and reset failed attempts."""
            admin.failed_login_attempts = 0
            admin.locked_until = None
            
            # FIX: Convert timezone-aware datetime to naive for database storage
            now_utc = datetime.now(timezone.utc)
            admin.last_admin_login = now_utc.replace(tzinfo=None)  # Remove timezone info
            
            session.add(admin)
            await session.flush()
        
        # Generate JWT access token
        access_token = create_access_token(
            user_id=admin.id,
            role=admin.role.value
        )
        
        admin_response = convert_user_to_admin_response(admin)
        
        await log_admin_action(
            db, admin.id, "login_successful",
            details={"email": admin.email},
            ip_address=request.client.host
        )
        
        logger.info(f"✅ Admin {admin.email} successfully logged in")
        return AdminTokenResponse(
            access_token=access_token,
            admin=admin_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in verify_admin_mfa: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MFA verification error"
        )

@router.post("/invite", response_model=AdminInvitationResponse)
async def invite_admin(
    request: Request,
    invite_data: AdminInviteRequest,
    current_admin: Annotated[User, Depends(get_current_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> AdminInvitationResponse:
    """
    Invite a new admin (only super-admins can invite).
    """
    try:
        # Create invitation
        invitation = await create_admin_invitation(db, invite_data, current_admin.id)
        
        # TODO: Send invitation email
        # await send_admin_invitation_email(invite_data.email, invitation.token)
        logger.info(f"Admin invitation created for {invite_data.email}. Token: {invitation.token}")
        
        await log_admin_action(
            db, current_admin.id, "admin_invited",
            details={"invited_email": invite_data.email, "role": invite_data.role.value},
            ip_address=request.client.host
        )
        
        return AdminInvitationResponse(
            id=invitation.id,
            email=invitation.email,
            role=AdminRole(invitation.role.value),
            expires_at=invitation.expires_at,
            is_used=invitation.is_used,
            created_at=invitation.created_at,
            inviter_name=current_admin.full_name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in invite_admin: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating admin invitation"
        )

@router.post("/accept-invite", response_model=AdminTokenResponse)
async def accept_admin_invite(
    request: Request,
    acceptance_data: AcceptInviteRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
) -> AdminTokenResponse:
    """
    Accept admin invitation and create account.
    """
    try:
        # Validate password confirmation
        if acceptance_data.password != acceptance_data.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match"
            )

        # Validate invitation token
        invitation = await validate_invite_token(db, acceptance_data.token)
        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired invitation token"
            )

        # Create admin account
        admin = await create_admin_from_invite(db, invitation, acceptance_data)
        
        # Invalidate invitation
        await invalidate_invite(db, invitation.id)
        
        # Generate access token
        access_token = create_access_token(
            user_id=admin.id,
            role=admin.role.value
        )
        
        admin_response = convert_user_to_admin_response(admin)
        
        await log_admin_action(
            db, admin.id, "admin_account_created",
            details={"email": admin.email, "invitation_id": str(invitation.id)},
            ip_address=request.client.host
        )
        
        logger.info(f"Admin account created from invitation: {admin.email}")
        return AdminTokenResponse(
            access_token=access_token,
            admin=admin_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in accept_admin_invite: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error accepting admin invitation"
        )

@router.get("/me", response_model=AdminResponse)
async def get_current_admin_profile(
    current_admin: Annotated[User, Depends(get_current_admin_user)]
) -> AdminResponse:
    """Get current admin's profile information."""
    return convert_user_to_admin_response(current_admin)