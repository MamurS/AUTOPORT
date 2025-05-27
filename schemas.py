import re
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from decimal import Decimal

from pydantic import BaseModel, Field, validator
# Enums are now imported from models.py
from models import UserRole, UserStatus, CarVerificationStatus, TripStatus, BookingStatus

# Phone number validation regex for Uzbekistan format
PHONE_REGEX = r"^\+998[0-9]{9}$"

class UserBase(BaseModel):
    phone_number: str
    full_name: Optional[str] = None
    role: UserRole = UserRole.PASSENGER # Uses UserRole from models

    @validator("phone_number")
    def validate_phone_number(cls, v: str) -> str:
        if not re.match(PHONE_REGEX, v):
            raise ValueError("Phone number must be in Uzbekistan format: +998XXXXXXXXX")
        return v

class UserCreatePhoneNumber(BaseModel):
    phone_number: str = Field(..., description="Phone number in Uzbekistan format: +998XXXXXXXXX")

    @validator("phone_number")
    def validate_phone_number(cls, v: str) -> str:
        if not re.match(PHONE_REGEX, v):
            raise ValueError("Phone number must be in Uzbekistan format: +998XXXXXXXXX")
        return v

class UserCreateProfile(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)

class UserResponse(UserBase):
    id: UUID
    status: UserStatus # Uses UserStatus from models
    admin_verification_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class SMSVerificationCreate(BaseModel):
    """Internal schema for creating SMS verification records."""
    phone_number: str
    code: str
    expires_at: datetime

class SMSVerificationRequest(BaseModel):
    """Schema for verifying SMS OTP codes."""
    phone_number: str = Field(..., description="Phone number in Uzbekistan format: +998XXXXXXXXX")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")

    @validator("phone_number")
    def validate_phone_number(cls, v: str) -> str:
        if not re.match(PHONE_REGEX, v):
            raise ValueError("Phone number must be in Uzbekistan format: +998XXXXXXXXX")
        return v

    @validator("code")
    def validate_code(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("Verification code must contain only digits")
        return v

class UserVerifyOTPAndSetProfileRequest(BaseModel):
    """Schema for verifying OTP and setting user profile."""
    phone_number: str = Field(..., description="Phone number in Uzbekistan format: +998XXXXXXXXX")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")
    full_name: str = Field(..., min_length=2, max_length=100, description="User's full name")

    @validator("phone_number")
    def validate_phone_number(cls, v: str) -> str:
        if not re.match(PHONE_REGEX, v):
            raise ValueError("Phone number must be in Uzbekistan format: +998XXXXXXXXX")
        return v

    @validator("code")
    def validate_code(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("Verification code must contain only digits")
        return v

class TokenResponse(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# Car Schemas
class CarBase(BaseModel):
    make: str = Field(..., min_length=2, max_length=50)
    model: str = Field(..., min_length=1, max_length=50)
    license_plate: str = Field(..., min_length=4, max_length=15)
    color: str = Field(..., min_length=3, max_length=30)
    seats_count: Optional[int] = Field(default=4, ge=2, le=8)
    is_default: Optional[bool] = Field(default=False)

class CarCreate(CarBase):
    pass

class CarUpdate(BaseModel):
    make: Optional[str] = Field(None, min_length=2, max_length=50)
    model: Optional[str] = Field(None, min_length=1, max_length=50)
    license_plate: Optional[str] = Field(None, min_length=4, max_length=15)
    color: Optional[str] = Field(None, min_length=3, max_length=30)
    seats_count: Optional[int] = Field(None, ge=2, le=8)
    is_default: Optional[bool] = None

class CarResponse(CarBase):
    id: UUID
    driver_id: UUID
    verification_status: CarVerificationStatus # Uses CarVerificationStatus from models
    admin_verification_notes: Optional[str] = None
    is_default: bool # In previous good version, is_default was present here. Let's keep it.
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Trip Schemas
class TripBase(BaseModel):
    from_location_text: str = Field(..., min_length=3)
    to_location_text: str = Field(..., min_length=3)
    departure_datetime: datetime
    estimated_arrival_datetime: Optional[datetime] = None
    price_per_seat: Decimal = Field(..., ge=0)
    total_seats_offered: int = Field(..., gt=0, le=7)
    additional_info: Optional[str] = None

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
    status: Optional[TripStatus] = None # Uses TripStatus from models

class TripResponse(TripBase):
    id: UUID
    driver_id: UUID
    car_id: UUID
    available_seats: int
    status: TripStatus # Uses TripStatus from models
    created_at: datetime
    updated_at: datetime
    driver: Optional["UserResponse"] = None # Forward reference
    car: Optional["CarResponse"] = None # Forward reference

    class Config:
        from_attributes = True

# Booking Schemas
class BookingBase(BaseModel):
    trip_id: UUID
    seats_booked: int = Field(default=1, ge=1, le=4)

class BookingCreate(BookingBase):
    pass

class BookingUpdate(BaseModel):
    status: Optional[BookingStatus] = None # Uses BookingStatus from models

class BookingResponse(BookingBase):
    id: UUID
    passenger_id: UUID
    total_price: Decimal
    status: BookingStatus # Uses BookingStatus from models
    booking_time: datetime
    created_at: datetime
    updated_at: datetime
    trip: Optional[TripResponse] = None # Forward reference
    passenger: Optional["UserResponse"] = None # Forward reference

    class Config:
        from_attributes = True

# Admin Schemas
class AdminUpdateStatusRequest(BaseModel):
    admin_notes: Optional[str] = Field(None, description="Optional notes from the admin regarding the verification status update.", max_length=1000)

# NO update_forward_refs() or model_rebuild() calls needed for Pydantic v2