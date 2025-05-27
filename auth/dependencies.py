# File: auth/dependencies.py

import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
# jose.jwt and JWTError are now used via verify_token_payload from jwt_handler
# from jose import JWTError, jwt 
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings # Import settings
from crud.auth_crud import get_user_by_id
from database import get_db
from models import User, UserStatus, UserRole
from auth.jwt_handler import verify_token_payload # Import the utility

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.APP_NAME.lower().replace(' ', '')}/auth/token") # Example tokenUrl using settings

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = verify_token_payload(token) # Use the utility from jwt_handler
    
    user_id_from_token: str = payload.get("sub")
    if user_id_from_token is None:
        raise credentials_exception
    
    # The get_user_by_id CRUD function expects a string and handles UUID conversion internally
    user = await get_user_by_id(session, user_id_from_token)
    if user is None:
        # This could happen if the user was deleted after the token was issued
        raise credentials_exception
    
    return user

async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    if current_user.status != UserStatus.ACTIVE:
        # Consider if PENDING_PROFILE_COMPLETION for drivers should also be allowed for some routes
        # For now, strict ACTIVE check
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, # 403 as they are authenticated but not permitted due to status
            detail="User is inactive or blocked."
        )
    return current_user

async def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> User:
    if current_user.role != UserRole.ADMIN:
        logger.warning(f"User {current_user.id} ({current_user.role.value}) attempted to access admin endpoint.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required."
        )
    return current_user