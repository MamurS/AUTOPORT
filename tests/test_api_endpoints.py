# tests/test_api_endpoints.py
"""
Integration tests for AutoPort API endpoints.
These tests use the FastAPI TestClient which handles async properly.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from database import Base, get_db
from config import settings

# Use in-memory SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def setup_database():
    """Create tables before each test and drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    """Create a test client."""
    with TestClient(app) as c:
        yield c

@pytest.fixture
def db():
    """Get database session."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
    
    def test_api_root(self, client):
        response = client.get("/api/v1")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

class TestAuthEndpoints:
    """Test authentication endpoints."""
    
    def test_register_request_otp(self, client):
        response = client.post(
            "/api/v1/auth/register/request-otp",
            json={"phone_number": "+998901234567"}
        )
        assert response.status_code == 200
        assert "SMS OTP sent successfully" in response.json()["message"]
    
    def test_register_duplicate_active_user(self, client, db):
        """Test registration fails for active user."""
        # First registration
        phone = "+998901234567"
        client.post("/api/v1/auth/register/request-otp", json={"phone_number": phone})
        
        # Get OTP and complete registration
        from models import SMSVerification
        otp = db.query(SMSVerification).filter(
            SMSVerification.phone_number == phone
        ).order_by(SMSVerification.created_at.desc()).first()
        
        client.post("/api/v1/auth/register/verify-otp", json={
            "phone_number": phone,
            "code": otp.code,
            "full_name": "Test User"
        })
        
        # Try to register again
        response = client.post(
            "/api/v1/auth/register/request-otp",
            json={"phone_number": phone}
        )
        assert response.status_code == 400
        assert "already exists and is active" in response.json()["detail"]
    
    def test_complete_registration_flow(self, client, db):
        """Test full registration with OTP verification."""
        phone = "+998901234568"
        
        # Request OTP
        response = client.post(
            "/api/v1/auth/register/request-otp",
            json={"phone_number": phone}
        )
        assert response.status_code == 200
        
        # Get OTP from DB
        from models import SMSVerification
        otp = db.query(SMSVerification).filter(
            SMSVerification.phone_number == phone
        ).order_by(SMSVerification.created_at.desc()).first()
        
        # Verify OTP
        response = client.post(
            "/api/v1/auth/register/verify-otp",
            json={
                "phone_number": phone,
                "code": otp.code,
                "full_name": "Test Driver"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["full_name"] == "Test Driver"
        
        return data["access_token"]
    
    def test_login_flow(self, client, db):
        """Test login for existing user."""
        # First create a user
        token = self.test_complete_registration_flow(client, db)
        
        phone = "+998901234568"
        
        # Request login OTP
        response = client.post(
            "/api/v1/auth/login/request-otp",
            json={"phone_number": phone}
        )
        assert response.status_code == 200
        
        # Get new OTP
        from models import SMSVerification
        otp = db.query(SMSVerification).filter(
            SMSVerification.phone_number == phone,
            SMSVerification.is_used == False
        ).order_by(SMSVerification.created_at.desc()).first()
        
        # Verify login OTP
        response = client.post(
            "/api/v1/auth/login/verify-otp",
            json={
                "phone_number": phone,
                "code": otp.code
            }
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

class TestProtectedEndpoints:
    """Test endpoints that require authentication."""
    
    def get_auth_token(self, client, db, phone="+998901234569"):
        """Helper to get auth token."""
        client.post("/api/v1/auth/register/request-otp", json={"phone_number": phone})
        
        from models import SMSVerification
        otp = db.query(SMSVerification).filter(
            SMSVerification.phone_number == phone
        ).order_by(SMSVerification.created_at.desc()).first()
        
        response = client.post("/api/v1/auth/register/verify-otp", json={
            "phone_number": phone,
            "code": otp.code,
            "full_name": "Test User"
        })
        return response.json()["access_token"]
    
    def test_get_profile_authenticated(self, client, db):
        """Test getting user profile with valid token."""
        token = self.get_auth_token(client, db)
        
        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["phone_number"] == "+998901234569"
    
    def test_get_profile_unauthenticated(self, client):
        """Test getting profile without token fails."""
        response = client.get("/api/v1/users/me")
        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]