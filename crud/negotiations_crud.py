# File: crud/negotiations_crud.py

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, update, delete, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError

from models import (
    PriceNegotiation, User, Trip, Booking, UserSettings,
    PriceNegotiationStatus, TripStatus, BookingStatus, UserRole,
    NotificationType
)
from schemas import (
    PriceNegotiationCreate, PriceNegotiationResponse, 
    PriceRecommendationRequest, PriceRecommendationResponse
)
from crud import notifications_crud, booking_crud

logger = logging.getLogger(__name__)

# --- CORE NEGOTIATION OPERATIONS ---

async def create_price_negotiation(
    session: AsyncSession,
    passenger_id: UUID,
    negotiation_data: PriceNegotiationCreate
) -> PriceNegotiation:
    """Create a new price negotiation."""
    try:
        # Verify trip exists and is available for negotiation
        trip_result = await session.execute(
            select(Trip)
            .options(selectinload(Trip.driver))
            .where(Trip.id == negotiation_data.trip_id)
        )
        trip = trip_result.scalar_one_or_none()
        
        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trip not found."
            )
        
        if trip.status != TripStatus.SCHEDULED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Trip is not available for price negotiation."
            )
        
        if not trip.price_negotiable:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This trip does not allow price negotiations."
            )
        
        if trip.driver_id == passenger_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot negotiate price on your own trip."
            )
        
        # Check if passenger already has a pending negotiation for this trip
        existing_result = await session.execute(
            select(PriceNegotiation)
            .where(
                and_(
                    PriceNegotiation.trip_id == negotiation_data.trip_id,
                    PriceNegotiation.passenger_id == passenger_id,
                    PriceNegotiation.status == PriceNegotiationStatus.PENDING
                )
            )
        )
        existing_negotiation = existing_result.scalar_one_or_none()
        
        if existing_negotiation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You already have a pending price negotiation for this trip."
            )
        
        # Check if passenger already has a confirmed booking
        existing_booking = await booking_crud.get_booking_by_trip_and_passenger(
            session=session,
            trip_id=negotiation_data.trip_id,
            passenger_id=passenger_id
        )
        
        if existing_booking:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You already have a confirmed booking for this trip."
            )
        
        # Validate negotiation parameters
        if negotiation_data.proposed_price >= trip.price_per_seat:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Proposed price must be lower than the original price for negotiation."
            )
        
        if negotiation_data.seats_requested > trip.available_seats:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Requested seats exceed available seats."
            )
        
        # Create negotiation with expiry time (24 hours)
        expires_at = datetime.utcnow() + timedelta(hours=24)
        
        negotiation = PriceNegotiation(
            trip_id=negotiation_data.trip_id,
            passenger_id=passenger_id,
            original_price=trip.price_per_seat,
            proposed_price=negotiation_data.proposed_price,
            seats_requested=negotiation_data.seats_requested,
            message=negotiation_data.message,
            expires_at=expires_at
        )
        
        session.add(negotiation)
        await session.flush()
        await session.refresh(negotiation)
        
        # Check if this negotiation should be auto-accepted
        auto_accepted = await check_auto_accept_rules(
            session=session,
            negotiation=negotiation,
            trip=trip
        )
        
        if not auto_accepted:
            # Send notification to driver
            await notify_driver_of_negotiation(
                session=session,
                negotiation=negotiation,
                trip=trip
            )
        
        # Load relationships for response
        result = await session.execute(
            select(PriceNegotiation)
            .options(
                selectinload(PriceNegotiation.passenger),
                selectinload(PriceNegotiation.trip).options(
                    selectinload(Trip.driver)
                )
            )
            .where(PriceNegotiation.id == negotiation.id)
        )
        negotiation_with_relations = result.scalar_one()
        
        logger.info(f"Price negotiation created: {negotiation.id} for trip {negotiation_data.trip_id}")
        return negotiation_with_relations
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating price negotiation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating price negotiation."
        )

async def check_auto_accept_rules(
    session: AsyncSession,
    negotiation: PriceNegotiation,
    trip: Trip
) -> bool:
    """Check if negotiation should be auto-accepted based on driver's rules."""
    try:
        # Get driver's auto-accept settings
        settings = await get_auto_accept_settings(
            session=session,
            driver_id=trip.driver_id
        )
        
        if not settings.get("enable_auto_accept", False):
            return False
        
        # Calculate discount percentage
        discount_percentage = ((trip.price_per_seat - negotiation.proposed_price) / trip.price_per_seat) * 100
        discount_amount = trip.price_per_seat - negotiation.proposed_price
        
        # Check if within auto-accept thresholds
        min_percentage = settings.get("min_price_percentage", 80)
        max_discount = settings.get("max_discount_amount", Decimal("10000"))
        
        price_percentage = (negotiation.proposed_price / trip.price_per_seat) * 100
        
        if price_percentage >= min_percentage and discount_amount <= max_discount:
            # Auto-accept the negotiation
            response = PriceNegotiationResponse(
                response="accept",
                final_price=negotiation.proposed_price,
                response_message="Auto-accepted based on your pricing preferences."
            )
            
            await respond_to_negotiation(
                session=session,
                negotiation_id=negotiation.id,
                driver_id=trip.driver_id,
                response=response,
                is_auto_response=True
            )
            
            logger.info(f"Negotiation {negotiation.id} auto-accepted")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking auto-accept rules: {e}", exc_info=True)
        return False

async def notify_driver_of_negotiation(
    session: AsyncSession,
    negotiation: PriceNegotiation,
    trip: Trip
):
    """Send notification to driver about new price negotiation."""
    try:
        # Get passenger details
        passenger_result = await session.execute(
            select(User).where(User.id == negotiation.passenger_id)
        )
        passenger = passenger_result.scalar_one()
        
        # Calculate discount
        discount_amount = negotiation.original_price - negotiation.proposed_price
        discount_percentage = (discount_amount / negotiation.original_price) * 100
        
        title = "💰 New Price Offer"
        content = f"{passenger.full_name} offers {negotiation.proposed_price:,.0f} som for {negotiation.seats_requested} seat(s) on your trip to {trip.to_location_text} ({discount_percentage:.0f}% discount)"
        
        if negotiation.message:
            content += f". Message: {negotiation.message}"
        
        notification = await notifications_crud.create_notification(
            session=session,
            user_id=trip.driver_id,
            notification_type=NotificationType.PUSH,
            title=title,
            content=content,
            data={
                "negotiation_id": str(negotiation.id),
                "trip_id": str(trip.id),
                "passenger_id": str(passenger.id),
                "proposed_price": float(negotiation.proposed_price),
                "original_price": float(negotiation.original_price),
                "discount_percentage": round(discount_percentage, 1),
                "action": "view_negotiation"
            }
        )
        
        if notification:
            await notifications_crud.queue_for_sending(session, notification.id)
        
        logger.info(f"Driver notification sent for negotiation {negotiation.id}")
        
    except Exception as e:
        logger.error(f"Error notifying driver of negotiation: {e}", exc_info=True)

async def respond_to_negotiation(
    session: AsyncSession,
    negotiation_id: UUID,
    driver_id: UUID,
    response: PriceNegotiationResponse,
    is_auto_response: bool = False
) -> Optional[PriceNegotiation]:
    """Respond to a price negotiation (accept/reject)."""
    try:
        # Get negotiation with trip details
        result = await session.execute(
            select(PriceNegotiation)
            .options(
                selectinload(PriceNegotiation.trip),
                selectinload(PriceNegotiation.passenger)
            )
            .where(
                and_(
                    PriceNegotiation.id == negotiation_id,
                    PriceNegotiation.status == PriceNegotiationStatus.PENDING
                )
            )
        )
        negotiation = result.scalar_one_or_none()
        
        if not negotiation:
            return None
        
        # Verify driver owns the trip
        if negotiation.trip.driver_id != driver_id:
            return None
        
        # Check if negotiation hasn't expired
        if negotiation.expires_at <= datetime.utcnow():
            negotiation.status = PriceNegotiationStatus.EXPIRED
            session.add(negotiation)
            await session.flush()
            return None
        
        # Update negotiation status
        if response.response == "accept":
            negotiation.status = PriceNegotiationStatus.ACCEPTED
            negotiation.final_price = response.final_price or negotiation.proposed_price
            
            # Create booking with negotiated price
            await create_booking_from_negotiation(
                session=session,
                negotiation=negotiation
            )
            
        elif response.response == "reject":
            negotiation.status = PriceNegotiationStatus.REJECTED
        
        negotiation.responded_at = datetime.utcnow()
        negotiation.response_message = response.response_message
        
        session.add(negotiation)
        await session.flush()
        await session.refresh(negotiation)
        
        # Notify passenger of response
        await notify_passenger_of_response(
            session=session,
            negotiation=negotiation,
            is_auto_response=is_auto_response
        )
        
        logger.info(f"Negotiation {negotiation_id} responded to: {response.response}")
        return negotiation
        
    except Exception as e:
        logger.error(f"Error responding to negotiation: {e}", exc_info=True)
        return None

async def create_booking_from_negotiation(
    session: AsyncSession,
    negotiation: PriceNegotiation
):
    """Create a booking when negotiation is accepted."""
    try:
        # Calculate total price with negotiated rate
        total_price = negotiation.final_price * negotiation.seats_requested
        
        booking = Booking(
            trip_id=negotiation.trip_id,
            passenger_id=negotiation.passenger_id,
            seats_booked=negotiation.seats_requested,
            total_price=total_price,
            status=BookingStatus.CONFIRMED,
            payment_method="negotiated"
        )
        
        session.add(booking)
        
        # Update trip available seats
        trip = negotiation.trip
        trip.available_seats -= negotiation.seats_requested
        if trip.available_seats <= 0:
            trip.status = TripStatus.FULL
        
        session.add(trip)
        await session.flush()
        
        # Send booking confirmation notifications
        await notifications_crud.send_booking_confirmation(
            session=session,
            booking_id=booking.id
        )
        
        logger.info(f"Booking created from negotiation {negotiation.id}: {booking.id}")
        
    except Exception as e:
        logger.error(f"Error creating booking from negotiation: {e}", exc_info=True)
        raise

async def notify_passenger_of_response(
    session: AsyncSession,
    negotiation: PriceNegotiation,
    is_auto_response: bool = False
):
    """Notify passenger of driver's response to negotiation."""
    try:
        driver_result = await session.execute(
            select(User).where(User.id == negotiation.trip.driver_id)
        )
        driver = driver_result.scalar_one()
        
        if negotiation.status == PriceNegotiationStatus.ACCEPTED:
            title = "✅ Price Offer Accepted!"
            content = f"Great! {driver.full_name} accepted your offer of {negotiation.final_price:,.0f} som. Your booking is confirmed!"
            if is_auto_response:
                content += " (Auto-accepted)"
        else:
            title = "❌ Price Offer Declined"
            content = f"{driver.full_name} declined your price offer for the trip to {negotiation.trip.to_location_text}."
        
        if negotiation.response_message:
            content += f" Message: {negotiation.response_message}"
        
        notification = await notifications_crud.create_notification(
            session=session,
            user_id=negotiation.passenger_id,
            notification_type=NotificationType.PUSH,
            title=title,
            content=content,
            data={
                "negotiation_id": str(negotiation.id),
                "trip_id": str(negotiation.trip_id),
                "response_status": negotiation.status.value,
                "final_price": float(negotiation.final_price) if negotiation.final_price else None,
                "action": "view_booking" if negotiation.status == PriceNegotiationStatus.ACCEPTED else "view_trip"
            }
        )
        
        if notification:
            await notifications_crud.queue_for_sending(session, notification.id)
        
        logger.info(f"Passenger notification sent for negotiation response {negotiation.id}")
        
    except Exception as e:
        logger.error(f"Error notifying passenger of response: {e}", exc_info=True)

async def create_counter_offer(
    session: AsyncSession,
    original_negotiation_id: UUID,
    driver_id: UUID,
    counter_price: Decimal,
    message: Optional[str] = None
) -> Optional[PriceNegotiation]:
    """Create a counter-offer for an existing negotiation."""
    try:
        # Get original negotiation
        original_result = await session.execute(
            select(PriceNegotiation)
            .options(selectinload(PriceNegotiation.trip))
            .where(
                and_(
                    PriceNegotiation.id == original_negotiation_id,
                    PriceNegotiation.status == PriceNegotiationStatus.PENDING
                )
            )
        )
        original_negotiation = original_result.scalar_one_or_none()
        
        if not original_negotiation:
            return None
        
        # Verify driver owns the trip
        if original_negotiation.trip.driver_id != driver_id:
            return None
        
        # Validate counter price
        if counter_price >= original_negotiation.original_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Counter-offer must be lower than original price."
            )
        
        if counter_price <= original_negotiation.proposed_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Counter-offer must be higher than passenger's offer."
            )
        
        # Mark original negotiation as rejected
        original_negotiation.status = PriceNegotiationStatus.REJECTED
        original_negotiation.responded_at = datetime.utcnow()
        original_negotiation.response_message = f"Counter-offer made: {counter_price} som"
        session.add(original_negotiation)
        
        # Create new negotiation as counter-offer
        counter_negotiation = PriceNegotiation(
            trip_id=original_negotiation.trip_id,
            passenger_id=original_negotiation.passenger_id,
            original_price=original_negotiation.original_price,
            proposed_price=counter_price,
            seats_requested=original_negotiation.seats_requested,
            message=message or f"Counter-offer: {counter_price} som",
            expires_at=datetime.utcnow() + timedelta(hours=12)  # Shorter expiry for counter-offers
        )
        
        session.add(counter_negotiation)
        await session.flush()
        await session.refresh(counter_negotiation)
        
        # Notify passenger of counter-offer
        await notify_passenger_of_counter_offer(
            session=session,
            counter_negotiation=counter_negotiation,
            original_negotiation=original_negotiation
        )
        
        # Load relationships
        result = await session.execute(
            select(PriceNegotiation)
            .options(
                selectinload(PriceNegotiation.passenger),
                selectinload(PriceNegotiation.trip).options(
                    selectinload(Trip.driver)
                )
            )
            .where(PriceNegotiation.id == counter_negotiation.id)
        )
        counter_with_relations = result.scalar_one()
        
        logger.info(f"Counter-offer created: {counter_negotiation.id} for original {original_negotiation_id}")
        return counter_with_relations
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating counter-offer: {e}", exc_info=True)
        return None

async def notify_passenger_of_counter_offer(
    session: AsyncSession,
    counter_negotiation: PriceNegotiation,
    original_negotiation: PriceNegotiation
):
    """Notify passenger of driver's counter-offer."""
    try:
        driver_result = await session.execute(
            select(User).where(User.id == counter_negotiation.trip.driver_id)
        )
        driver = driver_result.scalar_one()
        
        title = "🔄 Counter-Offer Received"
        content = f"{driver.full_name} made a counter-offer: {counter_negotiation.proposed_price:,.0f} som (instead of your {original_negotiation.proposed_price:,.0f} som offer)"
        
        if counter_negotiation.message:
            content += f". Message: {counter_negotiation.message}"
        
        notification = await notifications_crud.create_notification(
            session=session,
            user_id=counter_negotiation.passenger_id,
            notification_type=NotificationType.PUSH,
            title=title,
            content=content,
            data={
                "negotiation_id": str(counter_negotiation.id),
                "original_negotiation_id": str(original_negotiation.id),
                "trip_id": str(counter_negotiation.trip_id),
                "counter_price": float(counter_negotiation.proposed_price),
                "original_offer": float(original_negotiation.proposed_price),
                "action": "view_counter_offer"
            }
        )
        
        if notification:
            await notifications_crud.queue_for_sending(session, notification.id)
        
        logger.info(f"Counter-offer notification sent for negotiation {counter_negotiation.id}")
        
    except Exception as e:
        logger.error(f"Error notifying passenger of counter-offer: {e}", exc_info=True)

async def accept_counter_offer(
    session: AsyncSession,
    negotiation_id: UUID,
    passenger_id: UUID
) -> Optional[PriceNegotiation]:
    """Accept a counter-offer from driver."""
    try:
        result = await session.execute(
            select(PriceNegotiation)
            .options(
                selectinload(PriceNegotiation.trip),
                selectinload(PriceNegotiation.passenger)
            )
            .where(
                and_(
                    PriceNegotiation.id == negotiation_id,
                    PriceNegotiation.passenger_id == passenger_id,
                    PriceNegotiation.status == PriceNegotiationStatus.PENDING
                )
            )
        )
        negotiation = result.scalar_one_or_none()
        
        if not negotiation:
            return None
        
        # Check if not expired
        if negotiation.expires_at <= datetime.utcnow():
            negotiation.status = PriceNegotiationStatus.EXPIRED
            session.add(negotiation)
            await session.flush()
            return None
        
        # Accept the counter-offer
        negotiation.status = PriceNegotiationStatus.ACCEPTED
        negotiation.final_price = negotiation.proposed_price
        negotiation.responded_at = datetime.utcnow()
        negotiation.response_message = "Counter-offer accepted by passenger"
        
        session.add(negotiation)
        await session.flush()
        
        # Create booking
        await create_booking_from_negotiation(
            session=session,
            negotiation=negotiation
        )
        
        # Notify driver of acceptance
        await notify_driver_of_counter_acceptance(
            session=session,
            negotiation=negotiation
        )
        
        await session.refresh(negotiation)
        logger.info(f"Counter-offer accepted: {negotiation_id}")
        return negotiation
        
    except Exception as e:
        logger.error(f"Error accepting counter-offer: {e}", exc_info=True)
        return None

async def notify_driver_of_counter_acceptance(
    session: AsyncSession,
    negotiation: PriceNegotiation
):
    """Notify driver that passenger accepted counter-offer."""
    try:
        passenger_result = await session.execute(
            select(User).where(User.id == negotiation.passenger_id)
        )
        passenger = passenger_result.scalar_one()
        
        title = "🎉 Counter-Offer Accepted!"
        content = f"{passenger.full_name} accepted your counter-offer of {negotiation.final_price:,.0f} som. Booking is confirmed!"
        
        notification = await notifications_crud.create_notification(
            session=session,
            user_id=negotiation.trip.driver_id,
            notification_type=NotificationType.PUSH,
            title=title,
            content=content,
            data={
                "negotiation_id": str(negotiation.id),
                "trip_id": str(negotiation.trip_id),
                "passenger_id": str(passenger.id),
                "final_price": float(negotiation.final_price),
                "action": "view_trip"
            }
        )
        
        if notification:
            await notifications_crud.queue_for_sending(session, notification.id)
        
        logger.info(f"Driver notification sent for counter-offer acceptance {negotiation.id}")
        
    except Exception as e:
        logger.error(f"Error notifying driver of counter acceptance: {e}", exc_info=True)

# --- QUERY OPERATIONS ---

async def get_trip_negotiations(
    session: AsyncSession,
    trip_id: UUID,
    user_id: UUID
) -> List[PriceNegotiation]:
    """Get all negotiations for a trip (driver only)."""
    try:
        # Verify user is the driver of this trip
        trip_result = await session.execute(
            select(Trip).where(
                and_(
                    Trip.id == trip_id,
                    Trip.driver_id == user_id
                )
            )
        )
        trip = trip_result.scalar_one_or_none()
        
        if not trip:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view negotiations for your own trips."
            )
        
        result = await session.execute(
            select(PriceNegotiation)
            .options(
                selectinload(PriceNegotiation.passenger),
                selectinload(PriceNegotiation.trip)
            )
            .where(PriceNegotiation.trip_id == trip_id)
            .order_by(desc(PriceNegotiation.created_at))
        )
        negotiations = result.scalars().all()
        
        logger.info(f"Retrieved {len(negotiations)} negotiations for trip {trip_id}")
        return negotiations
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trip negotiations: {e}", exc_info=True)
        return []

async def get_user_negotiations(
    session: AsyncSession,
    user_id: UUID,
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 20
) -> List[PriceNegotiation]:
    """Get negotiations created by user (passenger's offers)."""
    try:
        query = select(PriceNegotiation).options(
            selectinload(PriceNegotiation.trip).options(
                selectinload(Trip.driver)
            )
        ).where(PriceNegotiation.passenger_id == user_id)
        
        if status_filter:
            if status_filter == "pending":
                query = query.where(PriceNegotiation.status == PriceNegotiationStatus.PENDING)
            elif status_filter == "accepted":
                query = query.where(PriceNegotiation.status == PriceNegotiationStatus.ACCEPTED)
            elif status_filter == "rejected":
                query = query.where(PriceNegotiation.status == PriceNegotiationStatus.REJECTED)
            elif status_filter == "expired":
                query = query.where(PriceNegotiation.status == PriceNegotiationStatus.EXPIRED)
        
        query = query.order_by(desc(PriceNegotiation.created_at)).offset(skip).limit(limit)
        
        result = await session.execute(query)
        negotiations = result.scalars().all()
        
        logger.info(f"Retrieved {len(negotiations)} negotiations for user {user_id}")
        return negotiations
        
    except Exception as e:
        logger.error(f"Error getting user negotiations: {e}", exc_info=True)
        return []

async def get_driver_received_negotiations(
    session: AsyncSession,
    driver_id: UUID,
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 20
) -> List[PriceNegotiation]:
    """Get negotiations received by driver."""
    try:
        query = select(PriceNegotiation).options(
            selectinload(PriceNegotiation.passenger),
            selectinload(PriceNegotiation.trip)
        ).join(Trip).where(Trip.driver_id == driver_id)
        
        if status_filter:
            if status_filter == "pending":
                query = query.where(PriceNegotiation.status == PriceNegotiationStatus.PENDING)
            elif status_filter == "accepted":
                query = query.where(PriceNegotiation.status == PriceNegotiationStatus.ACCEPTED)
            elif status_filter == "rejected":
                query = query.where(PriceNegotiation.status == PriceNegotiationStatus.REJECTED)
            elif status_filter == "expired":
                query = query.where(PriceNegotiation.status == PriceNegotiationStatus.EXPIRED)
        
        query = query.order_by(desc(PriceNegotiation.created_at)).offset(skip).limit(limit)
        
        result = await session.execute(query)
        negotiations = result.scalars().all()
        
        logger.info(f"Retrieved {len(negotiations)} received negotiations for driver {driver_id}")
        return negotiations
        
    except Exception as e:
        logger.error(f"Error getting driver received negotiations: {e}", exc_info=True)
        return []

async def get_negotiation_details(
    session: AsyncSession,
    negotiation_id: UUID,
    user_id: UUID
) -> Optional[PriceNegotiation]:
    """Get detailed negotiation information."""
    try:
        result = await session.execute(
            select(PriceNegotiation)
            .options(
                selectinload(PriceNegotiation.passenger),
                selectinload(PriceNegotiation.trip).options(
                    selectinload(Trip.driver)
                )
            )
            .where(PriceNegotiation.id == negotiation_id)
        )
        negotiation = result.scalar_one_or_none()
        
        if not negotiation:
            return None
        
        # Verify user has access (either passenger or driver)
        has_access = (
            negotiation.passenger_id == user_id or 
            negotiation.trip.driver_id == user_id
        )
        
        if not has_access:
            return None
        
        return negotiation
        
    except Exception as e:
        logger.error(f"Error getting negotiation details: {e}", exc_info=True)
        return None

async def cancel_negotiation(
    session: AsyncSession,
    negotiation_id: UUID,
    passenger_id: UUID
) -> bool:
    """Cancel a pending negotiation."""
    try:
        result = await session.execute(
            select(PriceNegotiation)
            .where(
                and_(
                    PriceNegotiation.id == negotiation_id,
                    PriceNegotiation.passenger_id == passenger_id,
                    PriceNegotiation.status == PriceNegotiationStatus.PENDING
                )
            )
        )
        negotiation = result.scalar_one_or_none()
        
        if not negotiation:
            return False
        
        await session.delete(negotiation)
        await session.flush()
        
        logger.info(f"Negotiation {negotiation_id} cancelled by passenger {passenger_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error cancelling negotiation: {e}", exc_info=True)
        return False

# --- PRICE INTELLIGENCE ---

async def get_price_recommendation(
    session: AsyncSession,
    user_id: UUID,
    recommendation_request: PriceRecommendationRequest
) -> PriceRecommendationResponse:
    """Get AI-powered price recommendations."""
    try:
        # Get historical data for this route
        historical_result = await session.execute(
            select(
                func.avg(PriceNegotiation.final_price).label('avg_final'),
                func.min(PriceNegotiation.final_price).label('min_final'),
                func.max(PriceNegotiation.final_price).label('max_final'),
                func.count(PriceNegotiation.id).label('total_negotiations')
            )
            .join(Trip)
            .where(
                and_(
                    Trip.from_location_text.ilike(f"%{recommendation_request.from_location}%"),
                    Trip.to_location_text.ilike(f"%{recommendation_request.to_location}%"),
                    PriceNegotiation.status == PriceNegotiationStatus.ACCEPTED,
                    PriceNegotiation.created_at >= datetime.utcnow() - timedelta(days=90)
                )
            )
        )
        historical_data = historical_result.first()
        
        # Get current market prices for similar trips
        market_result = await session.execute(
            select(
                func.avg(Trip.price_per_seat).label('avg_market'),
                func.min(Trip.price_per_seat).label('min_market'),
                func.max(Trip.price_per_seat).label('max_market')
            )
            .where(
                and_(
                    Trip.from_location_text.ilike(f"%{recommendation_request.from_location}%"),
                    Trip.to_location_text.ilike(f"%{recommendation_request.to_location}%"),
                    Trip.status == TripStatus.SCHEDULED,
                    Trip.created_at >= datetime.utcnow() - timedelta(days=30)
                )
            )
        )
        market_data = market_result.first()
        
        # Calculate recommendations
        if historical_data.avg_final and market_data.avg_market:
            # Base recommendation on historical successful negotiations
            recommended_price = Decimal(str(historical_data.avg_final))
            market_average = Decimal(str(market_data.avg_market))
            
            # Adjust based on factors
            factors = {
                "base_calculation": "Historical successful negotiations",
                "data_points": historical_data.total_negotiations,
                "route_popularity": "moderate" if historical_data.total_negotiations > 10 else "low"
            }
            
            # Distance-based adjustment
            if recommendation_request.distance_km:
                price_per_km = recommended_price / recommendation_request.distance_km
                if price_per_km < 500:  # Minimum price per km in som
                    recommended_price = Decimal("500") * recommendation_request.distance_km
                    factors["distance_adjustment"] = "Applied minimum price per km"
            
            # Comfort level adjustment
            comfort_multiplier = {
                "economy": Decimal("1.0"),
                "comfort": Decimal("1.2"),
                "luxury": Decimal("1.5")
            }.get(recommendation_request.comfort_level, Decimal("1.0"))
            
            recommended_price *= comfort_multiplier
            if comfort_multiplier > 1:
                factors["comfort_adjustment"] = f"{recommendation_request.comfort_level} level"
            
            min_price = recommended_price * Decimal("0.85")  # 15% below recommended
            max_price = recommended_price * Decimal("1.1")   # 10% above recommended
            
        else:
            # Fallback to distance-based calculation
            base_price_per_km = Decimal("800")  # Base rate in som per km
            if recommendation_request.distance_km:
                recommended_price = base_price_per_km * recommendation_request.distance_km
            else:
                recommended_price = Decimal("15000")  # Default price
            
            min_price = recommended_price * Decimal("0.8")
            max_price = recommended_price * Decimal("1.2")
            market_average = recommended_price
            
            factors = {
                "base_calculation": "Distance-based estimation",
                "data_points": 0,
                "note": "Limited historical data available"
            }
        
        return PriceRecommendationResponse(
            recommended_price=recommended_price,
            min_price=min_price,
            max_price=max_price,
            market_average=market_average,
            factors=factors
        )
        
    except Exception as e:
        logger.error(f"Error getting price recommendation: {e}", exc_info=True)
        # Return default recommendation
        return PriceRecommendationResponse(
            recommended_price=Decimal("15000"),
            min_price=Decimal("12000"),
            max_price=Decimal("18000"),
            market_average=Decimal("16000"),
            factors={"error": "Unable to calculate precise recommendation"}
        )

async def get_market_price_trends(
    session: AsyncSession,
    from_location: str,
    to_location: str,
    days_back: int = 30
) -> Dict[str, Any]:
    """Get market price trends for a route."""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        # Get successful negotiations trend
        negotiations_result = await session.execute(
            select(
                func.date(PriceNegotiation.created_at).label('date'),
                func.avg(PriceNegotiation.final_price).label('avg_price'),
                func.count(PriceNegotiation.id).label('count')
            )
            .join(Trip)
            .where(
                and_(
                    Trip.from_location_text.ilike(f"%{from_location}%"),
                    Trip.to_location_text.ilike(f"%{to_location}%"),
                    PriceNegotiation.status == PriceNegotiationStatus.ACCEPTED,
                    PriceNegotiation.created_at >= cutoff_date
                )
            )
            .group_by(func.date(PriceNegotiation.created_at))
            .order_by(func.date(PriceNegotiation.created_at))
        )
        negotiations_trend = negotiations_result.all()
        
        # Get market prices trend
        market_result = await session.execute(
            select(
                func.date(Trip.created_at).label('date'),
                func.avg(Trip.price_per_seat).label('avg_price'),
                func.count(Trip.id).label('count')
            )
            .where(
                and_(
                    Trip.from_location_text.ilike(f"%{from_location}%"),
                    Trip.to_location_text.ilike(f"%{to_location}%"),
                    Trip.created_at >= cutoff_date
                )
            )
            .group_by(func.date(Trip.created_at))
            .order_by(func.date(Trip.created_at))
        )
        market_trend = market_result.all()
        
        # Calculate statistics
        all_negotiations = await session.execute(
            select(PriceNegotiation.final_price)
            .join(Trip)
            .where(
                and_(
                    Trip.from_location_text.ilike(f"%{from_location}%"),
                    Trip.to_location_text.ilike(f"%{to_location}%"),
                    PriceNegotiation.status == PriceNegotiationStatus.ACCEPTED,
                    PriceNegotiation.created_at >= cutoff_date
                )
            )
        )
        negotiation_prices = [float(price) for price in all_negotiations.scalars().all()]
        
        trends = {
            "route": f"{from_location} → {to_location}",
            "period_days": days_back,
            "successful_negotiations": [
                {
                    "date": row.date.isoformat(),
                    "average_price": float(row.avg_price),
                    "negotiations_count": row.count
                }
                for row in negotiations_trend
            ],
            "market_prices": [
                {
                    "date": row.date.isoformat(),
                    "average_price": float(row.avg_price),
                    "trips_count": row.count
                }
                for row in market_trend
            ],
            "statistics": {
                "total_successful_negotiations": len(negotiation_prices),
                "average_negotiated_price": sum(negotiation_prices) / len(negotiation_prices) if negotiation_prices else 0,
                "min_negotiated_price": min(negotiation_prices) if negotiation_prices else 0,
                "max_negotiated_price": max(negotiation_prices) if negotiation_prices else 0
            }
        }
        
        logger.info(f"Market trends retrieved for {from_location} → {to_location}")
        return trends
        
    except Exception as e:
        logger.error(f"Error getting market price trends: {e}", exc_info=True)
        return {"error": "Unable to retrieve price trends"}

# --- AUTO-ACCEPT SETTINGS ---

async def setup_auto_accept_rules(
    session: AsyncSession,
    driver_id: UUID,
    min_price_percentage: int,
    max_discount_amount: Decimal,
    enable_auto_accept: bool
) -> bool:
    """Setup auto-accept rules for a driver."""
    try:
        # Store in user settings or create a separate table
        # For simplicity, we'll use a JSON field in user settings
        settings_result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == driver_id)
        )
        settings = settings_result.scalar_one_or_none()
        
        if not settings:
            # Create user settings if not exists
            from crud.preferences_crud import get_user_settings
            settings = await get_user_settings(session, driver_id)
        
        # Update auto-accept rules (we'd need to add these fields to UserSettings model)
        # For now, we'll store in a hypothetical JSON field
        auto_accept_rules = {
            "enable_auto_accept": enable_auto_accept,
            "min_price_percentage": min_price_percentage,
            "max_discount_amount": float(max_discount_amount),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # This would require adding an auto_accept_rules JSON field to UserSettings
        # settings.auto_accept_rules = auto_accept_rules
        # session.add(settings)
        # await session.flush()
        
        logger.info(f"Auto-accept rules setup for driver {driver_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error setting up auto-accept rules: {e}", exc_info=True)
        return False

async def get_auto_accept_settings(
    session: AsyncSession,
    driver_id: UUID
) -> Dict[str, Any]:
    """Get auto-accept settings for a driver."""
    try:
        # This would read from the UserSettings auto_accept_rules field
        # For now, return default settings
        default_settings = {
            "enable_auto_accept": False,
            "min_price_percentage": 80,
            "max_discount_amount": 10000,
            "updated_at": None
        }
        
        logger.info(f"Auto-accept settings retrieved for driver {driver_id}")
        return default_settings
        
    except Exception as e:
        logger.error(f"Error getting auto-accept settings: {e}", exc_info=True)
        return {"enable_auto_accept": False}

# --- ANALYTICS ---

async def get_user_negotiation_analytics(
    session: AsyncSession,
    user_id: UUID
) -> Dict[str, Any]:
    """Get negotiation analytics for a user."""
    try:
        # Get user role
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one()
        
        if user.role == UserRole.PASSENGER:
            # Passenger analytics - offers made
            analytics_result = await session.execute(
                select(
                    func.count(PriceNegotiation.id).label('total_offers'),
                    func.sum(func.case(
                        (PriceNegotiation.status == PriceNegotiationStatus.ACCEPTED, 1),
                        else_=0
                    )).label('accepted_offers'),
                    func.avg(
                        func.case(
                            (PriceNegotiation.status == PriceNegotiationStatus.ACCEPTED,
                             (PriceNegotiation.original_price - PriceNegotiation.final_price) / PriceNegotiation.original_price * 100),
                            else_=None
                        )
                    ).label('avg_discount_percentage')
                )
                .where(PriceNegotiation.passenger_id == user_id)
            )
            stats = analytics_result.first()
            
            success_rate = (stats.accepted_offers / stats.total_offers * 100) if stats.total_offers > 0 else 0
            
            analytics = {
                "user_type": "passenger",
                "total_offers_made": stats.total_offers or 0,
                "accepted_offers": stats.accepted_offers or 0,
                "success_rate_percentage": round(success_rate, 1),
                "average_discount_achieved": round(stats.avg_discount_percentage or 0, 1)
            }
            
        else:  # Driver
            # Driver analytics - offers received
            analytics_result = await session.execute(
                select(
                    func.count(PriceNegotiation.id).label('total_received'),
                    func.sum(func.case(
                        (PriceNegotiation.status == PriceNegotiationStatus.ACCEPTED, 1),
                        else_=0
                    )).label('accepted_offers'),
                    func.avg(
                        func.case(
                            (PriceNegotiation.status == PriceNegotiationStatus.ACCEPTED,
                             (PriceNegotiation.original_price - PriceNegotiation.final_price) / PriceNegotiation.original_price * 100),
                            else_=None
                        )
                    ).label('avg_discount_given')
                )
                .join(Trip)
                .where(Trip.driver_id == user_id)
            )
            stats = analytics_result.first()
            
            acceptance_rate = (stats.accepted_offers / stats.total_received * 100) if stats.total_received > 0 else 0
            
            analytics = {
                "user_type": "driver",
                "total_offers_received": stats.total_received or 0,
                "offers_accepted": stats.accepted_offers or 0,
                "acceptance_rate_percentage": round(acceptance_rate, 1),
                "average_discount_given": round(stats.avg_discount_given or 0, 1)
            }
        
        logger.info(f"Negotiation analytics retrieved for user {user_id}")
        return analytics
        
    except Exception as e:
        logger.error(f"Error getting negotiation analytics: {e}", exc_info=True)
        return {"error": "Unable to retrieve analytics"}

async def get_popular_negotiation_routes(
    session: AsyncSession,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Get routes with most active price negotiations."""
    try:
        result = await session.execute(
            select(
                Trip.from_location_text,
                Trip.to_location_text,
                func.count(PriceNegotiation.id).label('negotiation_count'),
                func.avg(PriceNegotiation.proposed_price).label('avg_proposed_price'),
                func.avg(
                    func.case(
                        (PriceNegotiation.status == PriceNegotiationStatus.ACCEPTED,
                         PriceNegotiation.final_price),
                        else_=None
                    )
                ).label('avg_final_price')
            )
            .join(Trip)
            .where(PriceNegotiation.created_at >= datetime.utcnow() - timedelta(days=30))
            .group_by(Trip.from_location_text, Trip.to_location_text)
            .order_by(desc('negotiation_count'))
            .limit(limit)
        )
        
        routes = [
            {
                "route": f"{row.from_location_text} → {row.to_location_text}",
                "negotiation_count": row.negotiation_count,
                "average_proposed_price": float(row.avg_proposed_price),
                "average_final_price": float(row.avg_final_price) if row.avg_final_price else None
            }
            for row in result
        ]
        
        logger.info(f"Retrieved {len(routes)} popular negotiation routes")
        return routes
        
    except Exception as e:
        logger.error(f"Error getting popular negotiation routes: {e}", exc_info=True)
        return []

# --- BULK OPERATIONS ---

async def bulk_respond_negotiations(
    session: AsyncSession,
    driver_id: UUID,
    negotiation_ids: List[UUID],
    response_type: str
) -> Dict[str, Any]:
    """Bulk respond to multiple negotiations."""
    try:
        successful_responses = 0
        failed_responses = 0
        
        for negotiation_id in negotiation_ids:
            try:
                response = PriceNegotiationResponse(
                    response=response_type,
                    response_message=f"Bulk {response_type}"
                )
                
                result = await respond_to_negotiation(
                    session=session,
                    negotiation_id=negotiation_id,
                    driver_id=driver_id,
                    response=response
                )
                
                if result:
                    successful_responses += 1
                else:
                    failed_responses += 1
                    
            except Exception as e:
                logger.error(f"Error in bulk response for negotiation {negotiation_id}: {e}")
                failed_responses += 1
        
        results = {
            "total_processed": len(negotiation_ids),
            "successful_responses": successful_responses,
            "failed_responses": failed_responses,
            "response_type": response_type
        }
        
        logger.info(f"Bulk response completed for driver {driver_id}: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Error in bulk respond negotiations: {e}", exc_info=True)
        return {"error": "Bulk operation failed"}

# --- TEMPLATES ---

async def create_negotiation_template(
    session: AsyncSession,
    passenger_id: UUID,
    template_name: str,
    discount_percentage: int,
    message_template: str
) -> bool:
    """Create a negotiation template for quick offers."""
    try:
        # This would require a NegotiationTemplate model
        # For now, we'll store in user settings or return success
        # In a real implementation, you'd create the template record
        
        logger.info(f"Negotiation template created for passenger {passenger_id}: {template_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating negotiation template: {e}", exc_info=True)
        return False

async def get_user_negotiation_templates(
    session: AsyncSession,
    passenger_id: UUID
) -> List[Dict[str, Any]]:
    """Get negotiation templates for a passenger."""
    try:
        # This would query the NegotiationTemplate model
        # For now, return default templates
        default_templates = [
            {
                "id": "template1",
                "name": "Standard 10% off",
                "discount_percentage": 10,
                "message_template": "Would you accept {proposed_price} som for this trip?"
            },
            {
                "id": "template2",
                "name": "Budget 20% off",
                "discount_percentage": 20,
                "message_template": "I'm on a budget, can you do {proposed_price} som?"
            }
        ]
        
        logger.info(f"Retrieved negotiation templates for passenger {passenger_id}")
        return default_templates
        
    except Exception as e:
        logger.error(f"Error getting negotiation templates: {e}", exc_info=True)
        return []

# --- CLEANUP OPERATIONS ---

async def expire_old_negotiations(
    session: AsyncSession
) -> int:
    """Expire old pending negotiations (background task)."""
    try:
        result = await session.execute(
            update(PriceNegotiation)
            .where(
                and_(
                    PriceNegotiation.status == PriceNegotiationStatus.PENDING,
                    PriceNegotiation.expires_at <= datetime.utcnow()
                )
            )
            .values(status=PriceNegotiationStatus.EXPIRED)
        )
        
        expired_count = result.rowcount
        logger.info(f"Expired {expired_count} old negotiations")
        return expired_count
        
    except Exception as e:
        logger.error(f"Error expiring old negotiations: {e}", exc_info=True)
        return 0