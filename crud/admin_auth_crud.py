# File: crud/admin_auth_crud.py (NEW FILE)

import random
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from uuid import UUID

from fastapi import HTTPException, status
from passlib.context import CryptContext
from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import logging

from models import (
    User, UserRole, UserStatus, AdminInvitation, AdminMFAToken, 
    AdminAuditLog, AdminPasswordHistory, AdminRole
)
from schemas import (
    AdminInviteRequest, AcceptInviteRequest, BootstrapAdminRequest
)

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Password policy constants
MIN_PASSWORD_LENGTH = 12
PASSWORD_HISTORY_COUNT = 5
ACCOUNT_LOCKOUT_ATTEMPTS = 5
ACCOUNT_LOCKOUT_DURATION = 30  # minutes

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def validate_password_strength(password: str, user_info: Optional[Dict] = None) -> None:
    """
    Validate password meets security requirements.
    Raises HTTPException if password is weak.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )
    
    if not any(c.isupper() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one uppercase letter"
        )
    
    if not any(c.islower() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one lowercase letter"
        )
    
    if not any(c.isdigit() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one number"
        )
    
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one special character"
        )
    
    # Check if password contains user info
    if user_info:
        email = user_info.get("email", "").lower()
        name = user_info.get("name", "").lower()
        if email and email.split("@")[0] in password.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password cannot contain your email address"
            )
        if name and len(name) > 3 and name in password.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password cannot contain your name"
            )

async def check_password_history(
    session: AsyncSession, 
    admin_id: UUID, 
    new_password: str
) -> None:
    """Check if password was used recently."""
    result = await session.execute(
        select(AdminPasswordHistory.password_hash)
        .where(AdminPasswordHistory.admin_id == admin_id)
        .order_by(AdminPasswordHistory.created_at.desc())
        .limit(PASSWORD_HISTORY_COUNT)
    )
    
    previous_hashes = [row[0] for row in result.fetchall()]
    
    for old_hash in previous_hashes:
        if verify_password(new_password, old_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot reuse any of your last {PASSWORD_HISTORY_COUNT} passwords"
            )

async def store_password_history(
    session: AsyncSession,
    admin_id: UUID,
    password_hash: str
) -> None:
    """Store password hash in history."""
    # Remove old entries beyond limit
    result = await session.execute(
        select(AdminPasswordHistory.id)
        .where(AdminPasswordHistory.admin_id == admin_id)
        .order_by(AdminPasswordHistory.created_at.desc())
        .offset(PASSWORD_HISTORY_COUNT - 1)
    )
    
    old_ids = [row[0] for row in result.fetchall()]
    if old_ids:
        await session.execute(
            AdminPasswordHistory.__table__.delete()
            .where(AdminPasswordHistory.id.in_(old_ids))
        )
    
    # Add new entry
    history_entry = AdminPasswordHistory(
        admin_id=admin_id,
        password_hash=password_hash
    )
    session.add(history_entry)

# --- AUTHENTICATION FUNCTIONS ---

async def get_admin_count(session: AsyncSession) -> int:
    """Get total number of admin users."""
    result = await session.execute(
        select(func.count(User.id))
        .where(User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN]))
    )
    return result.scalar() or 0

async def get_admin_by_email(session: AsyncSession, email: str) -> Optional[User]:
    """Get admin user by email."""
    result = await session.execute(
        select(User)
        .where(
            and_(
                User.email == email,
                User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN])
            )
        )
    )
    return result.scalar_one_or_none()

async def authenticate_admin(
    session: AsyncSession, 
    email: str, 
    password: str
) -> Optional[User]:
    """Authenticate admin with email and password."""
    admin = await get_admin_by_email(session, email)
    if not admin or not admin.password_hash:
        return None
    
    if not verify_password(password, admin.password_hash):
        return None
    
    # Check if admin is active
    if admin.status != UserStatus.ACTIVE:
        return None
    
    return admin

async def check_account_lockout(session: AsyncSession, email: str) -> Dict[str, Any]:
    """Check if admin account is locked due to failed attempts."""
    admin = await get_admin_by_email(session, email)
    if not admin:
        return {"is_locked": False}
    
    if admin.locked_until and admin.locked_until > datetime.now(timezone.utc):
        return {
            "is_locked": True,
            "locked_until": admin.locked_until,
            "attempts": admin.failed_login_attempts
        }
    
    return {"is_locked": False, "attempts": admin.failed_login_attempts or 0}

async def record_failed_login(session: AsyncSession, email: str) -> None:
    """Record failed login attempt and potentially lock account."""
    admin = await get_admin_by_email(session, email)
    if not admin:
        return
    
    admin.failed_login_attempts = (admin.failed_login_attempts or 0) + 1
    
    if admin.failed_login_attempts >= ACCOUNT_LOCKOUT_ATTEMPTS:
        admin.locked_until = datetime.now(timezone.utc) + timedelta(minutes=ACCOUNT_LOCKOUT_DURATION)
        logger.warning(f"Admin account locked: {email} (attempts: {admin.failed_login_attempts})")
    
    session.add(admin)
    await session.flush()

async def record_successful_login(session: AsyncSession, admin: User) -> None:
    """Record successful login and reset failed attempts."""
    admin.failed_login_attempts = 0
    admin.locked_until = None
    admin.last_admin_login = datetime.now(timezone.utc)
    session.add(admin)
    await session.flush()

# --- MFA FUNCTIONS ---

async def create_mfa_token(session, admin_id: UUID) -> str:
    # Invalidate any existing unused tokens
    await session.execute(
        update(AdminMFAToken)
        .where(AdminMFAToken.admin_id == admin_id, AdminMFAToken.is_used == False)
        .values(is_used=True)
    )
    
    # Generate MFA code
    mfa_code = str(random.randint(100000, 999999))
    
    # FIX: Use timezone-aware datetime for new columns
    now_utc = datetime.now(timezone.utc)
    expires_at = now_utc + timedelta(minutes=5)
    
    mfa_token = AdminMFAToken(
        admin_id=admin_id,
        code=mfa_code,
        expires_at_tz=expires_at,      # Use new timezone-aware column
        created_at_tz=now_utc,         # Use new timezone-aware column
        is_used=False
    )
    
    session.add(mfa_token)
    await session.flush()
    
    return mfa_code

async def verify_mfa_token(session: AsyncSession, code: str) -> Optional[User]:
    """Verify MFA token and return admin user."""
    result = await session.execute(
        select(AdminMFAToken)
        .options(selectinload(AdminMFAToken.admin))
        .where(
            and_(
                AdminMFAToken.code == code,
                AdminMFAToken.is_used == False,
                AdminMFAToken.expires_at_tz > datetime.now(timezone.utc)
            )
        )
    )
    
    mfa_token = result.scalar_one_or_none()
    if not mfa_token:
        return None
    
    # Mark token as used
    mfa_token.is_used = True
    session.add(mfa_token)
    await session.flush()
    
    return mfa_token.admin

# --- ADMIN CREATION FUNCTIONS ---

async def create_bootstrap_admin(
    session: AsyncSession,
    bootstrap_data: BootstrapAdminRequest
) -> User:
    """Create the first admin account."""
    # Validate password
    validate_password_strength(
        bootstrap_data.password,
        {"email": bootstrap_data.email, "name": bootstrap_data.full_name}
    )
    
    # Hash password
    password_hash = hash_password(bootstrap_data.password)
    
    # Create admin user
    admin = User(
        email=bootstrap_data.email,
        full_name=bootstrap_data.full_name,
        phone_number=f"+998{random.randint(100000000, 999999999)}",  # Generate dummy phone
        role=UserRole.SUPER_ADMIN,
        status=UserStatus.ACTIVE,
        password_hash=password_hash,
        password_changed_at=datetime.now(),
        is_email_verified=True
    )
    
    session.add(admin)
    await session.flush()
    await session.refresh(admin)
    
    # Store password in history
    await store_password_history(session, admin.id, password_hash)
    
    return admin

# --- INVITATION FUNCTIONS ---

async def create_admin_invitation(
    session: AsyncSession,
    invite_data: AdminInviteRequest,
    inviter_id: UUID
) -> AdminInvitation:
    """Create admin invitation."""
    # Check if invitation already exists
    result = await session.execute(
        select(AdminInvitation)
        .where(
            and_(
                AdminInvitation.email == invite_data.email,
                AdminInvitation.is_used == False,
                AdminInvitation.expires_at > datetime.now(timezone.utc)
            )
        )
    )
    
    existing_invitation = result.scalar_one_or_none()
    if existing_invitation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active invitation already exists for this email"
        )
    
    # Check if admin already exists
    existing_admin = await get_admin_by_email(session, invite_data.email)
    if existing_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin with this email already exists"
        )
    
    # Generate secure token
    token = secrets.token_urlsafe(32)
    
    # Create invitation
    invitation = AdminInvitation(
        email=invite_data.email,
        invited_by=inviter_id,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        role=AdminRole(invite_data.role.value)
    )
    
    session.add(invitation)
    await session.flush()
    await session.refresh(invitation)
    
    return invitation

async def validate_invite_token(
    session: AsyncSession,
    token: str
) -> Optional[AdminInvitation]:
    """Validate invitation token."""
    result = await session.execute(
        select(AdminInvitation)
        .where(
            and_(
                AdminInvitation.token == token,
                AdminInvitation.is_used == False,
                AdminInvitation.expires_at > datetime.now(timezone.utc)
            )
        )
    )
    
    return result.scalar_one_or_none()

async def create_admin_from_invite(
    session: AsyncSession,
    invitation: AdminInvitation,
    acceptance_data: AcceptInviteRequest
) -> User:
    """Create admin account from invitation."""
    # Validate password
    validate_password_strength(
        acceptance_data.password,
        {"email": invitation.email, "name": acceptance_data.full_name}
    )
    
    # Hash password
    password_hash = hash_password(acceptance_data.password)
    
    # Determine user role
    user_role = UserRole.SUPER_ADMIN if invitation.role == AdminRole.SUPER_ADMIN else UserRole.ADMIN
    
    # Create admin user
    admin = User(
        email=invitation.email,
        full_name=acceptance_data.full_name,
        phone_number=f"+998{random.randint(100000000, 999999999)}",  # Generate dummy phone
        role=user_role,
        status=UserStatus.ACTIVE,
        password_hash=password_hash,
        password_changed_at=datetime.now(timezone.utc),
        is_email_verified=True
    )
    
    session.add(admin)
    await session.flush()
    await session.refresh(admin)
    
    # Store password in history
    await store_password_history(session, admin.id, password_hash)
    
    return admin

async def invalidate_invite(session: AsyncSession, invitation_id: UUID) -> None:
    """Mark invitation as used."""
    await session.execute(
        update(AdminInvitation)
        .where(AdminInvitation.id == invitation_id)
        .values(is_used=True, used_at=datetime.now(timezone.utc))
    )

# --- AUDIT LOGGING ---

async def log_admin_action(
    session: AsyncSession,
    admin_id: Optional[UUID],
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[UUID] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None
) -> None:
    """Log admin action for audit trail."""
    audit_log = AdminAuditLog(
        admin_id=admin_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        error_message=error_message
    )
    
    session.add(audit_log)
    await session.flush()