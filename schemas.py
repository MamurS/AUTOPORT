# File: schemas.py (Fixed with proper imports and dependencies)

import re
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from uuid import UUID
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, field_validator, ConfigDict

# Define enums locally to avoid circular imports
class UserRole(str, Enum):
    PASSENGER = "passenger"
    DRIVER = "driver"
    ADMIN = "admin"

class UserStatus(str, Enum):
    PENDING_SMS_VERIFICATION = "pending_sms_verification"
    PENDING_PROFILE_COMPLETION = "pending_profile_completion"
    ACTIVE = "active"
    BLOCKED = "blocked"

class CarVerificationStatus(str, Enum):
    PENDING_VERIFICATION = "pending_verification"
    APPROVED = "approved"
    REJECTED = "rejected"

class TripStatus(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED_BY_DRIVER = "cancelled_by_driver"
    FULL = "full"

class BookingStatus(str, Enum):
    CONFIRMED = "confirmed"
    CANCELLED_BY_PASSENGER = "cancelled_by_passenger"
    CANCELLED_BY_DRIVER = "cancelled_by_driver"

class NotificationType(str, Enum):
    SMS = "sms"
    PUSH = "push"
    EMAIL = "email"

class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"

class MessageType(str, Enum):
    TEXT = "text"
    LOCATION = "location"
    SYSTEM = "system"

class RatingType(str, Enum):
    DRIVER_TO_PASSENGER = "driver_to_passenger"
    PASSENGER_TO_DRIVER = "passenger_to_driver"

class PriceNegotiationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"

class EmergencyType(str, Enum):
    SOS = "sos"
    ACCIDENT = "accident"
    BREAKDOWN = "breakdown"
    HARASSMENT = "harassment"

# Phone number validation regex for Uzbekistan format
PHONE_REGEX = r"^\+998[0-9]{9}$"

# --- ENHANCED EXISTING SCHEMAS ---

class UserBase(BaseModel):
    phone_number: str
    full_name: Optional[str] = None
    role: UserRole = UserRole.PASSENGER
    
    # NEW: Enhanced profile fields
    profile_image_url: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = Field(None, regex="^(male|female|other)$")
    spoken_languages: Optional[List[str]] = Field(default_factory=lambda: ["uz"])
    bio: Optional[str] = Field(None, max_length=500)
    email: Optional[str] = None
    preferred_language: str = Field(default="uz", regex="^(uz|ru|en)$")
    currency_preference: str = Field(default="UZS", regex="^(UZS|USD|EUR)$")

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        if not re.match(PHONE_REGEX, v):
            raise ValueError("Phone number must be in Uzbekistan format: +998XXXXXXXXX")
        return v

    @field_validator("spoken_languages")
    @classmethod
    def validate_languages(cls, v: List[str]) -> List[str]:
        if v:
            valid_langs = {"uz", "ru", "en", "tr", "ar"}
            if not all(lang in valid_langs for lang in v):
                raise ValueError("Invalid language code")
        return v or ["uz"]

class UserCreatePhoneNumber(BaseModel):
    phone_number: str = Field(..., description="Phone number in Uzbekistan format: +998XXXXXXXXX")

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        if not re.match(PHONE_REGEX, v):
            raise ValueError("Phone number must be in Uzbekistan format: +998XXXXXXXXX")
        return v

class UserCreateProfile(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    gender: Optional[str] = Field(None, regex="^(male|female|other)$")
    date_of_birth: Optional[datetime] = None
    preferred_language: str = Field(default="uz", regex="^(uz|ru|en)$")

class UserResponse(UserBase):
    id: UUID
    status: UserStatus
    admin_verification_notes: Optional[str] = None
    is_phone_verified: bool = False
    is_email_verified: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    bio: Optional[str] = Field(None, max_length=500)
    gender: Optional[str] = Field(None, regex="^(male|female|other)$")
    date_of_birth: Optional[datetime] = None
    spoken_languages: Optional[List[str]] = None
    preferred_language: Optional[str] = Field(None, regex="^(uz|ru|en)$")
    email: Optional[str] = None

# --- TRAVEL PREFERENCES SCHEMAS ---

class TravelPreferenceBase(BaseModel):
    smoking_allowed: bool = False
    pets_allowed: bool = False
    music_allowed: bool = True
    talking_allowed: bool = True
    preferred_driver_gender: Optional[str] = Field(None, regex="^(male|female|any)$")
    preferred_passenger_gender: Optional[str] = Field(None, regex="^(male|female|any)$")
    preferred_comfort_level: str = Field(default="economy", regex="^(economy|comfort|luxury)$")
    max_price_per_km: Optional[Decimal] = Field(None, ge=0, le=10000)

class TravelPreferenceCreate(TravelPreferenceBase):
    pass

class TravelPreferenceUpdate(BaseModel):
    smoking_allowed: Optional[bool] = None
    pets_allowed: Optional[bool] = None
    music_allowed: Optional[bool] = None
    talking_allowed: Optional[bool] = None
    preferred_driver_gender: Optional[str] = Field(None, regex="^(male|female|any)$")
    preferred_passenger_gender: Optional[str] = Field(None, regex="^(male|female|any)$")
    preferred_comfort_level: Optional[str] = Field(None, regex="^(economy|comfort|luxury)$")
    max_price_per_km: Optional[Decimal] = Field(None, ge=0, le=10000)

class TravelPreferenceResponse(TravelPreferenceBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- ENHANCED CAR SCHEMAS ---

class CarBase(BaseModel):
    make: str = Field(..., min_length=2, max_length=50)
    model: str = Field(..., min_length=1, max_length=50)
    license_plate: str = Field(..., min_length=4, max_length=15)
    color: str = Field(..., min_length=3, max_length=30)
    seats_count: Optional[int] = Field(default=4, ge=2, le=8)
    is_default: Optional[bool] = Field(default=False)
    
    # NEW: Enhanced car fields
    year: Optional[int] = Field(None, ge=1980, le=2030)
    car_image_url: Optional[str] = None
    features: Optional[List[str]] = Field(default_factory=list)
    comfort_level: Optional[str] = Field(default="economy", regex="^(economy|comfort|luxury)$")

    @field_validator("features")
    @classmethod
    def validate_features(cls, v: List[str]) -> List[str]:
        if v:
            valid_features = {
                "ac", "wifi", "music", "phone_charger", "gps", "dashcam", 
                "leather_seats", "bluetooth", "aux_cable", "water"
            }
            if not all(feature in valid_features for feature in v):
                raise ValueError("Invalid car feature")
        return v or []

class CarCreate(CarBase):
    pass

class CarUpdate(BaseModel):
    make: Optional[str] = Field(None, min_length=2, max_length=50)
    model: Optional[str] = Field(None, min_length=1, max_length=50)
    license_plate: Optional[str] = Field(None, min_length=4, max_length=15)
    color: Optional[str] = Field(None, min_length=3, max_length=30)
    seats_count: Optional[int] = Field(None, ge=2, le=8)
    is_default: Optional[bool] = None
    year: Optional[int] = Field(None, ge=1980, le=2030)
    car_image_url: Optional[str] = None
    features: Optional[List[str]] = None
    comfort_level: Optional[str] = Field(None, regex="^(economy|comfort|luxury)$")

class CarResponse(CarBase):
    id: UUID
    driver_id: UUID
    verification_status: CarVerificationStatus
    admin_verification_notes: Optional[str] = None
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- ENHANCED TRIP SCHEMAS ---

class IntermediateStop(BaseModel):
    location: str = Field(..., min_length=3, max_length=200)
    duration_minutes: int = Field(..., ge=5, le=120)

class TripPreferences(BaseModel):
    smoking: bool = False
    music: bool = True
    pets: bool = False
    talking: bool = True

class RecurringPattern(BaseModel):
    frequency: str = Field(..., regex="^(daily|weekly|monthly)$")
    days: Optional[List[str]] = None  # ["monday", "tuesday", ...] for weekly
    dates: Optional[List[int]] = None  # [1, 15] for monthly

    @field_validator("days")
    @classmethod
    def validate_days(cls, v, info):
        if info.data.get("frequency") == "weekly" and v:
            valid_days = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
            if not all(day in valid_days for day in v):
                raise ValueError("Invalid day name")
        return v

class TripBase(BaseModel):
    from_location_text: str = Field(..., min_length=3)
    to_location_text: str = Field(..., min_length=3)
    departure_datetime: datetime
    estimated_arrival_datetime: Optional[datetime] = None
    price_per_seat: Decimal = Field(..., ge=0)
    total_seats_offered: int = Field(..., gt=0, le=7)
    additional_info: Optional[str] = None
    
    # NEW: Enhanced trip fields
    intermediate_stops: Optional[List[IntermediateStop]] = Field(default_factory=list)
    trip_preferences: Optional[TripPreferences] = Field(default_factory=TripPreferences)
    is_recurring: bool = False
    recurring_pattern: Optional[RecurringPattern] = None
    is_instant_booking: bool = False
    max_detour_km: int = Field(default=5, ge=0, le=50)
    price_negotiable: bool = False
    estimated_distance_km: Optional[int] = Field(None, ge=1, le=5000)
    estimated_duration_minutes: Optional[int] = Field(None, ge=5, le=1440)

class TripCreate(TripBase):
    car_id: UUID

class TripUpdate(BaseModel):
    from_location_text: Optional[str] = Field(None, min_length=3)
    to_location_text: Optional[str] = Field(None, min_length=3)
    departure_datetime: Optional[datetime] = None
    estimated_arrival_datetime: Optional[datetime] = None
    price_per_seat: Optional[Decimal] = Field(None, ge=0)
    total_seats_offered: Optional[int] = Field(None, gt=0, le=7)
    additional_info: Optional[str] = None
    status: Optional[TripStatus] = None
    intermediate_stops: Optional[List[IntermediateStop]] = None
    trip_preferences: Optional[TripPreferences] = None
    is_instant_booking: Optional[bool] = None
    max_detour_km: Optional[int] = Field(None, ge=0, le=50)
    price_negotiable: Optional[bool] = None
    estimated_distance_km: Optional[int] = Field(None, ge=1, le=5000)
    estimated_duration_minutes: Optional[int] = Field(None, ge=5, le=1440)

class TripResponse(TripBase):
    id: UUID
    driver_id: UUID
    car_id: UUID
    available_seats: int
    status: TripStatus
    created_at: datetime
    updated_at: datetime
    driver: Optional[UserResponse] = None
    car: Optional[CarResponse] = None

    model_config = ConfigDict(from_attributes=True)

class TripSearchFilters(BaseModel):
    from_location: Optional[str] = None
    to_location: Optional[str] = None
    departure_date: Optional[datetime] = None
    seats_needed: int = Field(default=1, ge=1, le=7)
    max_price: Optional[Decimal] = Field(None, ge=0)
    comfort_level: Optional[str] = Field(None, regex="^(economy|comfort|luxury)$")
    driver_gender: Optional[str] = Field(None, regex="^(male|female)$")
    instant_booking_only: bool = False
    smoking_allowed: Optional[bool] = None
    pets_allowed: Optional[bool] = None
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)

# --- ENHANCED BOOKING SCHEMAS ---

class BookingBase(BaseModel):
    trip_id: UUID
    seats_booked: int = Field(default=1, ge=1, le=4)
    pickup_location: Optional[str] = None
    dropoff_location: Optional[str] = None
    special_requests: Optional[str] = Field(None, max_length=500)
    payment_method: str = Field(default="cash", regex="^(cash|card|wallet)$")

class BookingCreate(BookingBase):
    pass

class BookingUpdate(BaseModel):
    status: Optional[BookingStatus] = None
    pickup_location: Optional[str] = None
    dropoff_location: Optional[str] = None
    special_requests: Optional[str] = Field(None, max_length=500)

class BookingResponse(BookingBase):
    id: UUID
    passenger_id: UUID
    total_price: Decimal
    status: BookingStatus
    booking_time: datetime
    created_at: datetime
    updated_at: datetime
    trip: Optional[TripResponse] = None
    passenger: Optional[UserResponse] = None

    model_config = ConfigDict(from_attributes=True)

# --- MESSAGING SCHEMAS ---

class MessageBase(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)
    message_type: MessageType = MessageType.TEXT
    metadata: Optional[Dict[str, Any]] = None

class MessageCreate(MessageBase):
    receiver_id: Optional[UUID] = None  # None for group messages

class MessageResponse(MessageBase):
    id: UUID
    thread_id: UUID
    sender_id: UUID
    receiver_id: Optional[UUID] = None
    is_read: bool
    created_at: datetime
    sender: Optional[UserResponse] = None
    receiver: Optional[UserResponse] = None

    model_config = ConfigDict(from_attributes=True)

class MessageThreadResponse(BaseModel):
    id: UUID
    trip_id: UUID
    created_at: datetime
    trip: Optional[TripResponse] = None
    messages: List[MessageResponse] = Field(default_factory=list)
    participants: List[UserResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

# --- RATING SCHEMAS ---

class RatingBase(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    review: Optional[str] = Field(None, max_length=1000)
    punctuality: Optional[int] = Field(None, ge=1, le=5)
    cleanliness: Optional[int] = Field(None, ge=1, le=5)
    communication: Optional[int] = Field(None, ge=1, le=5)
    driving_quality: Optional[int] = Field(None, ge=1, le=5)

class RatingCreate(RatingBase):
    rated_user_id: UUID
    booking_id: Optional[UUID] = None

class RatingResponse(RatingBase):
    id: UUID
    trip_id: UUID
    booking_id: Optional[UUID] = None
    rater_id: UUID
    rated_user_id: UUID
    rating_type: RatingType
    created_at: datetime
    rater: Optional[UserResponse] = None
    rated_user: Optional[UserResponse] = None

    model_config = ConfigDict(from_attributes=True)

class UserRatingsSummary(BaseModel):
    average_rating: float
    total_ratings: int
    rating_breakdown: Dict[int, int]  # {5: 10, 4: 5, 3: 2, 2: 1, 1: 0}
    recent_reviews: List[RatingResponse] = Field(default_factory=list)

# --- NOTIFICATION SCHEMAS ---

class NotificationBase(BaseModel):
    notification_type: NotificationType
    title: str = Field(..., max_length=200)
    content: str = Field(..., max_length=1000)
    data: Optional[Dict[str, Any]] = None
    scheduled_at: Optional[datetime] = None

class NotificationCreate(NotificationBase):
    user_id: UUID
    phone_number: Optional[str] = None
    push_token: Optional[str] = None

class NotificationResponse(NotificationBase):
    id: UUID
    user_id: UUID
    status: NotificationStatus
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- EMERGENCY SCHEMAS ---

class EmergencyContactBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone_number: str
    relationship: str = Field(..., min_length=2, max_length=50)
    is_primary: bool = False

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        if not re.match(PHONE_REGEX, v):
            raise ValueError("Phone number must be in Uzbekistan format: +998XXXXXXXXX")
        return v

class EmergencyContactCreate(EmergencyContactBase):
    pass

class EmergencyContactUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone_number: Optional[str] = None
    relationship: Optional[str] = Field(None, min_length=2, max_length=50)
    is_primary: Optional[bool] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        if v and not re.match(PHONE_REGEX, v):
            raise ValueError("Phone number must be in Uzbekistan format: +998XXXXXXXXX")
        return v

class EmergencyContactResponse(EmergencyContactBase):
    id: UUID
    user_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class EmergencyAlertCreate(BaseModel):
    emergency_type: EmergencyType
    description: Optional[str] = Field(None, max_length=1000)
    location_lat: Optional[Decimal] = Field(None, ge=-90, le=90)
    location_lng: Optional[Decimal] = Field(None, ge=-180, le=180)
    location_address: Optional[str] = None
    trip_id: Optional[UUID] = None

class EmergencyAlertResponse(BaseModel):
    id: UUID
    user_id: UUID
    trip_id: Optional[UUID] = None
    emergency_type: EmergencyType
    description: Optional[str] = None
    location_lat: Optional[Decimal] = None
    location_lng: Optional[Decimal] = None
    location_address: Optional[str] = None
    is_resolved: bool
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- PRICE NEGOTIATION SCHEMAS ---

class PriceNegotiationCreate(BaseModel):
    trip_id: UUID
    proposed_price: Decimal = Field(..., ge=0)
    seats_requested: int = Field(default=1, ge=1, le=7)
    message: Optional[str] = Field(None, max_length=500)

class PriceNegotiationResponse(BaseModel):
    response: str = Field(..., regex="^(accept|reject)$")
    final_price: Optional[Decimal] = Field(None, ge=0)
    response_message: Optional[str] = Field(None, max_length=500)

class PriceNegotiationDetail(BaseModel):
    id: UUID
    trip_id: UUID
    passenger_id: UUID
    original_price: Decimal
    proposed_price: Decimal
    final_price: Optional[Decimal] = None
    seats_requested: int
    message: Optional[str] = None
    status: PriceNegotiationStatus
    expires_at: datetime
    responded_at: Optional[datetime] = None
    response_message: Optional[str] = None
    created_at: datetime
    passenger: Optional[UserResponse] = None
    trip: Optional[TripResponse] = None

    model_config = ConfigDict(from_attributes=True)

# --- USER SETTINGS SCHEMAS ---

class UserSettingsBase(BaseModel):
    sms_notifications: bool = True
    push_notifications: bool = True
    email_notifications: bool = False
    show_phone_to_driver: bool = True
    show_profile_picture: bool = True
    allow_contact_from_passengers: bool = True
    auto_location_detection: bool = True
    save_frequent_routes: bool = True

class UserSettingsUpdate(BaseModel):
    sms_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None
    email_notifications: Optional[bool] = None
    show_phone_to_driver: Optional[bool] = None
    show_profile_picture: Optional[bool] = None
    allow_contact_from_passengers: Optional[bool] = None
    auto_location_detection: Optional[bool] = None
    save_frequent_routes: Optional[bool] = None

class UserSettingsResponse(UserSettingsBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# --- PRICE RECOMMENDATION SCHEMAS ---

class PriceRecommendationRequest(BaseModel):
    from_location: str
    to_location: str
    distance_km: Optional[int] = None
    estimated_duration_minutes: Optional[int] = None
    departure_datetime: Optional[datetime] = None
    comfort_level: str = Field(default="economy", regex="^(economy|comfort|luxury)$")

class PriceRecommendationResponse(BaseModel):
    recommended_price: Decimal
    min_price: Decimal
    max_price: Decimal
    market_average: Decimal
    factors: Dict[str, Any]  # Explanation of price factors

# --- ANALYTICS SCHEMAS ---

class TripAnalytics(BaseModel):
    total_trips_created: int
    total_trips_completed: int
    total_revenue: Decimal
    average_rating: float
    popular_routes: List[Dict[str, Any]]
    peak_hours: List[int]

class UserAnalytics(BaseModel):
    total_trips: int
    total_distance_km: int
    average_rating: float
    preferred_routes: List[str]
    carbon_footprint_saved: float  # kg CO2

# --- ADMIN SCHEMAS ---

class AdminUpdateStatusRequest(BaseModel):
    admin_notes: Optional[str] = Field(None, description="Optional notes from the admin regarding the verification status update.", max_length=1000)

class AdminDashboardStats(BaseModel):
    total_users: int
    total_drivers: int
    pending_driver_verifications: int
    pending_car_verifications: int
    total_trips_today: int
    total_bookings_today: int
    revenue_today: Decimal
    active_emergencies: int

# --- SMS AND AUTH SCHEMAS (Enhanced) ---

class SMSVerificationCreate(BaseModel):
    phone_number: str
    code: str
    expires_at: datetime

class SMSVerificationRequest(BaseModel):
    phone_number: str = Field(..., description="Phone number in Uzbekistan format: +998XXXXXXXXX")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        if not re.match(PHONE_REGEX, v):
            raise ValueError("Phone number must be in Uzbekistan format: +998XXXXXXXXX")
        return v

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("Verification code must contain only digits")
        return v

class UserVerifyOTPAndSetProfileRequest(BaseModel):
    phone_number: str = Field(..., description="Phone number in Uzbekistan format: +998XXXXXXXXX")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")
    full_name: str = Field(..., min_length=2, max_length=100, description="User's full name")
    gender: Optional[str] = Field(None, regex="^(male|female|other)$")
    preferred_language: str = Field(default="uz", regex="^(uz|ru|en)$")

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        if not re.match(PHONE_REGEX, v):
            raise ValueError("Phone number must be in Uzbekistan format: +998XXXXXXXXX")
        return v

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("Verification code must contain only digits")
        return v

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse