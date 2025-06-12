# File: crud/messaging_crud.py

import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError

from models import (
    MessageThread, Message, ThreadParticipant, User, Trip, Booking, 
    MessageType, BookingStatus, TripStatus
)
from schemas import MessageCreate

logger = logging.getLogger(__name__)

async def get_user_threads(
    session: AsyncSession,
    user_id: UUID,
    skip: int = 0,
    limit: int = 20
) -> List[MessageThread]:
    """Get all message threads for a user with eager loading."""
    try:
        result = await session.execute(
            select(MessageThread)
            .join(ThreadParticipant)
            .options(
                selectinload(MessageThread.trip).options(
                    selectinload(Trip.driver),
                    selectinload(Trip.car)
                ),
                selectinload(MessageThread.messages.and_(
                    Message.created_at >= func.now() - func.interval('7 days')
                )).options(
                    selectinload(Message.sender),
                    selectinload(Message.receiver)
                ).limit(5),  # Last 5 messages per thread
                selectinload(MessageThread.participants).options(
                    selectinload(ThreadParticipant.user)
                )
            )
            .where(ThreadParticipant.user_id == user_id)
            .order_by(MessageThread.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        threads = result.scalars().all()
        logger.info(f"Found {len(threads)} message threads for user {user_id}")
        return threads
    except Exception as e:
        logger.error(f"Error fetching message threads for user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving message threads."
        )

async def get_thread_with_messages(
    session: AsyncSession,
    thread_id: UUID,
    user_id: UUID
) -> Optional[MessageThread]:
    """Get a specific thread with all messages if user has access."""
    try:
        # Verify user access first
        access_result = await session.execute(
            select(ThreadParticipant)
            .where(
                and_(
                    ThreadParticipant.thread_id == thread_id,
                    ThreadParticipant.user_id == user_id
                )
            )
        )
        if not access_result.scalar_one_or_none():
            return None
        
        # Get thread with messages
        result = await session.execute(
            select(MessageThread)
            .options(
                selectinload(MessageThread.trip).options(
                    selectinload(Trip.driver),
                    selectinload(Trip.car)
                ),
                selectinload(MessageThread.messages).options(
                    selectinload(Message.sender),
                    selectinload(Message.receiver)
                ),
                selectinload(MessageThread.participants).options(
                    selectinload(ThreadParticipant.user)
                )
            )
            .where(MessageThread.id == thread_id)
        )
        thread = result.scalar_one_or_none()
        
        if thread:
            logger.info(f"Retrieved thread {thread_id} with {len(thread.messages)} messages")
        
        return thread
    except Exception as e:
        logger.error(f"Error fetching thread {thread_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving message thread."
        )

async def get_thread_with_access_check(
    session: AsyncSession,
    thread_id: UUID,
    user_id: UUID
) -> Optional[MessageThread]:
    """Get a thread if user has access to it."""
    try:
        result = await session.execute(
            select(MessageThread)
            .join(ThreadParticipant)
            .where(
                and_(
                    MessageThread.id == thread_id,
                    ThreadParticipant.user_id == user_id
                )
            )
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking access to thread {thread_id}: {e}", exc_info=True)
        return None

async def create_message(
    session: AsyncSession,
    thread_id: UUID,
    sender_id: UUID,
    message_data: MessageCreate
) -> Message:
    """Create a new message in a thread."""
    try:
        message = Message(
            thread_id=thread_id,
            sender_id=sender_id,
            receiver_id=message_data.receiver_id,
            message_type=message_data.message_type,
            content=message_data.content,
            metadata=message_data.metadata
        )
        
        session.add(message)
        await session.flush()
        await session.refresh(message)
        
        # Eager load sender and receiver
        result = await session.execute(
            select(Message)
            .options(
                selectinload(Message.sender),
                selectinload(Message.receiver)
            )
            .where(Message.id == message.id)
        )
        message_with_relations = result.scalar_one()
        
        logger.info(f"Message created in thread {thread_id} by user {sender_id}")
        return message_with_relations
    except Exception as e:
        logger.error(f"Error creating message in thread {thread_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating message."
        )

async def verify_trip_access(
    session: AsyncSession,
    trip_id: UUID,
    user_id: UUID
) -> bool:
    """Verify if user has access to trip (driver or passenger)."""
    try:
        # Check if user is the driver
        driver_result = await session.execute(
            select(Trip)
            .where(and_(Trip.id == trip_id, Trip.driver_id == user_id))
        )
        if driver_result.scalar_one_or_none():
            return True
        
        # Check if user has a booking for this trip
        booking_result = await session.execute(
            select(Booking)
            .where(
                and_(
                    Booking.trip_id == trip_id,
                    Booking.passenger_id == user_id,
                    Booking.status.in_([
                        BookingStatus.CONFIRMED,
                        BookingStatus.CANCELLED_BY_PASSENGER,
                        BookingStatus.CANCELLED_BY_DRIVER
                    ])
                )
            )
        )
        return booking_result.scalar_one_or_none() is not None
    except Exception as e:
        logger.error(f"Error verifying trip access for user {user_id}: {e}", exc_info=True)
        return False

async def get_trip_thread(
    session: AsyncSession,
    trip_id: UUID
) -> Optional[MessageThread]:
    """Get existing thread for a trip."""
    try:
        result = await session.execute(
            select(MessageThread)
            .options(
                selectinload(MessageThread.trip),
                selectinload(MessageThread.participants).options(
                    selectinload(ThreadParticipant.user)
                ),
                selectinload(MessageThread.messages).options(
                    selectinload(Message.sender),
                    selectinload(Message.receiver)
                ).limit(10)
            )
            .where(MessageThread.trip_id == trip_id)
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error getting trip thread for trip {trip_id}: {e}", exc_info=True)
        return None

async def create_trip_thread(
    session: AsyncSession,
    trip_id: UUID,
    initiator_id: UUID
) -> MessageThread:
    """Create a new message thread for a trip."""
    try:
        # Get trip details
        trip_result = await session.execute(
            select(Trip)
            .options(
                selectinload(Trip.driver),
                selectinload(Trip.car)
            )
            .where(Trip.id == trip_id)
        )
        trip = trip_result.scalar_one_or_none()
        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found."
            )
        
        # Create thread
        thread = MessageThread(trip_id=trip_id)
        session.add(thread)
        await session.flush()
        
        # Add participants (driver and all confirmed passengers)
        participants_to_add = set()
        participants_to_add.add(trip.driver_id)
        
        # Get all passengers with confirmed bookings
        bookings_result = await session.execute(
            select(Booking)
            .where(
                and_(
                    Booking.trip_id == trip_id,
                    Booking.status == BookingStatus.CONFIRMED
                )
            )
        )
        bookings = bookings_result.scalars().all()
        for booking in bookings:
            participants_to_add.add(booking.passenger_id)
        
        # Add thread participants
        for user_id in participants_to_add:
            participant = ThreadParticipant(
                thread_id=thread.id,
                user_id=user_id
            )
            session.add(participant)
        
        await session.flush()
        await session.refresh(thread)
        
        # Create initial system message
        initial_message = Message(
            thread_id=thread.id,
            sender_id=initiator_id,
            message_type=MessageType.SYSTEM,
            content=f"Conversation started for trip from {trip.from_location_text} to {trip.to_location_text}",
            metadata={"system_action": "thread_created"}
        )
        session.add(initial_message)
        await session.flush()
        
        # Return thread with all relations
        result = await session.execute(
            select(MessageThread)
            .options(
                selectinload(MessageThread.trip).options(
                    selectinload(Trip.driver),
                    selectinload(Trip.car)
                ),
                selectinload(MessageThread.participants).options(
                    selectinload(ThreadParticipant.user)
                ),
                selectinload(MessageThread.messages).options(
                    selectinload(Message.sender),
                    selectinload(Message.receiver)
                )
            )
            .where(MessageThread.id == thread.id)
        )
        thread_with_relations = result.scalar_one()
        
        logger.info(f"Trip thread created for trip {trip_id} with {len(participants_to_add)} participants")
        return thread_with_relations
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating trip thread for trip {trip_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating trip conversation."
        )

async def verify_user_connection(
    session: AsyncSession,
    user1_id: UUID,
    user2_id: UUID
) -> bool:
    """Verify if two users have a trip connection (past or current)."""
    try:
        # Check if they have been driver/passenger together
        connection_result = await session.execute(
            select(Booking)
            .join(Trip)
            .where(
                or_(
                    and_(Trip.driver_id == user1_id, Booking.passenger_id == user2_id),
                    and_(Trip.driver_id == user2_id, Booking.passenger_id == user1_id)
                )
            )
            .limit(1)
        )
        return connection_result.scalar_one_or_none() is not None
    except Exception as e:
        logger.error(f"Error verifying user connection between {user1_id} and {user2_id}: {e}", exc_info=True)
        return False

async def get_direct_thread(
    session: AsyncSession,
    user1_id: UUID,
    user2_id: UUID
) -> Optional[MessageThread]:
    """Get existing direct thread between two users."""
    try:
        # Direct threads have no trip_id
        result = await session.execute(
            select(MessageThread)
            .join(ThreadParticipant, ThreadParticipant.thread_id == MessageThread.id)
            .options(
                selectinload(MessageThread.participants).options(
                    selectinload(ThreadParticipant.user)
                ),
                selectinload(MessageThread.messages).options(
                    selectinload(Message.sender),
                    selectinload(Message.receiver)
                ).limit(10)
            )
            .where(
                and_(
                    MessageThread.trip_id.is_(None),
                    ThreadParticipant.user_id.in_([user1_id, user2_id])
                )
            )
            .group_by(MessageThread.id)
            .having(func.count(ThreadParticipant.user_id) == 2)
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error getting direct thread between users {user1_id} and {user2_id}: {e}", exc_info=True)
        return None

async def create_direct_thread(
    session: AsyncSession,
    user1_id: UUID,
    user2_id: UUID,
    initial_message: MessageCreate
) -> MessageThread:
    """Create a direct message thread between two users."""
    try:
        # Create thread (no trip_id for direct messages)
        thread = MessageThread()
        session.add(thread)
        await session.flush()
        
        # Add participants
        for user_id in [user1_id, user2_id]:
            participant = ThreadParticipant(
                thread_id=thread.id,
                user_id=user_id
            )
            session.add(participant)
        
        await session.flush()
        
        # Create initial message
        message = Message(
            thread_id=thread.id,
            sender_id=user1_id,
            receiver_id=user2_id,
            message_type=initial_message.message_type,
            content=initial_message.content,
            metadata=initial_message.metadata
        )
        session.add(message)
        await session.flush()
        
        # Return thread with relations
        result = await session.execute(
            select(MessageThread)
            .options(
                selectinload(MessageThread.participants).options(
                    selectinload(ThreadParticipant.user)
                ),
                selectinload(MessageThread.messages).options(
                    selectinload(Message.sender),
                    selectinload(Message.receiver)
                )
            )
            .where(MessageThread.id == thread.id)
        )
        thread_with_relations = result.scalar_one()
        
        logger.info(f"Direct thread created between users {user1_id} and {user2_id}")
        return thread_with_relations
    except Exception as e:
        logger.error(f"Error creating direct thread between users {user1_id} and {user2_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating direct conversation."
        )

async def mark_messages_as_read(
    session: AsyncSession,
    thread_id: UUID,
    user_id: UUID
) -> int:
    """Mark all unread messages in a thread as read for a user."""
    try:
        # Update messages where user is receiver and message is unread
        result = await session.execute(
            update(Message)
            .where(
                and_(
                    Message.thread_id == thread_id,
                    or_(
                        Message.receiver_id == user_id,
                        Message.receiver_id.is_(None)  # Group messages
                    ),
                    Message.sender_id != user_id,  # Don't mark own messages
                    Message.is_read == False
                )
            )
            .values(is_read=True)
        )
        
        # Update participant's last_read_at
        await session.execute(
            update(ThreadParticipant)
            .where(
                and_(
                    ThreadParticipant.thread_id == thread_id,
                    ThreadParticipant.user_id == user_id
                )
            )
            .values(last_read_at=datetime.utcnow())
        )
        
        marked_count = result.rowcount
        logger.info(f"Marked {marked_count} messages as read in thread {thread_id} for user {user_id}")
        return marked_count
    except Exception as e:
        logger.error(f"Error marking messages as read in thread {thread_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error marking messages as read."
        )

async def get_unread_message_count(
    session: AsyncSession,
    user_id: UUID
) -> int:
    """Get count of unread messages for a user."""
    try:
        result = await session.execute(
            select(func.count(Message.id))
            .join(ThreadParticipant, ThreadParticipant.thread_id == Message.thread_id)
            .where(
                and_(
                    ThreadParticipant.user_id == user_id,
                    or_(
                        Message.receiver_id == user_id,
                        Message.receiver_id.is_(None)  # Group messages
                    ),
                    Message.sender_id != user_id,
                    Message.is_read == False
                )
            )
        )
        count = result.scalar() or 0
        logger.info(f"User {user_id} has {count} unread messages")
        return count
    except Exception as e:
        logger.error(f"Error getting unread count for user {user_id}: {e}", exc_info=True)
        return 0

async def delete_message(
    session: AsyncSession,
    message_id: UUID,
    user_id: UUID
) -> bool:
    """Delete a message (only sender can delete)."""
    try:
        # Verify user owns the message
        message_result = await session.execute(
            select(Message)
            .where(
                and_(
                    Message.id == message_id,
                    Message.sender_id == user_id
                )
            )
        )
        message = message_result.scalar_one_or_none()
        if not message:
            return False
        
        await session.delete(message)
        await session.flush()
        
        logger.info(f"Message {message_id} deleted by user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting message {message_id}: {e}", exc_info=True)
        return False

async def add_participant_to_thread(
    session: AsyncSession,
    thread_id: UUID,
    user_id: UUID
) -> bool:
    """Add a new participant to a thread (for when new passengers join)."""
    try:
        # Check if participant already exists
        existing_result = await session.execute(
            select(ThreadParticipant)
            .where(
                and_(
                    ThreadParticipant.thread_id == thread_id,
                    ThreadParticipant.user_id == user_id
                )
            )
        )
        if existing_result.scalar_one_or_none():
            return True  # Already a participant
        
        participant = ThreadParticipant(
            thread_id=thread_id,
            user_id=user_id
        )
        session.add(participant)
        await session.flush()
        
        # Add system message about new participant
        system_message = Message(
            thread_id=thread_id,
            sender_id=user_id,
            message_type=MessageType.SYSTEM,
            content="A new passenger has joined the conversation",
            metadata={"system_action": "participant_added", "user_id": str(user_id)}
        )
        session.add(system_message)
        await session.flush()
        
        logger.info(f"User {user_id} added to thread {thread_id}")
        return True
    except Exception as e:
        logger.error(f"Error adding participant {user_id} to thread {thread_id}: {e}", exc_info=True)
        return False

async def get_thread_participants(
    session: AsyncSession,
    thread_id: UUID
) -> List[User]:
    """Get all participants in a thread."""
    try:
        result = await session.execute(
            select(User)
            .join(ThreadParticipant)
            .where(ThreadParticipant.thread_id == thread_id)
            .order_by(User.full_name)
        )
        participants = result.scalars().all()
        logger.info(f"Found {len(participants)} participants in thread {thread_id}")
        return participants
    except Exception as e:
        logger.error(f"Error getting participants for thread {thread_id}: {e}", exc_info=True)
        return []

async def remove_participant_from_thread(
    session: AsyncSession,
    thread_id: UUID,
    user_id: UUID,
    removed_by_id: UUID
) -> bool:
    """Remove a participant from a thread."""
    try:
        # Remove participant
        participant_result = await session.execute(
            select(ThreadParticipant)
            .where(
                and_(
                    ThreadParticipant.thread_id == thread_id,
                    ThreadParticipant.user_id == user_id
                )
            )
        )
        participant = participant_result.scalar_one_or_none()
        if not participant:
            return False
        
        await session.delete(participant)
        
        # Add system message about removal
        system_message = Message(
            thread_id=thread_id,
            sender_id=removed_by_id,
            message_type=MessageType.SYSTEM,
            content=f"A participant has left the conversation",
            metadata={"system_action": "participant_removed", "user_id": str(user_id)}
        )
        session.add(system_message)
        await session.flush()
        
        logger.info(f"User {user_id} removed from thread {thread_id} by {removed_by_id}")
        return True
    except Exception as e:
        logger.error(f"Error removing participant {user_id} from thread {thread_id}: {e}", exc_info=True)
        return False