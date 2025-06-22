# File: auth/dependencies.py (Complete updated version with admin support)

import logging
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from crud.auth_crud import get_user_by_id
from database import get_db
from models import User, UserStatus, UserRole
from auth.jwt_handler import verify_token_payload

logger = logging.getLogger(__name__)

# OAuth2 scheme for token extraction
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.APP_NAME.lower().replace(' ', '')}/auth/token"
)

# Optional OAuth2 scheme (doesn't raise exception if no token)
optional_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.APP_NAME.lower().replace(' ', '')}/auth/token",
    auto_error=False
)

# ===== CORE USER AUTHENTICATION =====

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    """
    Get current user from JWT token (for all users including admins).
    Raises 401 if token is invalid or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = verify_token_payload(token)
        user_id_from_token: str = payload.get("sub")
        
        if user_id_from_token is None:
            logger.warning("Token missing 'sub' field")
            raise credentials_exception
        
        user = await get_user_by_id(session, user_id_from_token)
        if user is None:
            logger.warning(f"User not found for ID: {user_id_from_token}")
            raise credentials_exception
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating token: {e}")
        raise credentials_exception

async def get_optional_current_user(
    token: Annotated[Optional[str], Depends(optional_oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)]
) -> Optional[User]:
    """
    Get current user if token is provided, otherwise return None.
    Useful for endpoints that work with or without authentication.
    """
    if not token:
        return None
    
    try:
        payload = verify_token_payload(token)
        user_id_from_token: str = payload.get("sub")
        
        if user_id_from_token is None:
            return None
        
        user = await get_user_by_id(session, user_id_from_token)
        return user
        
    except Exception as e:
        logger.debug(f"Optional auth failed: {e}")
        return None

# ===== USER STATUS VALIDATION =====

async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """
    Get current active user (for regular users).
    Raises 403 if user is not active.
    """
    if current_user.status != UserStatus.ACTIVE:
        logger.warning(f"Inactive user attempted access: {current_user.id} - {current_user.status}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive or blocked."
        )
    return current_user

async def get_current_verified_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """
    Get current user who has completed verification.
    Allows both ACTIVE and PENDING_PROFILE_COMPLETION for drivers.
    """
    allowed_statuses = [UserStatus.ACTIVE]
    
    # Allow drivers with pending profile completion to access some endpoints
    if current_user.role == UserRole.DRIVER:
        allowed_statuses.append(UserStatus.PENDING_PROFILE_COMPLETION)
    
    if current_user.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account verification required."
        )
    
    return current_user

# ===== ADMIN AUTHENTICATION =====

async def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """
    Get current admin user (admin or super admin).
    Raises 403 if user is not an admin or account is inactive.
    """
    # Check admin role
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        logger.warning(
            f"Non-admin user {current_user.id} ({current_user.role.value}) "
            f"attempted to access admin endpoint"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required."
        )
    
    # Check account status
    if current_user.status != UserStatus.ACTIVE:
        logger.warning(f"Inactive admin attempted access: {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin account is inactive."
        )
    
    logger.info(f"Admin access granted: {current_user.id} ({current_user.role.value})")
    return current_user

async def get_current_super_admin(
    current_user: Annotated[User, Depends(get_current_admin_user)]
) -> User:
    """
    Get current super admin user (only super admins).
    Raises 403 if user is not a super admin.
    """
    if current_user.role != UserRole.SUPER_ADMIN:
        logger.warning(
            f"Admin {current_user.id} ({current_user.role.value}) "
            f"attempted to access super admin endpoint"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super administrator access required."
        )
    
    logger.info(f"Super admin access granted: {current_user.id}")
    return current_user

# ===== ROLE-SPECIFIC DEPENDENCIES =====

async def get_current_driver(
    current_user: Annotated[User, Depends(get_current_verified_user)]
) -> User:
    """
    Get current driver user.
    Allows drivers with pending profile completion.
    """
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Driver access required."
        )
    return current_user

async def get_current_passenger(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> User:
    """
    Get current passenger user.
    Requires active status.
    """
    if current_user.role != UserRole.PASSENGER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Passenger access required."
        )
    return current_user

# ===== FLEXIBLE ROLE DEPENDENCIES =====

def require_any_role(*roles: UserRole):
    """
    Factory function to create dependency that requires any of the specified roles.
    
    Usage:
        @app.get("/endpoint")
        async def endpoint(user: User = Depends(require_any_role(UserRole.DRIVER, UserRole.ADMIN))):
            pass
    """
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)]
    ) -> User:
        if current_user.role not in roles:
            logger.warning(
                f"User {current_user.id} ({current_user.role.value}) "
                f"attempted access requiring roles: {[r.value for r in roles]}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[role.value for role in roles]}"
            )
        
        # Check account status based on role
        if current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            # Admins must be active
            if current_user.status != UserStatus.ACTIVE:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin account is inactive."
                )
        elif current_user.role == UserRole.DRIVER:
            # Drivers can be active or pending profile completion
            if current_user.status not in [UserStatus.ACTIVE, UserStatus.PENDING_PROFILE_COMPLETION]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Driver account verification required."
                )
        else:
            # Passengers must be active
            if current_user.status != UserStatus.ACTIVE:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is inactive."
                )
        
        return current_user
    
    return Depends(role_checker)

def require_driver_or_admin():
    """Dependency that allows both drivers and admins."""
    return require_any_role(UserRole.DRIVER, UserRole.ADMIN, UserRole.SUPER_ADMIN)

def require_passenger_or_admin():
    """Dependency that allows both passengers and admins."""
    return require_any_role(UserRole.PASSENGER, UserRole.ADMIN, UserRole.SUPER_ADMIN)

def require_user_or_admin():
    """Dependency that allows any user type including admins."""
    return require_any_role(UserRole.PASSENGER, UserRole.DRIVER, UserRole.ADMIN, UserRole.SUPER_ADMIN)

# ===== ADMIN PERMISSION DEPENDENCIES =====

def require_admin_permission(permission: str):
    """
    Factory function to create dependency that requires specific admin permissions.
    
    Note: Currently all admins have all permissions. 
    This is prepared for future granular permission system.
    
    Usage:
        @app.post("/admin/sensitive-action")
        async def action(admin: User = Depends(require_admin_permission("manage_users"))):
            pass
    """
    async def permission_checker(
        current_admin: Annotated[User, Depends(get_current_admin_user)]
    ) -> User:
        # TODO: Implement granular permissions system
        # For now, all admins have all permissions
        # Future implementation might check:
        # if permission not in current_admin.permissions:
        #     raise HTTPException(403, f"Permission '{permission}' required")
        
        logger.debug(f"Permission '{permission}' granted to admin {current_admin.id}")
        return current_admin
    
    return Depends(permission_checker)

# ===== SPECIALIZED ADMIN DEPENDENCIES =====

async def get_admin_with_driver_management(
    current_admin: Annotated[User, Depends(get_current_admin_user)]
) -> User:
    """
    Admin with permission to manage drivers.
    Currently all admins can manage drivers.
    """
    return current_admin

async def get_admin_with_car_management(
    current_admin: Annotated[User, Depends(get_current_admin_user)]
) -> User:
    """
    Admin with permission to manage cars.
    Currently all admins can manage cars.
    """
    return current_admin

async def get_admin_with_user_management(
    current_admin: Annotated[User, Depends(get_current_admin_user)]
) -> User:
    """
    Admin with permission to manage users.
    Currently all admins can manage users.
    """
    return current_admin

async def get_admin_with_system_management(
    current_admin: Annotated[User, Depends(get_current_super_admin)]
) -> User:
    """
    Admin with permission to manage system settings.
    Only super admins can manage system settings.
    """
    return current_admin

# ===== RESOURCE OWNERSHIP DEPENDENCIES =====

async def get_user_or_admin(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """
    Get user with admin override capability.
    Useful for endpoints where users can access their own data or admins can access any data.
    """
    # Validate status based on role
    if current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        if current_user.status != UserStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin account is inactive."
            )
    else:
        if current_user.status != UserStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive."
            )
    
    return current_user

# ===== UTILITY FUNCTIONS =====

def is_admin(user: User) -> bool:
    """Check if user is an admin (any level)."""
    return user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]

def is_super_admin(user: User) -> bool:
    """Check if user is a super admin."""
    return user.role == UserRole.SUPER_ADMIN

def is_driver(user: User) -> bool:
    """Check if user is a driver."""
    return user.role == UserRole.DRIVER

def is_passenger(user: User) -> bool:
    """Check if user is a passenger."""
    return user.role == UserRole.PASSENGER

def can_access_resource(user: User, resource_owner_id: str) -> bool:
    """
    Check if user can access a resource.
    Users can access their own resources, admins can access any resource.
    """
    return str(user.id) == resource_owner_id or is_admin(user)

def has_admin_privileges(user: User) -> bool:
    """Check if user has admin privileges."""
    return is_admin(user) and user.status == UserStatus.ACTIVE