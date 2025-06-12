# File: routers/bookings.py (Enhanced with comprehensive booking management)

import logging
from typing import Annotated, List, Optional
from uuid import UUID
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.dependencies import get_current_active_user, get_current_admin_user
from crud import (
    booking_crud, notifications_crud, ratings_crud, messaging_crud, 
    emergency_crud, negotiations_crud
)
from database import get_db
from models import User, UserRole, Booking, Trip, TripStatus, BookingStatus
from schemas import BookingCreate, BookingResponse, BookingUpdate

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/bookings",
    tags=["bookings"]
)

@router.post(
    "/",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new booking",
    description="Create a new booking for a trip with enhanced features including negotiated pricing support."
)
async def create_booking(
    booking_in: BookingCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> BookingResponse:
    """
    Create a new booking with enhanced features.
    Now supports negotiated pricing, automatic messaging, and safety notifications.
    """
    if current_user.role != UserRole.PASSENGER:
        logger.warning(f"User {current_user.id} attempted to create a booking without passenger role")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only passengers can create bookings."
        )
    
    try:
        booking_id: Optional[UUID] = None
        async with db.begin_nested():
            booking = await booking_crud.create_passenger_booking(
                session=db,
                booking_in=booking_in,
                passenger_id=current_user.id
            )
            booking_id = booking.id
            logger.info(f"Successfully created booking {booking.id} for passenger {current_user.id}")
        
        # After transaction commits, re-fetch booking with relationships
        if booking_id:
            booking_result = await db.execute(
                select(Booking)
                .options(
                    selectinload(Booking.trip).options(
                        selectinload(Trip.driver),
                        selectinload(Trip.car)
                    ),
                    selectinload(Booking.passenger)
                )
                .where(Booking.id == booking_id)
            )
            booking_with_relations = booking_result.scalar_one_or_none()
            
            if not booking_with_relations:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to retrieve created booking."
                )
            
            # Enhanced post-booking actions
            await post_booking_actions(db, booking_with_relations, current_user.id)
            
            return booking_with_relations
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Booking creation failed."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in create_booking: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

async def post_booking_actions(
    db: AsyncSession,
    booking: Booking,
    passenger_id: UUID
):
    """Enhanced post-booking actions with new features."""
    try:
        # 1. Send booking confirmation notifications (enhanced)
        await notifications_crud.send_booking_confirmation(
            session=db,
            booking_id=booking.id
        )
        
        # 2. Auto-create trip conversation if not exists
        try:
            await messaging_crud.create_trip_thread(
                session=db,
                trip_id=booking.trip_id,
                initiator_id=passenger_id
            )
        except Exception as e:
            # Thread might already exist, that's ok
            logger.info(f"Trip thread might already exist for trip {booking.trip_id}: {e}")
        
        # 3. Add passenger to existing trip conversation
        try:
            thread = await messaging_crud.get_trip_thread(
                session=db,
                trip_id=booking.trip_id
            )
            if thread:
                await messaging_crud.add_participant_to_thread(
                    session=db,
                    thread_id=thread.id,
                    user_id=passenger_id
                )
        except Exception as e:
            logger.warning(f"Could not add passenger to trip thread: {e}")
        
        # 4. Send safety reminder to passenger
        safety_notification = await notifications_crud.create_notification(
            session=db,
            user_id=passenger_id,
            notification_type="push",
            title="🛡️ Travel Safety Reminder",
            content="Remember to share your trip with emergency contacts and use our safety features during your journey.",
            data={
                "booking_id": str(booking.id),
                "trip_id": str(booking.trip_id),
                "safety_reminder": True,
                "action": "view_safety_features"
            }
        )
        
        if safety_notification:
            await notifications_crud.queue_for_sending(db, safety_notification.id)
        
        logger.info(f"Post-booking actions completed for booking {booking.id}")
        
    except Exception as e:
        logger.error(f"Error in post-booking actions: {e}", exc_info=True)

@router.get(
    "/my-bookings",
    response_model=List[BookingResponse],
    summary="Get my bookings",
    description="Get all bookings made by the authenticated passenger with enhanced filtering."
)
async def get_my_bookings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return")] = 20,
    status_filter: Optional[str] = Query(default=None, regex="^(confirmed|cancelled_by_passenger|cancelled_by_driver)$"),
    upcoming_only: bool = Query(default=False, description="Show only upcoming trips")
) -> List[BookingResponse]:
    """
    Get bookings with enhanced filtering options.
    """
    if current_user.role != UserRole.PASSENGER:
        logger.warning(f"User {current_user.id} attempted to view bookings without passenger role")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only passengers can view their bookings."
        )
    
    try:
        bookings = await booking_crud.get_passenger_bookings(
            session=db,
            passenger_id=current_user.id,
            skip=skip,
            limit=limit
        )
        
        # Apply additional filtering
        filtered_bookings = bookings
        
        if status_filter:
            if status_filter == "confirmed":
                filtered_bookings = [b for b in bookings if b.status == BookingStatus.CONFIRMED]
            elif status_filter == "cancelled_by_passenger":
                filtered_bookings = [b for b in bookings if b.status == BookingStatus.CANCELLED_BY_PASSENGER]
            elif status_filter == "cancelled_by_driver":
                filtered_bookings = [b for b in bookings if b.status == BookingStatus.CANCELLED_BY_DRIVER]
        
        if upcoming_only:
            now = datetime.utcnow()
            filtered_bookings = [b for b in filtered_bookings if b.trip.departure_datetime > now]
        
        logger.info(f"Successfully retrieved {len(filtered_bookings)} bookings for passenger {current_user.id}")
        return filtered_bookings
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_my_bookings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.get(
    "/{booking_id}",
    response_model=BookingResponse,
    summary="Get booking details",
    description="Get detailed information about a specific booking with enhanced data."
)
async def get_booking(
    booking_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> BookingResponse:
    """
    Get detailed booking information.
    """
    if current_user.role != UserRole.PASSENGER:
        logger.warning(f"User {current_user.id} attempted to view booking {booking_id} without passenger role")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only passengers can view booking details."
        )
    
    try:
        booking = await booking_crud.get_booking_by_id_and_passenger(
            session=db,
            booking_id=booking_id,
            passenger_id=current_user.id
        )
        if not booking:
            logger.warning(f"Booking {booking_id} not found or not owned by passenger {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found or you do not have permission to view it."
            )
        return booking
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_booking: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

@router.patch("/{booking_id}", response_model=BookingResponse)
async def update_booking(
    booking_id: UUID,
    booking_update: BookingUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> BookingResponse:
    """
    Update booking details (limited fields allowed).
    Passengers can update pickup/dropoff locations and special requests.
    """
    if current_user.role != UserRole.PASSENGER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only passengers can update their bookings."
        )
    
    try:
        # Get booking
        booking = await booking_crud.get_booking_by_id_and_passenger(
            session=db,
            booking_id=booking_id,
            passenger_id=current_user.id
        )
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found or you do not have permission to update it."
            )
        
        # Check if booking can be updated
        if booking.status != BookingStatus.CONFIRMED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only confirmed bookings can be updated."
            )
        
        # Check if trip hasn't started
        if booking.trip.departure_datetime <= datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot update booking for trips that have already started."
            )
        
        # Update allowed fields
        update_data = booking_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(booking, field):
                setattr(booking, field, value)
        
        db.add(booking)
        await db.flush()
        await db.refresh(booking)
        
        # Notify driver of changes
        if update_data:
            await notify_driver_of_booking_update(db, booking, update_data)
        
        logger.info(f"Booking {booking_id} updated by passenger {current_user.id}")
        return booking
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating booking: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the booking."
        )

async def notify_driver_of_booking_update(
    db: AsyncSession,
    booking: Booking,
    update_data: dict
):
    """Notify driver when passenger updates booking details."""
    try:
        changes = []
        if "pickup_location" in update_data:
            changes.append(f"Pickup location: {update_data['pickup_location']}")
        if "dropoff_location" in update_data:
            changes.append(f"Dropoff location: {update_data['dropoff_location']}")
        if "special_requests" in update_data:
            changes.append(f"Special requests: {update_data['special_requests']}")
        
        if changes:
            notification = await notifications_crud.create_notification(
                session=db,
                user_id=booking.trip.driver_id,
                notification_type="push",
                title="📝 Booking Updated",
                content=f"{booking.passenger.full_name} updated their booking details: {'; '.join(changes)}",
                data={
                    "booking_id": str(booking.id),
                    "trip_id": str(booking.trip_id),
                    "passenger_id": str(booking.passenger_id),
                    "update_type": "booking_details",
                    "action": "view_booking"
                }
            )
            
            if notification:
                await notifications_crud.queue_for_sending(db, notification.id)
        
        logger.info(f"Driver notified of booking update for booking {booking.id}")
        
    except Exception as e:
        logger.error(f"Error notifying driver of booking update: {e}", exc_info=True)

@router.post(
    "/{booking_id}/cancel",
    response_model=BookingResponse,
    summary="Cancel my booking",
    description="Cancel a booking with enhanced notification and refund handling."
)
async def cancel_my_booking(
    booking_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cancellation_reason: Optional[str] = Query(default=None, max_length=500)
) -> BookingResponse:
    """
    Cancel a booking with enhanced features.
    """
    if current_user.role != UserRole.PASSENGER:
        logger.warning(f"User {current_user.id} attempted to cancel booking {booking_id} without passenger role")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only passengers can cancel their bookings."
        )
    
    try:
        cancelled_booking_id: Optional[UUID] = None
        async with db.begin_nested():
            booking = await booking_crud.get_booking_by_id_and_passenger(
                session=db,
                booking_id=booking_id,
                passenger_id=current_user.id
            )
            if not booking:
                logger.warning(f"Booking {booking_id} not found or not owned by passenger {current_user.id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found or you do not have permission to cancel it."
                )
            
            cancelled_booking = await booking_crud.cancel_passenger_booking(
                session=db,
                booking_to_cancel=booking
            )
            cancelled_booking_id = cancelled_booking.id
            logger.info(f"Successfully cancelled booking {booking_id} for passenger {current_user.id}")
        
        # Re-fetch with relationships
        if cancelled_booking_id:
            booking_result = await db.execute(
                select(Booking)
                .options(
                    selectinload(Booking.trip).options(
                        selectinload(Trip.driver),
                        selectinload(Trip.car)
                    ),
                    selectinload(Booking.passenger)
                )
                .where(Booking.id == cancelled_booking_id)
            )
            booking_with_relations = booking_result.scalar_one_or_none()
            
            if not booking_with_relations:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to retrieve cancelled booking."
                )
            
            # Enhanced post-cancellation actions
            await post_cancellation_actions(db, booking_with_relations, cancellation_reason)
            
            return booking_with_relations
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Booking cancellation failed."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in cancel_my_booking: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred."
        )

async def post_cancellation_actions(
    db: AsyncSession,
    booking: Booking,
    cancellation_reason: Optional[str]
):
    """Enhanced post-cancellation actions."""
    try:
        # 1. Notify driver of cancellation
        notification_content = f"{booking.passenger.full_name} cancelled their booking for your trip to {booking.trip.to_location_text}"
        if cancellation_reason:
            notification_content += f". Reason: {cancellation_reason}"
        
        driver_notification = await notifications_crud.create_notification(
            session=db,
            user_id=booking.trip.driver_id,
            notification_type="push",
            title="❌ Booking Cancelled",
            content=notification_content,
            data={
                "booking_id": str(booking.id),
                "trip_id": str(booking.trip_id),
                "passenger_id": str(booking.passenger_id),
                "cancellation_reason": cancellation_reason,
                "seats_freed": booking.seats_booked,
                "action": "view_trip"
            }
        )
        
        if driver_notification:
            await notifications_crud.queue_for_sending(db, driver_notification.id)
        
        # 2. Send message to trip chat about cancellation
        try:
            thread = await messaging_crud.get_trip_thread(
                session=db,
                trip_id=booking.trip_id
            )
            if thread:
                system_message = await messaging_crud.create_message(
                    session=db,
                    thread_id=thread.id,
                    sender_id=booking.passenger_id,
                    message_data={
                        "content": f"{booking.passenger.full_name} has cancelled their booking ({booking.seats_booked} seat{'s' if booking.seats_booked > 1 else ''} now available)",
                        "message_type": "system",
                        "metadata": {
                            "system_action": "booking_cancelled",
                            "seats_freed": booking.seats_booked
                        }
                    }
                )
        except Exception as e:
            logger.warning(f"Could not send cancellation message to trip chat: {e}")
        
        # 3. Check if trip can accommodate waitlisted passengers
        await check_waitlist_for_freed_seats(db, booking.trip_id, booking.seats_booked)
        
        logger.info(f"Post-cancellation actions completed for booking {booking.id}")
        
    except Exception as e:
        logger.error(f"Error in post-cancellation actions: {e}", exc_info=True)

async def check_waitlist_for_freed_seats(
    db: AsyncSession,
    trip_id: UUID,
    freed_seats: int
):
    """Check if any waitlisted passengers can now be accommodated."""
    try:
        # This would involve implementing a waitlist system
        # For now, just log the opportunity
        logger.info(f"Trip {trip_id} now has {freed_seats} additional seats available")
        
        # In a real implementation, this would:
        # 1. Check for waitlisted passengers for this trip
        # 2. Notify them about availability
        # 3. Allow quick booking with time limit
        
    except Exception as e:
        logger.error(f"Error checking waitlist: {e}", exc_info=True)

# --- ENHANCED BOOKING FEATURES ---

@router.get("/{booking_id}/trip-chat")
async def get_booking_trip_chat(
    booking_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get the trip chat thread for a booking.
    Direct access to communication with driver and other passengers.
    """
    try:
        # Verify booking ownership
        booking = await booking_crud.get_booking_by_id_and_passenger(
            session=db,
            booking_id=booking_id,
            passenger_id=current_user.id
        )
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found or you don't have permission to access it."
            )
        
        # Get trip thread
        thread = await messaging_crud.get_trip_thread(
            session=db,
            trip_id=booking.trip_id
        )
        
        if not thread:
            # Create thread if it doesn't exist
            thread = await messaging_crud.create_trip_thread(
                session=db,
                trip_id=booking.trip_id,
                initiator_id=current_user.id
            )
        
        return {
            "booking_id": booking_id,
            "trip_id": booking.trip_id,
            "thread_id": thread.id,
            "participants_count": len(thread.participants),
            "message_count": len(thread.messages)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting booking trip chat: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while accessing trip chat."
        )

@router.get("/{booking_id}/rating-eligibility")
async def check_booking_rating_eligibility(
    booking_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Check if the user can rate others for this booking.
    Shows who can be rated after trip completion.
    """
    try:
        # Verify booking ownership
        booking = await booking_crud.get_booking_by_id_and_passenger(
            session=db,
            booking_id=booking_id,
            passenger_id=current_user.id
        )
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found or you don't have permission to access it."
            )
        
        rating_eligibility = await ratings_crud.can_rate_booking(
            session=db,
            booking_id=booking_id,
            user_id=current_user.id
        )
        
        return rating_eligibility
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking rating eligibility: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while checking rating eligibility."
        )

@router.post("/{booking_id}/share-with-emergency-contacts")
async def share_booking_with_emergency_contacts(
    booking_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Share booking details with emergency contacts for safety.
    Sends trip information to all emergency contacts.
    """
    try:
        # Verify booking ownership
        booking = await booking_crud.get_booking_by_id_and_passenger(
            session=db,
            booking_id=booking_id,
            passenger_id=current_user.id
        )
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found or you don't have permission to access it."
            )
        
        # Share with emergency contacts
        success = await emergency_crud.share_trip_location(
            session=db,
            trip_id=booking.trip_id,
            user_id=current_user.id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No emergency contacts found or unable to share trip information."
            )
        
        logger.info(f"Booking {booking_id} shared with emergency contacts by user {current_user.id}")
        return {"message": "Trip details shared with your emergency contacts"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sharing booking with emergency contacts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while sharing trip information."
        )

@router.get("/{booking_id}/price-breakdown")
async def get_booking_price_breakdown(
    booking_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get detailed price breakdown for a booking.
    Shows base price, negotiated discounts, fees, etc.
    """
    try:
        # Verify booking ownership
        booking = await booking_crud.get_booking_by_id_and_passenger(
            session=db,
            booking_id=booking_id,
            passenger_id=current_user.id
        )
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found or you don't have permission to access it."
            )
        
        # Check if this booking came from a negotiation
        negotiation = None
        if booking.payment_method == "negotiated":
            # Find the negotiation that led to this booking
            negotiations = await negotiations_crud.get_trip_negotiations(
                session=db,
                trip_id=booking.trip_id,
                user_id=booking.trip.driver_id  # Need driver permission to access negotiations
            )
            negotiation = next(
                (n for n in negotiations if n.passenger_id == current_user.id and n.status.value == "accepted"),
                None
            )
        
        price_breakdown = {
            "booking_id": booking_id,
            "seats_booked": booking.seats_booked,
            "base_calculation": {
                "original_price_per_seat": booking.trip.price_per_seat,
                "seats": booking.seats_booked,
                "subtotal": booking.trip.price_per_seat * booking.seats_booked
            },
            "final_total": booking.total_price,
            "payment_method": booking.payment_method
        }
        
        if negotiation:
            discount_amount = (booking.trip.price_per_seat * booking.seats_booked) - booking.total_price
            discount_percentage = (discount_amount / (booking.trip.price_per_seat * booking.seats_booked)) * 100
            
            price_breakdown["negotiation_details"] = {
                "was_negotiated": True,
                "original_total": booking.trip.price_per_seat * booking.seats_booked,
                "negotiated_price_per_seat": negotiation.final_price,
                "discount_amount": discount_amount,
                "discount_percentage": round(discount_percentage, 1),
                "negotiation_message": negotiation.message
            }
        else:
            price_breakdown["negotiation_details"] = {
                "was_negotiated": False
            }
        
        return price_breakdown
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting price breakdown: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving price breakdown."
        )

@router.post("/{booking_id}/request-modification")
async def request_booking_modification(
    booking_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    modification_request: str = Query(..., max_length=500)
) -> dict:
    """
    Request a modification to the booking from the driver.
    For changes that require driver approval (time, route, etc.).
    """
    try:
        # Verify booking ownership
        booking = await booking_crud.get_booking_by_id_and_passenger(
            session=db,
            booking_id=booking_id,
            passenger_id=current_user.id
        )
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found or you don't have permission to access it."
            )
        
        if booking.status != BookingStatus.CONFIRMED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only request modifications for confirmed bookings."
            )
        
        # Send modification request to driver
        notification = await notifications_crud.create_notification(
            session=db,
            user_id=booking.trip.driver_id,
            notification_type="push",
            title="📝 Modification Request",
            content=f"{booking.passenger.full_name} requests a modification to their booking: {modification_request}",
            data={
                "booking_id": str(booking_id),
                "trip_id": str(booking.trip_id),
                "passenger_id": str(current_user.id),
                "modification_request": modification_request,
                "request_type": "booking_modification",
                "action": "review_request"
            }
        )
        
        if notification:
            await notifications_crud.queue_for_sending(db, notification.id)
        
        # Send message to trip chat
        try:
            thread = await messaging_crud.get_trip_thread(
                session=db,
                trip_id=booking.trip_id
            )
            if thread:
                await messaging_crud.create_message(
                    session=db,
                    thread_id=thread.id,
                    sender_id=current_user.id,
                    message_data={
                        "content": f"Modification request: {modification_request}",
                        "message_type": "text",
                        "metadata": {
                            "message_type": "modification_request",
                            "booking_id": str(booking_id)
                        }
                    }
                )
        except Exception as e:
            logger.warning(f"Could not send modification request to trip chat: {e}")
        
        logger.info(f"Modification request sent for booking {booking_id} by user {current_user.id}")
        return {"message": "Modification request sent to driver"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error requesting booking modification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while sending modification request."
        )

# --- BOOKING ANALYTICS ---

@router.get("/my-analytics")
async def get_my_booking_analytics(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get booking analytics for the current passenger.
    Shows travel patterns, spending, and preferences.
    """
    try:
        if current_user.role != UserRole.PASSENGER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Booking analytics are only available for passengers."
            )
        
        # Get all bookings for analysis
        all_bookings = await booking_crud.get_passenger_bookings(
            session=db,
            passenger_id=current_user.id,
            skip=0,
            limit=1000  # Get all for analytics
        )
        
        if not all_bookings:
            return {
                "total_bookings": 0,
                "message": "No bookings found for analysis"
            }
        
        # Calculate analytics
        total_bookings = len(all_bookings)
        confirmed_bookings = [b for b in all_bookings if b.status == BookingStatus.CONFIRMED]
        cancelled_bookings = [b for b in all_bookings if b.status in [BookingStatus.CANCELLED_BY_PASSENGER, BookingStatus.CANCELLED_BY_DRIVER]]
        
        total_spent = sum(b.total_price for b in confirmed_bookings)
        total_seats_booked = sum(b.seats_booked for b in confirmed_bookings)
        
        # Route analysis
        route_frequency = {}
        for booking in confirmed_bookings:
            route = f"{booking.trip.from_location_text} → {booking.trip.to_location_text}"
            route_frequency[route] = route_frequency.get(route, 0) + 1
        
        # Monthly spending
        monthly_spending = {}
        for booking in confirmed_bookings:
            month_key = booking.booking_time.strftime("%Y-%m")
            monthly_spending[month_key] = monthly_spending.get(month_key, 0) + float(booking.total_price)
        
        analytics = {
            "user_id": current_user.id,
            "period": "all_time",
            "summary": {
                "total_bookings": total_bookings,
                "confirmed_bookings": len(confirmed_bookings),
                "cancelled_bookings": len(cancelled_bookings),
                "cancellation_rate": round((len(cancelled_bookings) / total_bookings * 100), 1) if total_bookings > 0 else 0,
                "total_spent": float(total_spent),
                "average_booking_value": float(total_spent / len(confirmed_bookings)) if confirmed_bookings else 0,
                "total_seats_booked": total_seats_booked
            },
            "travel_patterns": {
                "most_frequent_routes": sorted(route_frequency.items(), key=lambda x: x[1], reverse=True)[:5],
                "average_seats_per_booking": total_seats_booked / len(confirmed_bookings) if confirmed_bookings else 0
            },
            "spending_analysis": {
                "monthly_spending": monthly_spending,
                "peak_spending_month": max(monthly_spending.items(), key=lambda x: x[1])[0] if monthly_spending else None
            }
        }
        
        logger.info(f"Booking analytics generated for user {current_user.id}")
        return analytics
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting booking analytics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating booking analytics."
        )

# --- DRIVER BOOKING MANAGEMENT ---

@router.get("/driver/incoming-bookings")
async def get_incoming_bookings_for_driver(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100)
) -> dict:
    """
    Get incoming bookings for driver's trips.
    Shows all bookings made on the driver's trips.
    """
    try:
        if current_user.role != UserRole.DRIVER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only drivers can view incoming bookings."
            )
        
        # Get driver's trips and their bookings
        from crud import trip_crud
        driver_trips = await trip_crud.get_driver_created_trips(
            session=db,
            driver_id=current_user.id,
            skip=0,
            limit=100  # Get many trips for booking analysis
        )
        
        all_bookings = []
        for trip in driver_trips:
            trip_bookings = await booking_crud.get_confirmed_bookings_for_trip(
                session=db,
                trip_id=trip.id
            )
            for booking in trip_bookings:
                # Add trip context to booking
                booking_data = {
                    "booking_id": booking.id,
                    "trip_id": trip.id,
                    "trip_route": f"{trip.from_location_text} → {trip.to_location_text}",
                    "departure_datetime": trip.departure_datetime,
                    "passenger_name": booking.passenger.full_name,
                    "passenger_phone": booking.passenger.phone_number,
                    "seats_booked": booking.seats_booked,
                    "total_price": booking.total_price,
                    "status": booking.status.value,
                    "booking_time": booking.booking_time,
                    "pickup_location": booking.pickup_location,
                    "dropoff_location": booking.dropoff_location,
                    "special_requests": booking.special_requests
                }
                all_bookings.append(booking_data)
        
        # Sort by booking time (most recent first)
        all_bookings.sort(key=lambda x: x["booking_time"], reverse=True)
        
        # Apply pagination
        paginated_bookings = all_bookings[skip:skip + limit]
        
        return {
            "driver_id": current_user.id,
            "total_bookings": len(all_bookings),
            "bookings": paginated_bookings,
            "pagination": {"skip": skip, "limit": limit}
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting incoming bookings for driver: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving incoming bookings."
        )

# --- ADMIN BOOKING MANAGEMENT ---

@router.get("/admin/all-bookings", dependencies=[Depends(get_current_admin_user)])
async def admin_get_all_bookings(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: Optional[str] = Query(default=None),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None)
) -> dict:
    """
    Admin endpoint to view all bookings with filtering.
    """
    try:
        # This would involve comprehensive booking queries with admin-level access
        # For now, return a placeholder structure
        bookings_data = {
            "total_bookings": 0,
            "filtered_bookings": [],
            "filters_applied": {
                "status": status_filter,
                "date_from": date_from,
                "date_to": date_to
            },
            "pagination": {"skip": skip, "limit": limit}
        }
        
        logger.info(f"Admin booking query performed by {current_admin.id}")
        return bookings_data
    except Exception as e:
        logger.error(f"Error in admin booking query: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving booking data."
        )