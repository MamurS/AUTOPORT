# File: models.py (Complete updated version with admin security)

import uuid
from enum import Enum
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Enum as SQLAlchemyEnum, func, Boolean, Integer, ForeignKey, Numeric, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base

# Create Base here to avoid circular imports
Base = declarative_base()

# --- Enhanced Enums ---
class UserRole(str, Enum):
    PASSENGER = "passenger"
    DRIVER = "driver"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"  # NEW: Can manage other admins

class AdminRole(str, Enum):
    ADMIN = "admin"              # Can manage users, drivers, cars
    SUPER_ADMIN = "super_admin"  # Can manage other admins
    MODERATOR = "moderator"      # Limited permissions

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

# --- NEW ENUMS FOR ENHANCED FEATURES ---
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

# --- ENHANCED USER MODEL ---
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(SQLAlchemyEnum(UserRole), nullable=False, default=UserRole.PASSENGER)
    status = Column(SQLAlchemyEnum(UserStatus), nullable=False, default=UserStatus.PENDING_SMS_VERIFICATION)
    admin_verification_notes = Column(Text, nullable=True)
    
    # Enhanced profile fields
    profile_image_url = Column(String, nullable=True)
    date_of_birth = Column(DateTime, nullable=True)
    gender = Column(String(10), nullable=True)  # male, female, other
    spoken_languages = Column(JSON, nullable=True)  # ["uz", "ru", "en"]
    bio = Column(Text, nullable=True)
    
    # Verification fields
    is_phone_verified = Column(Boolean, default=False)
    is_email_verified = Column(Boolean, default=False)
    email = Column(String, nullable=True)
    
    # Preferences
    preferred_language = Column(String(5), default="uz")  # uz, ru, en
    currency_preference = Column(String(3), default="UZS")  # UZS, USD
    
    # NEW: Admin-specific fields (only used when role is ADMIN/SUPER_ADMIN)
    password_hash = Column(String, nullable=True)  # For admin authentication
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    last_admin_login = Column(DateTime, nullable=True)
    password_changed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    cars = relationship("Car", back_populates="driver", cascade="all, delete-orphan")
    travel_preferences = relationship("TravelPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")
    emergency_contacts = relationship("EmergencyContact", back_populates="user", cascade="all, delete-orphan")
    sent_messages = relationship("Message", foreign_keys="[Message.sender_id]", back_populates="sender")
    received_messages = relationship("Message", foreign_keys="[Message.receiver_id]", back_populates="receiver")
    given_ratings = relationship("Rating", foreign_keys="[Rating.rater_id]", back_populates="rater")
    received_ratings = relationship("Rating", foreign_keys="[Rating.rated_user_id]", back_populates="rated_user")
    emergency_alerts = relationship("EmergencyAlert", foreign_keys="[EmergencyAlert.user_id]", back_populates="user")
    resolved_emergency_alerts = relationship("EmergencyAlert", foreign_keys="[EmergencyAlert.resolved_by]", back_populates="resolved_by_user")

    def __repr__(self) -> str:
        return f"<User {self.phone_number}>"

class SMSVerification(Base):
    __tablename__ = "sms_verifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String, index=True, nullable=False)
    code = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<SMSVerification {self.phone_number}>"

# --- NEW: ADMIN SECURITY TABLES ---

class AdminInvitation(Base):
    """Secure admin invitation system"""
    __tablename__ = "admin_invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False, index=True)
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token = Column(String(255), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    is_used = Column(Boolean, default=False)
    role = Column(SQLAlchemyEnum(AdminRole), default=AdminRole.ADMIN)
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    inviter = relationship("User", backref="sent_admin_invitations")

class AdminMFAToken(Base):
    """Multi-factor authentication tokens for admin login"""
    __tablename__ = "admin_mfa_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    admin = relationship("User")

class AdminAuditLog(Base):
    """Comprehensive audit logging for admin actions"""
    __tablename__ = "admin_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)  # "approve_driver", "reject_car", "login"
    resource_type = Column(String(50), nullable=True)  # "driver", "car", "user"
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    details = Column(JSON, nullable=True)  # Additional context
    ip_address = Column(String(45), nullable=True)  # IPv4/IPv6
    user_agent = Column(String(500), nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    timestamp = Column(DateTime, nullable=False, server_default=func.now())

    admin = relationship("User")

class AdminPasswordHistory(Base):
    """Track password history to prevent reuse"""
    __tablename__ = "admin_password_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    admin = relationship("User")

# --- EXISTING MODELS (Enhanced) ---

class Car(Base):
    __tablename__ = "cars"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    make = Column(String, nullable=False)
    model = Column(String, nullable=False)
    license_plate = Column(String, unique=True, index=True, nullable=False)
    color = Column(String, nullable=False)
    seats_count = Column(Integer, nullable=False, default=4)
    verification_status = Column(SQLAlchemyEnum(CarVerificationStatus), nullable=False, default=CarVerificationStatus.PENDING_VERIFICATION)
    admin_verification_notes = Column(Text, nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)
    
    # Enhanced car features
    year = Column(Integer, nullable=True)
    car_image_url = Column(String, nullable=True)
    features = Column(JSON, nullable=True)  # ["ac", "wifi", "music", "phone_charger"]
    comfort_level = Column(String(20), nullable=True)  # economy, comfort, luxury
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    driver = relationship("User", back_populates="cars")

    def __repr__(self) -> str:
        return f"<Car {self.license_plate}>"

class Trip(Base):
    __tablename__ = "trips"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    car_id = Column(UUID(as_uuid=True), ForeignKey("cars.id", ondelete="SET NULL"), nullable=True)
    from_location_text = Column(String, nullable=False)
    to_location_text = Column(String, nullable=False)
    departure_datetime = Column(DateTime, nullable=False)
    estimated_arrival_datetime = Column(DateTime, nullable=True)
    price_per_seat = Column(Numeric(10, 2), nullable=False)
    total_seats_offered = Column(Integer, nullable=False)
    available_seats = Column(Integer, nullable=False)
    status = Column(SQLAlchemyEnum(TripStatus), nullable=False, default=TripStatus.SCHEDULED)
    additional_info = Column(String, nullable=True)
    
    # Enhanced trip features
    intermediate_stops = Column(JSON, nullable=True)  # [{"location": "Guliston", "duration_minutes": 15}]
    trip_preferences = Column(JSON, nullable=True)  # {"smoking": false, "music": true, "pets": false}
    is_recurring = Column(Boolean, default=False)
    recurring_pattern = Column(JSON, nullable=True)  # {"frequency": "weekly", "days": ["monday", "friday"]}
    is_instant_booking = Column(Boolean, default=False)
    max_detour_km = Column(Integer, default=5)  # Maximum detour for pickup/dropoff
    price_negotiable = Column(Boolean, default=False)
    estimated_distance_km = Column(Integer, nullable=True)
    estimated_duration_minutes = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    driver = relationship("User", backref="created_trips")
    car = relationship("Car", backref="trips_assigned")
    bookings = relationship("Booking", back_populates="trip", cascade="all, delete-orphan")
    message_threads = relationship("MessageThread", back_populates="trip", cascade="all, delete-orphan")
    price_negotiations = relationship("PriceNegotiation", back_populates="trip", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Trip {self.id} from {self.from_location_text} to {self.to_location_text}>"

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    passenger_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    seats_booked = Column(Integer, nullable=False, default=1)
    total_price = Column(Numeric(10, 2), nullable=False)
    status = Column(SQLAlchemyEnum(BookingStatus), nullable=False, default=BookingStatus.CONFIRMED)
    booking_time = Column(DateTime, nullable=False, server_default=func.now())
    
    # Enhanced booking features
    pickup_location = Column(String, nullable=True)  # Specific pickup point
    dropoff_location = Column(String, nullable=True)  # Specific dropoff point
    special_requests = Column(Text, nullable=True)
    payment_method = Column(String(20), default="cash")  # cash, card, wallet
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    trip = relationship("Trip", back_populates="bookings")
    passenger = relationship("User", backref="trip_bookings")

    def __repr__(self) -> str:
        return f"<Booking {self.id} for Trip {self.trip_id}>"

# --- ENHANCED FEATURE MODELS ---

class TravelPreference(Base):
    """User travel preferences for better matching"""
    __tablename__ = "travel_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Preference settings
    smoking_allowed = Column(Boolean, default=False)
    pets_allowed = Column(Boolean, default=False)
    music_allowed = Column(Boolean, default=True)
    talking_allowed = Column(Boolean, default=True)
    
    # Gender preferences for safety (important in Uzbekistan)
    preferred_driver_gender = Column(String(10), nullable=True)  # male, female, any
    preferred_passenger_gender = Column(String(10), nullable=True)  # male, female, any
    
    # Comfort preferences
    preferred_comfort_level = Column(String(20), default="economy")  # economy, comfort, luxury
    max_price_per_km = Column(Numeric(6, 2), nullable=True)
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="travel_preferences")

class MessageThread(Base):
    """Message threads between trip participants"""
    __tablename__ = "message_threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    trip = relationship("Trip", back_populates="message_threads")
    messages = relationship("Message", back_populates="thread", cascade="all, delete-orphan")
    participants = relationship("ThreadParticipant", back_populates="thread", cascade="all, delete-orphan")

class ThreadParticipant(Base):
    """Participants in a message thread"""
    __tablename__ = "thread_participants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("message_threads.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    joined_at = Column(DateTime, nullable=False, server_default=func.now())
    last_read_at = Column(DateTime, nullable=True)

    thread = relationship("MessageThread", back_populates="participants")
    user = relationship("User")

class Message(Base):
    """Messages within threads"""
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("message_threads.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    
    message_type = Column(SQLAlchemyEnum(MessageType), default=MessageType.TEXT)
    content = Column(Text, nullable=False)
    message_metadata = Column(JSON, nullable=True)  # For location, system messages, etc.
    
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    thread = relationship("MessageThread", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_messages")
    receiver = relationship("User", foreign_keys=[receiver_id], back_populates="received_messages")

class Rating(Base):
    """User ratings and reviews"""
    __tablename__ = "ratings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    booking_id = Column(UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=True)
    rater_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rated_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    rating_type = Column(SQLAlchemyEnum(RatingType), nullable=False)
    rating = Column(Integer, nullable=False)  # 1-5 stars
    review = Column(Text, nullable=True)
    
    # Detailed ratings
    punctuality = Column(Integer, nullable=True)  # 1-5
    cleanliness = Column(Integer, nullable=True)  # 1-5
    communication = Column(Integer, nullable=True)  # 1-5
    driving_quality = Column(Integer, nullable=True)  # 1-5 (for drivers)
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    trip = relationship("Trip")
    booking = relationship("Booking")
    rater = relationship("User", foreign_keys=[rater_id], back_populates="given_ratings")
    rated_user = relationship("User", foreign_keys=[rated_user_id], back_populates="received_ratings")

class Notification(Base):
    """Notification system for SMS/Push"""
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    notification_type = Column(SQLAlchemyEnum(NotificationType), nullable=False)
    status = Column(SQLAlchemyEnum(NotificationStatus), default=NotificationStatus.PENDING)
    
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    data = Column(JSON, nullable=True)  # Additional data for deep linking
    
    scheduled_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    
    # For SMS
    phone_number = Column(String, nullable=True)
    
    # For Push
    push_token = Column(String, nullable=True)
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    user = relationship("User")

class EmergencyContact(Base):
    """Emergency contacts for safety"""
    __tablename__ = "emergency_contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String(100), nullable=False)
    phone_number = Column(String(20), nullable=False)
    relationship_type = Column(String(50), nullable=False)  # family, friend, colleague
    is_primary = Column(Boolean, default=False)
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    user = relationship("User", back_populates="emergency_contacts")

class EmergencyAlert(Base):
    """Emergency alerts and SOS"""
    __tablename__ = "emergency_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id", ondelete="SET NULL"), nullable=True)
    
    emergency_type = Column(SQLAlchemyEnum(EmergencyType), nullable=False)
    description = Column(Text, nullable=True)
    location_lat = Column(Numeric(10, 8), nullable=True)
    location_lng = Column(Numeric(11, 8), nullable=True)
    location_address = Column(String, nullable=True)
    
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    user = relationship("User", foreign_keys=[user_id], back_populates="emergency_alerts")
    trip = relationship("Trip")
    resolved_by_user = relationship("User", foreign_keys=[resolved_by], back_populates="resolved_emergency_alerts")

class PriceNegotiation(Base):
    """Price negotiation for flexible pricing"""
    __tablename__ = "price_negotiations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    passenger_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    original_price = Column(Numeric(10, 2), nullable=False)
    proposed_price = Column(Numeric(10, 2), nullable=False)
    final_price = Column(Numeric(10, 2), nullable=True)
    
    seats_requested = Column(Integer, default=1)
    message = Column(Text, nullable=True)
    
    status = Column(SQLAlchemyEnum(PriceNegotiationStatus), default=PriceNegotiationStatus.PENDING)
    expires_at = Column(DateTime, nullable=False)
    
    responded_at = Column(DateTime, nullable=True)
    response_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    trip = relationship("Trip", back_populates="price_negotiations")
    passenger = relationship("User")

class UserSettings(Base):
    """User application settings"""
    __tablename__ = "user_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Notification preferences
    sms_notifications = Column(Boolean, default=True)
    push_notifications = Column(Boolean, default=True)
    email_notifications = Column(Boolean, default=False)
    
    # Privacy settings
    show_phone_to_driver = Column(Boolean, default=True)
    show_profile_picture = Column(Boolean, default=True)
    allow_contact_from_passengers = Column(Boolean, default=True)
    
    # App preferences
    auto_location_detection = Column(Boolean, default=True)
    save_frequent_routes = Column(Boolean, default=True)
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    user = relationship("User")