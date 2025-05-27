import uuid
from enum import Enum # Using Python's built-in Enum
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Enum as SQLAlchemyEnum, func, Boolean, Integer, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database import Base

# --- Enums defined directly in models.py ---
class UserRole(str, Enum):
    PASSENGER = "passenger"
    DRIVER = "driver"
    ADMIN = "admin"

class UserStatus(str, Enum):
    PENDING_SMS_VERIFICATION = "pending_sms_verification"
    PENDING_PROFILE_COMPLETION = "pending_profile_completion" # For drivers after initial profile setup
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

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(
        SQLAlchemyEnum(UserRole),
        nullable=False,
        default=UserRole.PASSENGER
    )
    status = Column(
        SQLAlchemyEnum(UserStatus),
        nullable=False,
        default=UserStatus.PENDING_SMS_VERIFICATION # Default for new users
    )
    admin_verification_notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

    cars = relationship("Car", back_populates="driver", cascade="all, delete-orphan")
    # For User.created_trips, relies on backref from Trip.driver
    # For User.trip_bookings, relies on backref from Booking.passenger

    def __repr__(self) -> str:
        return f"<User {self.phone_number}>"

class SMSVerification(Base):
    __tablename__ = "sms_verifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String, index=True, nullable=False)
    code = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<SMSVerification {self.phone_number}>"

class Car(Base):
    __tablename__ = "cars"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    make = Column(String, nullable=False)
    model = Column(String, nullable=False)
    license_plate = Column(String, unique=True, index=True, nullable=False)
    color = Column(String, nullable=False)
    seats_count = Column(Integer, nullable=False, default=4)
    verification_status = Column(
        SQLAlchemyEnum(CarVerificationStatus),
        nullable=False,
        default=CarVerificationStatus.PENDING_VERIFICATION
    )
    admin_verification_notes = Column(Text, nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

    driver = relationship("User", back_populates="cars")
    # For Car.trips_assigned, relies on backref from Trip.car

    def __repr__(self) -> str:
        return f"<Car {self.license_plate}>"

class Trip(Base):
    __tablename__ = "trips"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    car_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cars.id", ondelete="SET NULL"),
        nullable=True
    )
    from_location_text = Column(String, nullable=False)
    to_location_text = Column(String, nullable=False)
    departure_datetime = Column(DateTime, nullable=False)
    estimated_arrival_datetime = Column(DateTime, nullable=True)
    price_per_seat = Column(Numeric(10, 2), nullable=False)
    total_seats_offered = Column(Integer, nullable=False)
    available_seats = Column(Integer, nullable=False)
    status = Column(
        SQLAlchemyEnum(TripStatus),
        nullable=False,
        default=TripStatus.SCHEDULED
    )
    additional_info = Column(String, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

    driver = relationship("User", backref="created_trips")
    car = relationship("Car", backref="trips_assigned")
    bookings = relationship("Booking", back_populates="trip", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Trip {self.id} from {self.from_location_text} to {self.to_location_text}>"

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id = Column(
        UUID(as_uuid=True),
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False
    )
    passenger_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    seats_booked = Column(Integer, nullable=False, default=1)
    total_price = Column(Numeric(10, 2), nullable=False)
    status = Column(
        SQLAlchemyEnum(BookingStatus),
        nullable=False,
        default=BookingStatus.CONFIRMED
    )
    booking_time = Column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

    trip = relationship("Trip", back_populates="bookings")
    passenger = relationship("User", backref="trip_bookings")

    def __repr__(self) -> str:
        return f"<Booking {self.id} for Trip {self.trip_id}>"