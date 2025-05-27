# tests/test_auth.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.asyncio
async def test_register_request_otp(client: AsyncClient):
    """Test requesting OTP for registration."""
    response = await client.post(
        "/api/v1/auth/register/request-otp",
        json={"phone_number": "+998901234567"}
    )
    assert response.status_code == 200
    assert "SMS OTP sent successfully" in response.json()["message"]

@pytest.mark.asyncio
async def test_register_with_existing_active_user(client: AsyncClient, db_session: AsyncSession):
    """Test registration fails for existing active user."""
    # Create an active user first
    from crud.auth_crud import create_user
    from models import UserStatus
    
    user = await create_user(db_session, "+998901234567")
    user.status = UserStatus.ACTIVE
    await db_session.commit()
    
    # Try to register again
    response = await client.post(
        "/api/v1/auth/register/request-otp",
        json={"phone_number": "+998901234567"}
    )
    assert response.status_code == 400
    assert "already exists and is active" in response.json()["detail"]

@pytest.mark.asyncio
async def test_verify_otp_and_complete_registration(client: AsyncClient, db_session: AsyncSession):
    """Test complete registration flow."""
    # Request OTP
    phone = "+998901234567"
    await client.post(
        "/api/v1/auth/register/request-otp",
        json={"phone_number": phone}
    )
    
    # Get the OTP from database
    from sqlalchemy import select
    from models import SMSVerification
    
    result = await db_session.execute(
        select(SMSVerification).where(SMSVerification.phone_number == phone)
    )
    verification = result.scalar_one()
    
    # Verify OTP and complete registration
    response = await client.post(
        "/api/v1/auth/register/verify-otp",
        json={
            "phone_number": phone,
            "code": verification.code,
            "full_name": "Test User"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["phone_number"] == phone
    assert data["user"]["full_name"] == "Test User"

@pytest.mark.asyncio
async def test_login_with_invalid_phone(client: AsyncClient):
    """Test login fails with non-existent phone."""
    response = await client.post(
        "/api/v1/auth/login/request-otp",
        json={"phone_number": "+998999999999"}
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]

@pytest.mark.asyncio
async def test_verify_invalid_otp(client: AsyncClient, db_session: AsyncSession):
    """Test OTP verification fails with wrong code."""
    phone = "+998901234567"
    
    # Create user and request OTP
    from crud.auth_crud import create_user
    from models import UserStatus
    
    user = await create_user(db_session, phone)
    user.status = UserStatus.ACTIVE
    await db_session.commit()
    
    await client.post(
        "/api/v1/auth/login/request-otp",
        json={"phone_number": phone}
    )
    
    # Try wrong OTP
    response = await client.post(
        "/api/v1/auth/login/verify-otp",
        json={
            "phone_number": phone,
            "code": "000000"  # Wrong code
        }
    )
    
    assert response.status_code == 400
    assert "Invalid or expired OTP" in response.json()["detail"]