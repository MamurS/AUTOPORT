# File: tests/test_admin_auth.py

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from main import app
from database import get_db, async_session
from models import User, UserRole, UserStatus, AdminInvitation, AdminMFAToken
from crud.admin_auth_crud import (
    create_bootstrap_admin, 
    get_admin_count,
    hash_password,
    validate_password_strength
)
from schemas import BootstrapAdminRequest

# Test database setup
@pytest.fixture
async def db_session():
    """Create a test database session."""
    async with async_session() as session:
        yield session

@pytest.fixture
async def client():
    """Create test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def bootstrap_admin_data():
    """Test data for bootstrap admin."""
    return BootstrapAdminRequest(
        email="admin@test.autoport.uz",
        full_name="Test Admin",
        password="SecureTestPass123!",
        confirm_password="SecureTestPass123!"
    )

@pytest.fixture
async def created_admin(db_session: AsyncSession, bootstrap_admin_data: BootstrapAdminRequest):
    """Create a test admin user."""
    admin = await create_bootstrap_admin(db_session, bootstrap_admin_data)
    await db_session.commit()
    return admin

class TestPasswordValidation:
    """Test password validation functionality."""
    
    def test_valid_password(self):
        """Test that valid passwords pass validation."""
        valid_password = "SecureTestPass123!"
        # Should not raise any exception
        validate_password_strength(valid_password)
    
    def test_password_too_short(self):
        """Test that short passwords are rejected."""
        with pytest.raises(Exception) as exc_info:
            validate_password_strength("Short1!")
        assert "12 characters" in str(exc_info.value)
    
    def test_password_no_uppercase(self):
        """Test that passwords without uppercase are rejected."""
        with pytest.raises(Exception) as exc_info:
            validate_password_strength("securetestpass123!")
        assert "uppercase" in str(exc_info.value)
    
    def test_password_no_lowercase(self):
        """Test that passwords without lowercase are rejected."""
        with pytest.raises(Exception) as exc_info:
            validate_password_strength("SECURETESTPASS123!")
        assert "lowercase" in str(exc_info.value)
    
    def test_password_no_numbers(self):
        """Test that passwords without numbers are rejected."""
        with pytest.raises(Exception) as exc_info:
            validate_password_strength("SecureTestPass!")
        assert "number" in str(exc_info.value)
    
    def test_password_no_special_chars(self):
        """Test that passwords without special characters are rejected."""
        with pytest.raises(Exception) as exc_info:
            validate_password_strength("SecureTestPass123")
        assert "special character" in str(exc_info.value)
    
    def test_password_contains_email(self):
        """Test that passwords containing email are rejected."""
        with pytest.raises(Exception) as exc_info:
            validate_password_strength(
                "adminSecurePass123!", 
                {"email": "admin@test.com", "name": "Admin User"}
            )
        assert "email" in str(exc_info.value)

class TestBootstrapAdmin:
    """Test bootstrap admin creation."""
    
    @pytest.mark.asyncio
    async def test_create_first_admin_success(self, client: AsyncClient, bootstrap_admin_data: BootstrapAdminRequest):
        """Test successful creation of first admin."""
        response = await client.post(
            "/api/v1/auth/admin/bootstrap",
            json={
                "email": bootstrap_admin_data.email,
                "full_name": bootstrap_admin_data.full_name,
                "password": bootstrap_admin_data.password,
                "confirm_password": bootstrap_admin_data.confirm_password
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "access_token" in data
        assert "admin" in data
        assert data["admin"]["email"] == bootstrap_admin_data.email
        assert data["admin"]["role"] == "super_admin"
        assert data["token_type"] == "bearer"
    
    @pytest.mark.asyncio
    async def test_bootstrap_admin_password_mismatch(self, client: AsyncClient):
        """Test bootstrap fails with password mismatch."""
        response = await client.post(
            "/api/v1/auth/admin/bootstrap",
            json={
                "email": "admin@test.com",
                "full_name": "Test Admin",
                "password": "SecureTestPass123!",
                "confirm_password": "DifferentPassword123!"
            }
        )
        
        assert response.status_code == 400
        assert "do not match" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_bootstrap_admin_weak_password(self, client: AsyncClient):
        """Test bootstrap fails with weak password."""
        response = await client.post(
            "/api/v1/auth/admin/bootstrap",
            json={
                "email": "admin@test.com",
                "full_name": "Test Admin",
                "password": "weak",
                "confirm_password": "weak"
            }
        )
        
        assert response.status_code == 400
        assert "12 characters" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_bootstrap_admin_already_exists(self, client: AsyncClient, created_admin: User):
        """Test bootstrap fails when admin already exists."""
        response = await client.post(
            "/api/v1/auth/admin/bootstrap",
            json={
                "email": "another@test.com",
                "full_name": "Another Admin",
                "password": "SecureTestPass123!",
                "confirm_password": "SecureTestPass123!"
            }
        )
        
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

class TestAdminLogin:
    """Test admin login functionality."""
    
    @pytest.mark.asyncio
    async def test_admin_login_success(self, client: AsyncClient, created_admin: User):
        """Test successful admin login."""
        response = await client.post(
            "/api/v1/auth/admin/login",
            json={
                "email": created_admin.email,
                "password": "SecureTestPass123!"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "session_token" in data
        assert "expires_in" in data
        assert "MFA code sent" in data["message"]
    
    @pytest.mark.asyncio
    async def test_admin_login_invalid_email(self, client: AsyncClient):
        """Test admin login with invalid email."""
        response = await client.post(
            "/api/v1/auth/admin/login",
            json={
                "email": "nonexistent@test.com",
                "password": "SecureTestPass123!"
            }
        )
        
        assert response.status_code == 401
        assert "Invalid credentials" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_admin_login_invalid_password(self, client: AsyncClient, created_admin: User):
        """Test admin login with invalid password."""
        response = await client.post(
            "/api/v1/auth/admin/login",
            json={
                "email": created_admin.email,
                "password": "WrongPassword123!"
            }
        )
        
        assert response.status_code == 401
        assert "Invalid credentials" in response.json()["detail"]

class TestAdminMFA:
    """Test admin MFA functionality."""
    
    @pytest.mark.asyncio
    async def test_mfa_verification_success(self, client: AsyncClient, created_admin: User, db_session: AsyncSession):
        """Test successful MFA verification."""
        # First, login to get session token
        login_response = await client.post(
            "/api/v1/auth/admin/login",
            json={
                "email": created_admin.email,
                "password": "SecureTestPass123!"
            }
        )
        
        assert login_response.status_code == 200
        session_token = login_response.json()["session_token"]
        
        # Get the MFA code from database (in real scenario, it would be sent via email)
        # This is a simplified test approach
        from sqlalchemy import select
        result = await db_session.execute(
            select(AdminMFAToken)
            .where(AdminMFAToken.admin_id == created_admin.id)
            .where(AdminMFAToken.is_used == False)
            .order_by(AdminMFAToken.created_at.desc())
        )
        mfa_token = result.scalar_one_or_none()
        
        assert mfa_token is not None
        
        # Verify MFA
        mfa_response = await client.post(
            "/api/v1/auth/admin/verify-mfa",
            json={
                "session_token": session_token,
                "mfa_code": mfa_token.code
            }
        )
        
        assert mfa_response.status_code == 200
        data = mfa_response.json()
        
        assert "access_token" in data
        assert "admin" in data
        assert data["admin"]["email"] == created_admin.email
    
    @pytest.mark.asyncio
    async def test_mfa_verification_invalid_code(self, client: AsyncClient, created_admin: User):
        """Test MFA verification with invalid code."""
        # First, login to get session token
        login_response = await client.post(
            "/api/v1/auth/admin/login",
            json={
                "email": created_admin.email,
                "password": "SecureTestPass123!"
            }
        )
        
        session_token = login_response.json()["session_token"]
        
        # Try with invalid MFA code
        mfa_response = await client.post(
            "/api/v1/auth/admin/verify-mfa",
            json={
                "session_token": session_token,
                "mfa_code": "123456"  # Invalid code
            }
        )
        
        assert mfa_response.status_code == 401
        assert "Invalid or expired" in mfa_response.json()["detail"]

class TestAdminProtectedEndpoints:
    """Test admin-protected endpoints."""
    
    @pytest.mark.asyncio
    async def test_admin_profile_access(self, client: AsyncClient, created_admin: User):
        """Test admin profile access with valid token."""
        # Get admin token (simplified - in real test, go through full login flow)
        from auth.jwt_handler import create_access_token
        token = create_access_token(created_admin.id, created_admin.role.value)
        
        response = await client.get(
            "/api/v1/auth/admin/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["email"] == created_admin.email
        assert data["role"] == "super_admin"
    
    @pytest.mark.asyncio
    async def test_admin_endpoint_without_token(self, client: AsyncClient):
        """Test admin endpoint access without token."""
        response = await client.get("/api/v1/auth/admin/me")
        
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_admin_endpoint_with_user_token(self, client: AsyncClient, db_session: AsyncSession):
        """Test admin endpoint access with regular user token."""
        # Create a regular user
        regular_user = User(
            phone_number="+998901234567",
            full_name="Regular User",
            role=UserRole.PASSENGER,
            status=UserStatus.ACTIVE
        )
        db_session.add(regular_user)
        await db_session.commit()
        
        # Get user token
        from auth.jwt_handler import create_access_token
        token = create_access_token(regular_user.id, regular_user.role.value)
        
        response = await client.get(
            "/api/v1/auth/admin/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 403
        assert "Administrator access required" in response.json()["detail"]

class TestAdminInvitations:
    """Test admin invitation system."""
    
    @pytest.mark.asyncio
    async def test_super_admin_can_invite(self, client: AsyncClient, created_admin: User):
        """Test that super admin can invite new admin."""
        # Get super admin token
        from auth.jwt_handler import create_access_token
        token = create_access_token(created_admin.id, created_admin.role.value)
        
        response = await client.post(
            "/api/v1/auth/admin/invite",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "newadmin@test.com",
                "role": "admin",
                "message": "Welcome to the team!"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["email"] == "newadmin@test.com"
        assert data["role"] == "admin"
        assert not data["is_used"]
    
    @pytest.mark.asyncio
    async def test_regular_admin_cannot_invite(self, client: AsyncClient, db_session: AsyncSession):
        """Test that regular admin cannot invite new admin."""
        # Create a regular admin (not super admin)
        regular_admin = User(
            phone_number="+998901234568",
            full_name="Regular Admin",
            email="regularadmin@test.com",
            role=UserRole.ADMIN,  # Not SUPER_ADMIN
            status=UserStatus.ACTIVE,
            password_hash=hash_password("SecureTestPass123!")
        )
        db_session.add(regular_admin)
        await db_session.commit()
        
        # Get regular admin token
        from auth.jwt_handler import create_access_token
        token = create_access_token(regular_admin.id, regular_admin.role.value)
        
        response = await client.post(
            "/api/v1/auth/admin/invite",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "newadmin@test.com",
                "role": "admin"
            }
        )
        
        assert response.status_code == 403
        assert "Super administrator access required" in response.json()["detail"]

class TestAdminAuditLogging:
    """Test admin audit logging functionality."""
    
    @pytest.mark.asyncio
    async def test_admin_actions_are_logged(self, client: AsyncClient, created_admin: User, db_session: AsyncSession):
        """Test that admin actions are properly logged."""
        # Perform an admin action (get profile)
        from auth.jwt_handler import create_access_token
        token = create_access_token(created_admin.id, created_admin.role.value)
        
        response = await client.get(
            "/api/v1/auth/admin/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        
        # Check if action was logged (this would need to be implemented in the actual endpoint)
        # For now, just verify the endpoint works
        # In a real implementation, you'd check the AdminAuditLog table

# Integration test class
class TestAdminAuthIntegration:
    """Integration tests for complete admin auth flow."""
    
    @pytest.mark.asyncio
    async def test_complete_admin_flow(self, client: AsyncClient):
        """Test complete admin authentication flow from bootstrap to protected endpoint access."""
        
        # 1. Bootstrap first admin
        bootstrap_response = await client.post(
            "/api/v1/auth/admin/bootstrap",
            json={
                "email": "integration@test.com",
                "full_name": "Integration Test Admin",
                "password": "IntegrationTest123!",
                "confirm_password": "IntegrationTest123!"
            }
        )
        
        assert bootstrap_response.status_code == 200
        bootstrap_token = bootstrap_response.json()["access_token"]
        
        # 2. Access admin profile with bootstrap token
        profile_response = await client.get(
            "/api/v1/auth/admin/me",
            headers={"Authorization": f"Bearer {bootstrap_token}"}
        )
        
        assert profile_response.status_code == 200
        profile_data = profile_response.json()
        assert profile_data["email"] == "integration@test.com"
        assert profile_data["role"] == "super_admin"
        
        # 3. Login with credentials
        login_response = await client.post(
            "/api/v1/auth/admin/login",
            json={
                "email": "integration@test.com",
                "password": "IntegrationTest123!"
            }
        )
        
        assert login_response.status_code == 200
        assert "session_token" in login_response.json()
        
        # 4. Test admin management endpoints (if available)
        management_response = await client.get(
            "/api/v1/admin/verifications/drivers/pending",
            headers={"Authorization": f"Bearer {bootstrap_token}"}
        )
        
        # Should work even if no pending drivers
        assert management_response.status_code == 200

# Utility functions for tests
def create_test_admin_data(email: str = "test@admin.com") -> dict:
    """Create test admin data."""
    return {
        "email": email,
        "full_name": "Test Admin",
        "password": "SecureTestPass123!",
        "confirm_password": "SecureTestPass123!"
    }

def create_test_login_data(email: str = "test@admin.com") -> dict:
    """Create test login data."""
    return {
        "email": email,
        "password": "SecureTestPass123!"
    }

# Run tests with: pytest tests/test_admin_auth.py -v