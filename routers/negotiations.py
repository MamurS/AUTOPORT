# File: routers/negotiations.py

import logging
from typing import Annotated, List, Optional
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_active_user
from crud import negotiations_crud
from database import get_db
from models import User, UserRole
from schemas import (
    PriceNegotiationCreate, PriceNegotiationResponse, PriceNegotiationDetail,
    PriceRecommendationRequest, PriceRecommendationResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/negotiations", tags=["price-negotiations"])

# --- PRICE NEGOTIATIONS ---

@router.post("/", response_model=PriceNegotiationDetail, status_code=status.HTTP_201_CREATED)
async def create_price_negotiation(
    negotiation_data: PriceNegotiationCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> PriceNegotiationDetail:
    """
    Create a new price negotiation offer for a trip.
    Passengers can propose alternative prices to drivers.
    """
    try:
        if current_user.role != UserRole.PASSENGER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only passengers can initiate price negotiations."
            )
        
        negotiation = await negotiations_crud.create_price_negotiation(
            session=db,
            passenger_id=current_user.id,
            negotiation_data=negotiation_data
        )
        
        logger.info(f"Price negotiation created by passenger {current_user.id} for trip {negotiation_data.trip_id}")
        return negotiation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating price negotiation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the price negotiation."
        )

@router.get("/trip/{trip_id}", response_model=List[PriceNegotiationDetail])
async def get_trip_negotiations(
    trip_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> List[PriceNegotiationDetail]:
    """
    Get all price negotiations for a specific trip.
    Drivers can see all offers for their trips.
    """
    try:
        negotiations = await negotiations_crud.get_trip_negotiations(
            session=db,
            trip_id=trip_id,
            user_id=current_user.id
        )
        
        logger.info(f"Retrieved {len(negotiations)} negotiations for trip {trip_id}")
        return negotiations
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trip negotiations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving price negotiations."
        )

@router.get("/my-offers", response_model=List[PriceNegotiationDetail])
async def get_my_price_offers(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[str] = Query(default=None, regex="^(pending|accepted|rejected|expired)$")
) -> List[PriceNegotiationDetail]:
    """
    Get price negotiations created by the current user (passenger's offers).
    """
    try:
        if current_user.role != UserRole.PASSENGER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only passengers can view their price offers."
            )
        
        negotiations = await negotiations_crud.get_user_negotiations(
            session=db,
            user_id=current_user.id,
            status_filter=status_filter,
            skip=skip,
            limit=limit
        )
        
        logger.info(f"Retrieved {len(negotiations)} negotiations for passenger {current_user.id}")
        return negotiations
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user negotiations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving your price offers."
        )

@router.get("/received-offers", response_model=List[PriceNegotiationDetail])
async def get_received_price_offers(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[str] = Query(default=None, regex="^(pending|accepted|rejected|expired)$")
) -> List[PriceNegotiationDetail]:
    """
    Get price negotiations received by the current user (driver's received offers).
    """
    try:
        if current_user.role != UserRole.DRIVER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only drivers can view received price offers."
            )
        
        negotiations = await negotiations_crud.get_driver_received_negotiations(
            session=db,
            driver_id=current_user.id,
            status_filter=status_filter,
            skip=skip,
            limit=limit
        )
        
        logger.info(f"Retrieved {len(negotiations)} received negotiations for driver {current_user.id}")
        return negotiations
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting received negotiations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving received price offers."
        )

@router.patch("/{negotiation_id}/respond", response_model=PriceNegotiationDetail)
async def respond_to_price_negotiation(
    negotiation_id: UUID,
    response: PriceNegotiationResponse,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> PriceNegotiationDetail:
    """
    Respond to a price negotiation (accept/reject).
    Drivers can accept or reject passenger price offers.
    """
    try:
        if current_user.role != UserRole.DRIVER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only drivers can respond to price negotiations."
            )
        
        negotiation = await negotiations_crud.respond_to_negotiation(
            session=db,
            negotiation_id=negotiation_id,
            driver_id=current_user.id,
            response=response
        )
        
        if not negotiation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Price negotiation not found or you don't have permission to respond."
            )
        
        logger.info(f"Price negotiation {negotiation_id} responded to by driver {current_user.id}: {response.response}")
        return negotiation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error responding to price negotiation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while responding to the price negotiation."
        )

@router.post("/{negotiation_id}/counter-offer", response_model=PriceNegotiationDetail)
async def create_counter_offer(
    negotiation_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    counter_price: Decimal = Query(..., ge=0),
    message: Optional[str] = Query(default=None, max_length=500)
) -> PriceNegotiationDetail:
    """
    Create a counter-offer for an existing negotiation.
    Drivers can propose alternative prices instead of accepting/rejecting.
    """
    try:
        if current_user.role != UserRole.DRIVER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only drivers can create counter-offers."
            )
        
        counter_negotiation = await negotiations_crud.create_counter_offer(
            session=db,
            original_negotiation_id=negotiation_id,
            driver_id=current_user.id,
            counter_price=counter_price,
            message=message
        )
        
        if not counter_negotiation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Original negotiation not found or cannot create counter-offer."
            )
        
        logger.info(f"Counter-offer created for negotiation {negotiation_id} by driver {current_user.id}")
        return counter_negotiation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating counter-offer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the counter-offer."
        )

@router.patch("/{negotiation_id}/accept-counter", response_model=PriceNegotiationDetail)
async def accept_counter_offer(
    negotiation_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> PriceNegotiationDetail:
    """
    Accept a counter-offer from a driver.
    Passengers can accept counter-offers to finalize the price.
    """
    try:
        if current_user.role != UserRole.PASSENGER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only passengers can accept counter-offers."
            )
        
        negotiation = await negotiations_crud.accept_counter_offer(
            session=db,
            negotiation_id=negotiation_id,
            passenger_id=current_user.id
        )
        
        if not negotiation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Counter-offer not found or you don't have permission to accept."
            )
        
        logger.info(f"Counter-offer {negotiation_id} accepted by passenger {current_user.id}")
        return negotiation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting counter-offer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while accepting the counter-offer."
        )

@router.delete("/{negotiation_id}")
async def cancel_price_negotiation(
    negotiation_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Cancel a pending price negotiation.
    Passengers can cancel their own pending offers.
    """
    try:
        if current_user.role != UserRole.PASSENGER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only passengers can cancel their price negotiations."
            )
        
        success = await negotiations_crud.cancel_negotiation(
            session=db,
            negotiation_id=negotiation_id,
            passenger_id=current_user.id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Price negotiation not found or cannot be cancelled."
            )
        
        logger.info(f"Price negotiation {negotiation_id} cancelled by passenger {current_user.id}")
        return {"message": "Price negotiation cancelled successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling price negotiation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while cancelling the price negotiation."
        )

@router.get("/{negotiation_id}", response_model=PriceNegotiationDetail)
async def get_negotiation_details(
    negotiation_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> PriceNegotiationDetail:
    """
    Get detailed information about a specific price negotiation.
    """
    try:
        negotiation = await negotiations_crud.get_negotiation_details(
            session=db,
            negotiation_id=negotiation_id,
            user_id=current_user.id
        )
        
        if not negotiation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Price negotiation not found or you don't have permission to view it."
            )
        
        return negotiation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting negotiation details: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving negotiation details."
        )

# --- PRICE RECOMMENDATIONS ---

@router.post("/price-recommendation", response_model=PriceRecommendationResponse)
async def get_price_recommendation(
    recommendation_request: PriceRecommendationRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> PriceRecommendationResponse:
    """
    Get AI-powered price recommendations for a route.
    Helps users understand fair market prices for negotiations.
    """
    try:
        recommendation = await negotiations_crud.get_price_recommendation(
            session=db,
            user_id=current_user.id,
            recommendation_request=recommendation_request
        )
        
        logger.info(f"Price recommendation generated for user {current_user.id}")
        return recommendation
    except Exception as e:
        logger.error(f"Error getting price recommendation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating price recommendation."
        )

@router.get("/market-prices")
async def get_market_price_trends(
    db: Annotated[AsyncSession, Depends(get_db)],
    from_location: str = Query(..., min_length=3),
    to_location: str = Query(..., min_length=3),
    days_back: int = Query(default=30, ge=7, le=90)
) -> dict:
    """
    Get market price trends for a specific route.
    Shows historical pricing data to help users make informed offers.
    """
    try:
        trends = await negotiations_crud.get_market_price_trends(
            session=db,
            from_location=from_location,
            to_location=to_location,
            days_back=days_back
        )
        
        return trends
    except Exception as e:
        logger.error(f"Error getting market price trends: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving market price trends."
        )

# --- AUTO-NEGOTIATION SETTINGS ---

@router.post("/auto-accept/setup")
async def setup_auto_accept_rules(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    min_price_percentage: int = Query(..., ge=50, le=100, description="Minimum percentage of original price to auto-accept"),
    max_discount_amount: Decimal = Query(..., ge=0, description="Maximum discount amount to auto-accept"),
    enable_auto_accept: bool = Query(default=True)
) -> dict:
    """
    Set up auto-accept rules for price negotiations.
    Drivers can automatically accept offers within certain thresholds.
    """
    try:
        if current_user.role != UserRole.DRIVER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only drivers can set up auto-accept rules."
            )
        
        success = await negotiations_crud.setup_auto_accept_rules(
            session=db,
            driver_id=current_user.id,
            min_price_percentage=min_price_percentage,
            max_discount_amount=max_discount_amount,
            enable_auto_accept=enable_auto_accept
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to setup auto-accept rules."
            )
        
        logger.info(f"Auto-accept rules setup for driver {current_user.id}")
        return {"message": "Auto-accept rules configured successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting up auto-accept rules: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while setting up auto-accept rules."
        )

@router.get("/auto-accept/settings")
async def get_auto_accept_settings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get current auto-accept settings for the driver.
    """
    try:
        if current_user.role != UserRole.DRIVER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only drivers can view auto-accept settings."
            )
        
        settings = await negotiations_crud.get_auto_accept_settings(
            session=db,
            driver_id=current_user.id
        )
        
        return settings
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting auto-accept settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving auto-accept settings."
        )

# --- NEGOTIATION ANALYTICS ---

@router.get("/analytics/my-stats")
async def get_negotiation_analytics(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get negotiation analytics for the current user.
    Shows success rates, average discounts, etc.
    """
    try:
        analytics = await negotiations_crud.get_user_negotiation_analytics(
            session=db,
            user_id=current_user.id
        )
        
        return analytics
    except Exception as e:
        logger.error(f"Error getting negotiation analytics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving negotiation analytics."
        )

@router.get("/popular-routes")
async def get_popular_negotiation_routes(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=10, ge=1, le=50)
) -> dict:
    """
    Get routes with most active price negotiations.
    Helps understand market dynamics.
    """
    try:
        routes = await negotiations_crud.get_popular_negotiation_routes(
            session=db,
            limit=limit
        )
        
        return {"popular_routes": routes}
    except Exception as e:
        logger.error(f"Error getting popular negotiation routes: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving popular routes."
        )

# --- BULK OPERATIONS ---

@router.post("/bulk-respond")
async def bulk_respond_to_negotiations(
    negotiation_ids: List[UUID],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    response_type: str = Query(..., regex="^(accept|reject)$")
) -> dict:
    """
    Respond to multiple price negotiations at once.
    Useful for drivers with many pending offers.
    """
    try:
        if current_user.role != UserRole.DRIVER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only drivers can bulk respond to negotiations."
            )
        
        if len(negotiation_ids) > 20:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 20 negotiations can be processed at once."
            )
        
        results = await negotiations_crud.bulk_respond_negotiations(
            session=db,
            driver_id=current_user.id,
            negotiation_ids=negotiation_ids,
            response_type=response_type
        )
        
        logger.info(f"Bulk response to {len(negotiation_ids)} negotiations by driver {current_user.id}")
        return results
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error bulk responding to negotiations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing bulk response."
        )

# --- NEGOTIATION TEMPLATES ---

@router.post("/templates/create")
async def create_negotiation_template(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    template_name: str = Query(..., min_length=3, max_length=100),
    discount_percentage: int = Query(..., ge=5, le=50),
    message_template: str = Query(..., max_length=500)
) -> dict:
    """
    Create a negotiation template for quick offers.
    Passengers can save common negotiation patterns.
    """
    try:
        if current_user.role != UserRole.PASSENGER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only passengers can create negotiation templates."
            )
        
        success = await negotiations_crud.create_negotiation_template(
            session=db,
            passenger_id=current_user.id,
            template_name=template_name,
            discount_percentage=discount_percentage,
            message_template=message_template
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Template with this name already exists or maximum templates reached."
            )
        
        logger.info(f"Negotiation template created by passenger {current_user.id}")
        return {"message": "Negotiation template created successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating negotiation template: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the negotiation template."
        )

@router.get("/templates")
async def get_negotiation_templates(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """
    Get all negotiation templates for the current user.
    """
    try:
        if current_user.role != UserRole.PASSENGER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only passengers can view negotiation templates."
            )
        
        templates = await negotiations_crud.get_user_negotiation_templates(
            session=db,
            passenger_id=current_user.id
        )
        
        return {"templates": templates}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting negotiation templates: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving negotiation templates."
        )