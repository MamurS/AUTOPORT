# tests/test_trips.py
import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.asyncio
async def test_create_trip_as_passenger_fails(client: AsyncClient, passenger_token: str):
    """Test that passengers cannot create trips."""
    response = await client.post(
        "/api/v1/trips",
        headers={"Authorization": f"Bearer {passenger_token}"},
        json={
            "car_id": "00000000-0000-0000-0000-000000000000",
            "from_location_text": "Tashkent",
            "to_location_text": "Samarkand",
            "departure_datetime": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "price_per_seat": 100000,
            "total_seats_offered": 3
        }
    )
    assert response.status_code == 403
    assert "Only drivers can create trips" in response.json()["detail"]

@pytest.mark.asyncio
async def test_create_trip_as_driver(client: AsyncClient, driver_token: str, db_session: AsyncSession):
    """Test successful trip creation by driver."""
    # First create an approved car for the driver
    from models import Car, CarVerificationStatus
    from jose import jwt
    from config import settings
    
    # Decode token to get driver ID
    payload = jwt.decode(driver_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    driver_id = payload["sub"]
    
    # Create approved car
    car = Car(
        driver_id=driver_id,
        make="Toyota",
        model="Camry",
        license_plate="01A123BC",
        color="White",
        seats_count=4,
        verification_status=CarVerificationStatus.APPROVED
    )
    db_session.add(car)
    await db_session.commit()
    await db_session.refresh(car)
    
    # Create trip
    departure = datetime.now(timezone.utc) + timedelta(days=1)
    response = await client.post(
        "/api/v1/trips",
        headers={"Authorization": f"Bearer {driver_token}"},
        json={
            "car_id": str(car.id),
            "from_location_text": "Tashkent",
            "to_location_text": "Samarkand",
            "departure_datetime": departure.isoformat(),
            "price_per_seat": 100000,
            "total_seats_offered": 3
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["from_location_text"] == "Tashkent"
    assert data["to_location_text"] == "Samarkand"
    assert data["available_seats"] == 3
    assert data["status"] == "scheduled"

@pytest.mark.asyncio
async def test_search_trips(client: AsyncClient, db_session: AsyncSession):
    """Test trip search functionality."""
    # Create a driver with approved car and trip
    from crud.auth_crud import create_user
    from models import UserRole, UserStatus, Car, CarVerificationStatus, Trip, TripStatus
    
    driver = await create_user(db_session, "+998900000003")
    driver.role = UserRole.DRIVER
    driver.status = UserStatus.ACTIVE
    
    car = Car(
        driver_id=driver.id,
        make="Toyota",
        model="Camry",
        license_plate="01B456CD",
        color="Black",
        seats_count=4,
        verification_status=CarVerificationStatus.APPROVED
    )
    
    trip = Trip(
        driver_id=driver.id,
        car_id=car.id,
        from_location_text="Tashkent",
        to_location_text="Bukhara",
        departure_datetime=datetime.now(timezone.utc) + timedelta(hours=5),
        price_per_seat=150000,
        total_seats_offered=3,
        available_seats=3,
        status=TripStatus.SCHEDULED
    )
    
    db_session.add_all([driver, car, trip])
    await db_session.commit()
    
    # Search for trips
    response = await client.get(
        "/api/v1/trips/search",
        params={
            "from_location": "Tashkent",
            "to_location": "Bukhara"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["from_location_text"] == "Tashkent"
    assert data[0]["to_location_text"] == "Bukhara"

@pytest.mark.asyncio
async def test_trip_seat_validation(client: AsyncClient, driver_token: str, db_session: AsyncSession):
    """Test that total seats cannot exceed car capacity."""
    from models import Car, CarVerificationStatus
    from jose import jwt
    from config import settings
    
    payload = jwt.decode(driver_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    driver_id = payload["sub"]
    
    # Create car with 4 total seats (3 passenger seats)
    car = Car(
        driver_id=driver_id,
        make="Toyota",
        model="Corolla",
        license_plate="01C789EF",
        color="Silver",
        seats_count=4,
        verification_status=CarVerificationStatus.APPROVED
    )
    db_session.add(car)
    await db_session.commit()
    await db_session.refresh(car)
    
    # Try to create trip with 4 seats (exceeds passenger capacity)
    response = await client.post(
        "/api/v1/trips",
        headers={"Authorization": f"Bearer {driver_token}"},
        json={
            "car_id": str(car.id),
            "from_location_text": "Tashkent",
            "to_location_text": "Khiva",
            "departure_datetime": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "price_per_seat": 200000,
            "total_seats_offered": 4  # Too many!
        }
    )
    
    assert response.status_code == 400
    assert "exceeds car capacity" in response.json()["detail"]