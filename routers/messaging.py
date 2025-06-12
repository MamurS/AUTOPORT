# File: routers/messaging.py

import logging
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_active_user
from crud import messaging_crud
from database import get_db
from models import User
from schemas import (
    MessageCreate, MessageResponse, MessageThreadResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/messaging", tags=["messaging"])

@router.get("/threads", response_model=List[MessageThreadResponse])
async def get_user_message_threads(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100)
) -> List[MessageThreadResponse]:
    """
    Get all message threads for the current user.
    """
    try:
        threads = await messaging_crud.get_user_threads(
            session=db,
            user_id=current_user.id,
            skip=skip,
            limit=limit
        )
        logger.info(f"Retrieved {len(threads)} message threads for user {current_user.id}")
        return threads
    except Exception as e:
        logger.error(f"Error getting message threads for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving message threads."
        )

@router.get("/threads/{thread_id}", response_model=MessageThreadResponse)
async def get_message_thread(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> MessageThreadResponse:
    """
    Get a specific message thread with all messages.
    """
    try:
        thread = await messaging_crud.get_thread_with_messages(
            session=db,
            thread_id=thread_id,
            user_id=current_user.id
        )
        if not thread:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message thread not found or you don't have access to it."
            )
        
        # Mark messages as read
        await messaging_crud.mark_messages_as_read(
            session=db,
            thread_id=thread_id,
            user_id=current_user.id
        )
        
        return thread
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting message thread {thread_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving the message thread."
        )

@router.post("/threads/{thread_id}/messages", response_model=MessageResponse)
async def send_message(
    thread_id: UUID,
    message_data: MessageCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> MessageResponse:
    """
    Send a message in a thread.
    """
    try:
        # Verify user has access to thread
        thread = await messaging_crud.get_thread_with_access_check(
            session=db,
            thread_id=thread_id,
            user_id=current_user.id
        )
        if not thread:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message thread not found or you don't have access to it."
            )
        
        message = await messaging_crud.create_message(
            session=db,
            thread_id=thread_id,
            sender_id=current_user.id,
            message_data=message_data
        )
        
        logger.info(f"Message sent by user {current_user.id} in thread {thread_id}")
        return message
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message in thread {thread_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while sending the message."
        )

@router.post("/trips/{trip_id}/start-conversation", response_model=MessageThreadResponse)
async def start_trip_conversation(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> MessageThreadResponse:
    """
    Start a conversation for a trip (driver or passenger can initiate).
    """
    try:
        # Verify user is related to the trip
        trip_access = await messaging_crud.verify_trip_access(
            session=db,
            trip_id=trip_id,
            user_id=current_user.id
        )
        if not trip_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to start a conversation for this trip."
            )
        
        # Check if thread already exists
        existing_thread = await messaging_crud.get_trip_thread(
            session=db,
            trip_id=trip_id
        )
        if existing_thread:
            return existing_thread
        
        # Create new thread
        thread = await messaging_crud.create_trip_thread(
            session=db,
            trip_id=trip_id,
            initiator_id=current_user.id
        )
        
        logger.info(f"Trip conversation started by user {current_user.id} for trip {trip_id}")
        return thread
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting conversation for trip {trip_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while starting the conversation."
        )

@router.post("/users/{user_id}/direct-message", response_model=MessageThreadResponse)
async def start_direct_conversation(
    user_id: UUID,
    message_data: MessageCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> MessageThreadResponse:
    """
    Start a direct conversation with another user.
    Only allowed between users who have a trip connection.
    """
    try:
        if user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot start a conversation with yourself."
            )
        
        # Verify users have a trip connection
        has_connection = await messaging_crud.verify_user_connection(
            session=db,
            user1_id=current_user.id,
            user2_id=user_id
        )
        if not has_connection:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only message users you have traveled or are traveling with."
            )
        
        # Check if direct thread already exists
        existing_thread = await messaging_crud.get_direct_thread(
            session=db,
            user1_id=current_user.id,
            user2_id=user_id
        )
        if existing_thread:
            # Send message in existing thread
            message = await messaging_crud.create_message(
                session=db,
                thread_id=existing_thread.id,
                sender_id=current_user.id,
                message_data=message_data
            )
            return existing_thread
        
        # Create new direct thread with initial message
        thread = await messaging_crud.create_direct_thread(
            session=db,
            user1_id=current_user.id,
            user2_id=user_id,
            initial_message=message_data
        )
        
        logger.info(f"Direct conversation started between users {current_user.id} and {user_id}")
        return thread
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting direct conversation with user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while starting the conversation."
        )

@router.get("/unread-count")
async def get_unread_message_count(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get count of unread messages for the current user.
    """
    try:
        count = await messaging_crud.get_unread_message_count(
            session=db,
            user_id=current_user.id
        )
        return {"unread_count": count}
    except Exception as e:
        logger.error(f"Error getting unread count for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while getting unread message count."
        )

@router.patch("/threads/{thread_id}/mark-read")
async def mark_thread_as_read(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Mark all messages in a thread as read.
    """
    try:
        # Verify user has access to thread
        thread = await messaging_crud.get_thread_with_access_check(
            session=db,
            thread_id=thread_id,
            user_id=current_user.id
        )
        if not thread:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message thread not found or you don't have access to it."
            )
        
        marked_count = await messaging_crud.mark_messages_as_read(
            session=db,
            thread_id=thread_id,
            user_id=current_user.id
        )
        
        return {"messages_marked_read": marked_count}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking thread {thread_id} as read: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while marking messages as read."
        )

@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Delete a message (only sender can delete their own messages).
    """
    try:
        success = await messaging_crud.delete_message(
            session=db,
            message_id=message_id,
            user_id=current_user.id
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found or you don't have permission to delete it."
            )
        
        logger.info(f"Message {message_id} deleted by user {current_user.id}")
        return {"message": "Message deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting message {message_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the message."
        )

@router.get("/threads/{thread_id}/participants")
async def get_thread_participants(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get all participants in a message thread.
    """
    try:
        # Verify user has access to thread
        thread = await messaging_crud.get_thread_with_access_check(
            session=db,
            thread_id=thread_id,
            user_id=current_user.id
        )
        if not thread:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message thread not found or you don't have access to it."
            )
        
        participants = await messaging_crud.get_thread_participants(
            session=db,
            thread_id=thread_id
        )
        
        return {"participants": participants}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting participants for thread {thread_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving thread participants."
        )