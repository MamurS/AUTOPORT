# tests/test_auth_simple.py
import pytest
from fastapi.testclient import TestClient

def test_register_request_otp(client: TestClient):
    """Test requesting OTP for registration."""
    response = client.post(
        "/api/v1/auth/register/request-otp",
        json={"phone_number": "+998901234567"}
    )
    assert response.status_code == 200
    assert "SMS OTP sent successfully" in response.json()["message"]

def test_login_request_otp_without_user(client: TestClient):
    """Test login OTP request fails for non-existent user."""
    response = client.post(
        "/api/v1/auth/login/request-otp",
        json={"phone_number": "+998999999999"}
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_complete_registration_flow(client: TestClient, db):
    """Test complete registration flow with OTP."""
    phone = "+998901234567"
    
    # Step 1: Request OTP
    response = client.post(
        "/api/v1/auth/register/request-otp",
        json={"phone_number": phone}
    )
    assert response.status_code == 200
    
    # Step 2: Get OTP from database (in real tests, you'd mock SMS)
    from models import SMSVerification
    otp_record = db.query(SMSVerification).filter(
        SMSVerification.phone_number == phone,
        SMSVerification.is_used == False
    ).order_by(SMSVerification.created_at.desc()).first()
    
    assert otp_record is not None
    otp_code = otp_record.code
    
    # Step 3: Verify OTP and complete registration
    response = client.post(
        "/api/v1/auth/register/verify-otp",
        json={
            "phone_number": phone,
            "code": otp_code,
            "full_name": "Test User"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["phone_number"] == phone
    assert data["user"]["full_name"] == "Test User"