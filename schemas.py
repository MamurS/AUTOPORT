# File: schemas.py (Complete updated version with admin schemas - FIXED)

import re
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from uuid import UUID
from decimal import Decimal
from enum import Enum
from dataclasses import dataclass, field

# Define enums locally to avoid circular imports
class UserRole(str, Enum):
    PASSENGER = "passenger"
    DRIVER = "driver"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"  # NEW

class AdminRole(str, Enum):
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
    MODERATOR = "moderator"

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

def validate_phone_number(phone: str) -> str:
    """Validate phone number format"""
    if not re.match(PHONE_REGEX, phone):
        raise ValueError("Phone number must be in Uzbekistan format: +998XXXXXXXXX")
    return phone

def validate_languages(languages: List[str]) -> List[str]:
    """Validate language codes"""
    if languages:
        valid_langs = {"uz", "ru", "en", "tr", "ar"}
        if not all(lang in valid_langs for lang in languages):
            raise ValueError("Invalid language code")
    return languages or ["uz"]

# --- BASE USER SCHEMAS ---

@dataclass
class UserBase:
    phone_number: str
    full_name: Optional[str] = None
    role: UserRole = UserRole.PASSENGER
    profile_image_url: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None  # male, female, other
    spoken_languages: Optional[List[str]] = field(default_factory=lambda: ["uz"])
    bio: Optional[str] = None
    email: Optional[str] = None
    preferred_language: str = "uz"
    currency_preference: str = "UZS"

    def __post_init__(self):
        self.phone_number = validate_phone_number(self.phone_number)
        self.spoken_languages = validate_languages(self.spoken_languages)

@dataclass
class UserCreatePhoneNumber:
    phone_number: str

    def __post_init__(self):
        self.phone_number = validate_phone_number(self.phone_number)

@dataclass
class UserCreateProfile:
    full_name: str
    gender: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    preferred_language: str = "uz"

@dataclass
class UserResponse:
    # Required fields first
    id: UUID
    phone_number: str
    status: UserStatus
    created_at: datetime
    updated_at: datetime
    # Optional fields with defaults
    full_name: Optional[str] = None
    role: UserRole = UserRole.PASSENGER
    profile_image_url: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None
    spoken_languages: Optional[List[str]] = field(default_factory=lambda: ["uz"])
    bio: Optional[str] = None
    email: Optional[str] = None
    preferred_language: str = "uz"
    currency_preference: str = "UZS"
    admin_verification_notes: Optional[str] = None
    is_phone_verified: bool = False
    is_email_verified: bool = False

@dataclass
class UserProfileUpdate:
    full_name: Optional[str] = None
    bio: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    spoken_languages: Optional[List[str]] = None
    preferred_language: Optional[str] = None
    email: Optional[str] = None

# --- ADMIN AUTHENTICATION SCHEMAS ---

@dataclass
class AdminLoginRequest:
    email: str
    password: str

@dataclass  
class AdminMFAVerificationRequest:
    session_token: str
    mfa_code: str

@dataclass
class AdminResponse:
    # Required fields first (no defaults)
    id: UUID
    email: str
    full_name: str
    role: AdminRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # Optional fields with defaults last
    last_login: Optional[datetime] = None

@dataclass
class AdminTokenResponse:
    # Required fields first
    access_token: str
    admin: AdminResponse
    # Optional fields with defaults last
    token_type: str = "bearer"

@dataclass
class AdminInviteRequest:
    email: str
    role: AdminRole = AdminRole.ADMIN
    message: Optional[str] = None

@dataclass
class AcceptInviteRequest:
    token: str
    full_name: str
    password: str
    confirm_password: str

@dataclass
class AdminInvitationResponse:
    # Required fields first
    id: UUID
    email: str
    role: AdminRole
    expires_at: datetime
    is_used: bool
    created_at: datetime
    # Optional fields with defaults last
    inviter_name: Optional[str] = None

@dataclass
class AdminCreateRequest:
    email: str
    full_name: str
    password: str
    role: AdminRole = AdminRole.ADMIN

@dataclass
class AdminUpdateRequest:
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[AdminRole] = None
    is_active: Optional[bool] = None

@dataclass
class ChangePasswordRequest:
    current_password: str
    new_password: str
    confirm_password: str

@dataclass  
class BootstrapAdminRequest:
    email: str
    full_name: str
    password: str
    confirm_password: str

@dataclass
class AdminAuditLogResponse:
    # Required fields first
    id: UUID
    admin_id: UUID
    action: str
    success: bool
    timestamp: datetime
    # Optional fields with defaults last
    resource_type: Optional[str] = None
    resource_id: Optional[UUID] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    admin_name: Optional[str] = None
    error_message: Optional[str] = None

@dataclass
class AdminStatsResponse:
    total_admins: int
    active_admins: int
    total_actions_today: int
    failed_logins_today: int
    pending_invitations: int

# --- TRAVEL PREFERENCES SCHEMAS ---

@dataclass
class TravelPreferenceBase:
    smoking_allowed: bool = False
    pets_allowed: bool = False
    music_allowed: bool = True
    talking_allowed: bool = True
    preferred_driver_gender: Optional[str] = None
    preferred_passenger_gender: Optional[str] = None
    preferred_comfort_level: str = "economy"
    max_price_per_km: Optional[Decimal] = None

@dataclass
class TravelPreferenceCreate(TravelPreferenceBase):
    pass

@dataclass
class TravelPreferenceUpdate:
    smoking_allowed: Optional[bool] = None
    pets_allowed: Optional[bool] = None
    music_allowed: Optional[bool] = None
    talking_allowed: Optional[bool] = None
    preferred_driver_gender: Optional[str] = None
    preferred_passenger_gender: Optional[str] = None
    preferred_comfort_level: Optional[str] = None
    max_price_per_km: Optional[Decimal] = None

@dataclass
class TravelPreferenceResponse:
    # Required fields first
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    # Optional fields with defaults from base
    smoking_allowed: bool = False
    pets_allowed: bool = False
    music_allowed: bool = True
    talking_allowed: bool = True
    preferred_driver_gender: Optional[str] = None
    preferred_passenger_gender: Optional[str] = None
    preferred_comfort_level: str = "economy"
    max_price_per_km: Optional[Decimal] = None

# --- CAR SCHEMAS ---

@dataclass
class CarBase:
    make: str
    model: str
    license_plate: str
    color: str
    seats_count: Optional[int] = 4
    is_default: Optional[bool] = False
    year: Optional[int] = None
    car_image_url: Optional[str] = None
    features: Optional[List[str]] = field(default_factory=list)
    comfort_level: Optional[str] = "economy"

@dataclass
class CarCreate(CarBase):
    pass

@dataclass
class CarUpdate:
    make: Optional[str] = None
    model: Optional[str] = None
    license_plate: Optional[str] = None
    color: Optional[str] = None
    seats_count: Optional[int] = None
    is_default: Optional[bool] = None
    year: Optional[int] = None
    car_image_url: Optional[str] = None
    features: Optional[List[str]] = None
    comfort_level: Optional[str] = None

@dataclass
class CarResponse:
    # Required fields first
    id: UUID
    driver_id: UUID
    verification_status: CarVerificationStatus
    created_at: datetime
    updated_at: datetime
    # Fields from base with defaults
    make: str = ""
    model: str = ""
    license_plate: str = ""
    color: str = ""
    seats_count: Optional[int] = 4
    is_default: bool = False
    year: Optional[int] = None
    car_image_url: Optional[str] = None
    features: Optional[List[str]] = field(default_factory=list)
    comfort_level: Optional[str] = "economy"
    admin_verification_notes: Optional[str] = None

# --- TRIP SCHEMAS ---

@dataclass
class IntermediateStop:
    location: str
    duration_minutes: int

@dataclass
class TripPreferences:
    smoking: bool = False
    music: bool = True
    pets: bool = False
    talking: bool = True

@dataclass
class RecurringPattern:
    frequency: str
    days: Optional[List[str]] = None
    dates: Optional[List[int]] = None

@dataclass
class TripBase:
    from_location_text: str
    to_location_text: str
    departure_datetime: datetime
    estimated_arrival_datetime: Optional[datetime] = None
    price_per_seat: Decimal = Decimal('0')
    total_seats_offered: int = 1
    additional_info: Optional[str] = None
    intermediate_stops: Optional[List[IntermediateStop]] = field(default_factory=list)
    trip_preferences: Optional[TripPreferences] = field(default_factory=TripPreferences)
    is_recurring: bool = False
    recurring_pattern: Optional[RecurringPattern] = None
    is_instant_booking: bool = False
    max_detour_km: int = 5
    price_negotiable: bool = False
    estimated_distance_km: Optional[int] = None
    estimated_duration_minutes: Optional[int] = None

@dataclass
class TripCreate:
    # Required fields first
    car_id: UUID
    from_location_text: str
    to_location_text: str
    departure_datetime: datetime
    # Optional fields with defaults
    estimated_arrival_datetime: Optional[datetime] = None
    price_per_seat: Decimal = Decimal('0')
    total_seats_offered: int = 1
    additional_info: Optional[str] = None
    intermediate_stops: Optional[List[IntermediateStop]] = field(default_factory=list)
    trip_preferences: Optional[TripPreferences] = field(default_factory=TripPreferences)
    is_recurring: bool = False
    recurring_pattern: Optional[RecurringPattern] = None
    is_instant_booking: bool = False
    max_detour_km: int = 5
    price_negotiable: bool = False
    estimated_distance_km: Optional[int] = None
    estimated_duration_minutes: Optional[int] = None

@dataclass
class TripUpdate:
    from_location_text: Optional[str] = None
    to_location_text: Optional[str] = None
    departure_datetime: Optional[datetime] = None
    estimated_arrival_datetime: Optional[datetime] = None
    price_per_seat: Optional[Decimal] = None
    total_seats_offered: Optional[int] = None
    additional_info: Optional[str] = None
    status: Optional[TripStatus] = None
    intermediate_stops: Optional[List[IntermediateStop]] = None
    trip_preferences: Optional[TripPreferences] = None
    is_instant_booking: Optional[bool] = None
    max_detour_km: Optional[int] = None
    price_negotiable: Optional[bool] = None
    estimated_distance_km: Optional[int] = None
    estimated_duration_minutes: Optional[int] = None

@dataclass
class TripResponse:
    # Required fields first
    id: UUID
    driver_id: UUID
    car_id: UUID
    available_seats: int
    status: TripStatus
    created_at: datetime
    updated_at: datetime
    # Fields from base with defaults
    from_location_text: str = ""
    to_location_text: str = ""
    departure_datetime: Optional[datetime] = None
    estimated_arrival_datetime: Optional[datetime] = None
    price_per_seat: Decimal = Decimal('0')
    total_seats_offered: int = 1
    additional_info: Optional[str] = None
    intermediate_stops: Optional[List[IntermediateStop]] = field(default_factory=list)
    trip_preferences: Optional[TripPreferences] = field(default_factory=TripPreferences)
    is_recurring: bool = False
    recurring_pattern: Optional[RecurringPattern] = None
    is_instant_booking: bool = False
    max_detour_km: int = 5
    price_negotiable: bool = False
    estimated_distance_km: Optional[int] = None
    estimated_duration_minutes: Optional[int] = None
    driver: Optional[UserResponse] = None
    car: Optional[CarResponse] = None

@dataclass
class TripSearchFilters:
    from_location: Optional[str] = None
    to_location: Optional[str] = None
    departure_date: Optional[datetime] = None
    seats_needed: int = 1
    max_price: Optional[Decimal] = None
    comfort_level: Optional[str] = None
    driver_gender: Optional[str] = None
    instant_booking_only: bool = False
    smoking_allowed: Optional[bool] = None
    pets_allowed: Optional[bool] = None
    skip: int = 0
    limit: int = 20

# --- BOOKING SCHEMAS ---

@dataclass
class BookingBase:
    trip_id: UUID
    seats_booked: int = 1
    pickup_location: Optional[str] = None
    dropoff_location: Optional[str] = None
    special_requests: Optional[str] = None
    payment_method: str = "cash"

@dataclass
class BookingCreate:
    trip_id: UUID
    seats_booked: int = 1
    pickup_location: Optional[str] = None
    dropoff_location: Optional[str] = None
    special_requests: Optional[str] = None
    payment_method: str = "cash"

@dataclass
class BookingUpdate:
    status: Optional[BookingStatus] = None
    pickup_location: Optional[str] = None
    dropoff_location: Optional[str] = None
    special_requests: Optional[str] = None

@dataclass
class BookingResponse:
    # Required fields first
    id: UUID
    passenger_id: UUID
    trip_id: UUID
    total_price: Decimal
    status: BookingStatus
    booking_time: datetime
    created_at: datetime
    updated_at: datetime
    # Optional fields with defaults
    seats_booked: int = 1
    pickup_location: Optional[str] = None
    dropoff_location: Optional[str] = None
    special_requests: Optional[str] = None
    payment_method: str = "cash"
    trip: Optional[TripResponse] = None
    passenger: Optional[UserResponse] = None

# --- MESSAGE SCHEMAS ---

@dataclass
class MessageBase:
    content: str
    message_type: MessageType = MessageType.TEXT
    message_metadata: Optional[Dict[str, Any]] = None

@dataclass
class MessageCreate:
    content: str
    message_type: MessageType = MessageType.TEXT
    message_metadata: Optional[Dict[str, Any]] = None
    receiver_id: Optional[UUID] = None

@dataclass
class MessageResponse:
    # Required fields first
    id: UUID
    thread_id: UUID
    sender_id: UUID
    created_at: datetime
    # Optional fields with defaults
    content: str = ""
    message_type: MessageType = MessageType.TEXT
    message_metadata: Optional[Dict[str, Any]] = None
    receiver_id: Optional[UUID] = None
    is_read: bool = False
    sender: Optional[UserResponse] = None
    receiver: Optional[UserResponse] = None

@dataclass
class MessageThreadResponse:
    id: UUID
    trip_id: UUID
    created_at: datetime
    trip: Optional[TripResponse] = None
    messages: List[MessageResponse] = field(default_factory=list)
    participants: List[UserResponse] = field(default_factory=list)

# --- RATING SCHEMAS ---

@dataclass
class RatingBase:
    rating: int  # 1-5
    review: Optional[str] = None
    punctuality: Optional[int] = None
    cleanliness: Optional[int] = None
    communication: Optional[int] = None
    driving_quality: Optional[int] = None

@dataclass
class RatingCreate:
    rated_user_id: UUID
    rating: int  # 1-5
    review: Optional[str] = None
    punctuality: Optional[int] = None
    cleanliness: Optional[int] = None
    communication: Optional[int] = None
    driving_quality: Optional[int] = None
    booking_id: Optional[UUID] = None

@dataclass
class RatingResponse:
    # Required fields first
    id: UUID
    trip_id: UUID
    rater_id: UUID
    rated_user_id: UUID
    rating_type: RatingType
    created_at: datetime
    # Optional fields with defaults
    rating: int = 1
    review: Optional[str] = None
    punctuality: Optional[int] = None
    cleanliness: Optional[int] = None
    communication: Optional[int] = None
    driving_quality: Optional[int] = None
    booking_id: Optional[UUID] = None
    rater: Optional[UserResponse] = None
    rated_user: Optional[UserResponse] = None

@dataclass
class UserRatingsSummary:
    average_rating: float
    total_ratings: int
    rating_breakdown: Dict[int, int] = field(default_factory=dict)
    recent_reviews: List[RatingResponse] = field(default_factory=list)

# --- NOTIFICATION SCHEMAS ---

@dataclass
class NotificationBase:
    notification_type: NotificationType
    title: str
    content: str
    data: Optional[Dict[str, Any]] = None
    scheduled_at: Optional[datetime] = None

@dataclass
class NotificationCreate:
    user_id: UUID
    notification_type: NotificationType
    title: str
    content: str
    data: Optional[Dict[str, Any]] = None
    scheduled_at: Optional[datetime] = None
    phone_number: Optional[str] = None
    push_token: Optional[str] = None

@dataclass
class NotificationResponse:
    # Required fields first
    id: UUID
    user_id: UUID
    notification_type: NotificationType
    title: str
    content: str
    status: NotificationStatus
    created_at: datetime
    # Optional fields with defaults
    data: Optional[Dict[str, Any]] = None
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None

# --- EMERGENCY SCHEMAS ---

@dataclass
class EmergencyContactBase:
    name: str
    phone_number: str
    relationship_type: str
    is_primary: bool = False

    def __post_init__(self):
        self.phone_number = validate_phone_number(self.phone_number)

@dataclass
class EmergencyContactCreate:
    name: str
    phone_number: str
    relationship_type: str
    is_primary: bool = False

    def __post_init__(self):
        self.phone_number = validate_phone_number(self.phone_number)

@dataclass
class EmergencyContactUpdate:
    name: Optional[str] = None
    phone_number: Optional[str] = None
    relationship_type: Optional[str] = None
    is_primary: Optional[bool] = None

    def __post_init__(self):
        if self.phone_number:
            self.phone_number = validate_phone_number(self.phone_number)

@dataclass
class EmergencyContactResponse:
    # Required fields first
    id: UUID
    user_id: UUID
    created_at: datetime
    # Fields from base with defaults
    name: str = ""
    phone_number: str = ""
    relationship_type: str = ""
    is_primary: bool = False

@dataclass
class EmergencyAlertCreate:
    emergency_type: EmergencyType
    description: Optional[str] = None
    location_lat: Optional[Decimal] = None
    location_lng: Optional[Decimal] = None
    location_address: Optional[str] = None
    trip_id: Optional[UUID] = None

@dataclass
class EmergencyAlertResponse:
    id: UUID
    user_id: UUID
    emergency_type: EmergencyType
    created_at: datetime
    trip_id: Optional[UUID] = None
    description: Optional[str] = None
    location_lat: Optional[Decimal] = None
    location_lng: Optional[Decimal] = None
    location_address: Optional[str] = None
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[UUID] = None

# --- PRICE NEGOTIATION SCHEMAS ---

@dataclass
class PriceNegotiationCreate:
    trip_id: UUID
    proposed_price: Decimal
    seats_requested: int = 1
    message: Optional[str] = None

@dataclass
class PriceNegotiationResponse:
    response: str  # accept/reject
    final_price: Optional[Decimal] = None
    response_message: Optional[str] = None

@dataclass
class PriceNegotiationDetail:
    # Required fields first
    id: UUID
    trip_id: UUID
    passenger_id: UUID
    original_price: Decimal
    proposed_price: Decimal
    expires_at: datetime
    created_at: datetime
    # Optional fields with defaults
    final_price: Optional[Decimal] = None
    seats_requested: int = 1
    message: Optional[str] = None
    status: PriceNegotiationStatus = PriceNegotiationStatus.PENDING
    responded_at: Optional[datetime] = None
    response_message: Optional[str] = None
    passenger: Optional[UserResponse] = None
    trip: Optional[TripResponse] = None

# --- USER SETTINGS SCHEMAS ---

@dataclass
class UserSettingsBase:
    sms_notifications: bool = True
    push_notifications: bool = True
    email_notifications: bool = False
    show_phone_to_driver: bool = True
    show_profile_picture: bool = True
    allow_contact_from_passengers: bool = True
    auto_location_detection: bool = True
    save_frequent_routes: bool = True

@dataclass
class UserSettingsUpdate:
    sms_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None
    email_notifications: Optional[bool] = None
    show_phone_to_driver: Optional[bool] = None
    show_profile_picture: Optional[bool] = None
    allow_contact_from_passengers: Optional[bool] = None
    auto_location_detection: Optional[bool] = None
    save_frequent_routes: Optional[bool] = None

@dataclass
class UserSettingsResponse:
    # Required fields first
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    # Optional fields with defaults
    sms_notifications: bool = True
    push_notifications: bool = True
    email_notifications: bool = False
    show_phone_to_driver: bool = True
    show_profile_picture: bool = True
    allow_contact_from_passengers: bool = True
    auto_location_detection: bool = True
    save_frequent_routes: bool = True

# --- PRICE RECOMMENDATION SCHEMAS ---

@dataclass
class PriceRecommendationRequest:
    from_location: str
    to_location: str
    distance_km: Optional[int] = None
    estimated_duration_minutes: Optional[int] = None
    departure_datetime: Optional[datetime] = None
    comfort_level: str = "economy"

@dataclass
class PriceRecommendationResponse:
    recommended_price: Decimal
    min_price: Decimal
    max_price: Decimal
    market_average: Decimal
    factors: Dict[str, Any] = field(default_factory=dict)

# --- AUTH SCHEMAS ---

@dataclass
class SMSVerificationCreate:
    phone_number: str
    code: str
    expires_at: datetime

@dataclass
class SMSVerificationRequest:
    phone_number: str
    code: str

    def __post_init__(self):
        self.phone_number = validate_phone_number(self.phone_number)
        if not self.code.isdigit() or len(self.code) != 6:
            raise ValueError("Verification code must be 6 digits")

@dataclass
class UserVerifyOTPAndSetProfileRequest:
    phone_number: str
    code: str
    full_name: str
    gender: Optional[str] = None
    preferred_language: str = "uz"

    def __post_init__(self):
        self.phone_number = validate_phone_number(self.phone_number)
        if not self.code.isdigit() or len(self.code) != 6:
            raise ValueError("Verification code must be 6 digits")

@dataclass
class TokenResponse:
    access_token: str
    user: UserResponse
    token_type: str = "bearer"

# --- ADMIN MANAGEMENT SCHEMAS ---

@dataclass
class AdminUpdateStatusRequest:
    admin_notes: Optional[str] = None

@dataclass
class AdminDashboardStats:
    total_users: int = 0
    total_drivers: int = 0
    pending_driver_verifications: int = 0
    pending_car_verifications: int = 0
    total_trips_today: int = 0
    total_bookings_today: int = 0
    revenue_today: Decimal = Decimal('0')
    active_emergencies: int = 0