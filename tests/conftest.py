# tests/conftest.py
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from main import app
from database import Base, get_db
from config import settings

# Test database URL
TEST_DATABASE_URL = str(settings.DATABASE_URL).replace("/autoport", "/autoport_test")

# Create test engine
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)

@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a clean database session for each test."""
    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    async with TestSessionLocal() as session:
        yield session

@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with overridden database dependency."""
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def create_test_user(db_session: AsyncSession):
    """Factory fixture to create test users."""
    async def _create_user(phone: str, role: str = "passenger", status: str = "active"):
        from models import User, UserRole, UserStatus
        
        user = User(
            phone_number=phone,
            full_name=f"Test {role.capitalize()}",
            role=UserRole(role),
            status=UserStatus(status)
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user
    
    return _create_user

@pytest_asyncio.fixture
async def admin_token(create_test_user):
    """Create an admin user and return token."""
    from auth.jwt_handler import create_access_token
    
    user = await create_test_user("+998900000000", "admin", "active")
    return create_access_token(user.id, user.role.value)

@pytest_asyncio.fixture
async def driver_token(create_test_user):
    """Create a driver user and return token."""
    from auth.jwt_handler import create_access_token
    
    user = await create_test_user("+998900000001", "driver", "active")
    return create_access_token(user.id, user.role.value)

@pytest_asyncio.fixture
async def passenger_token(create_test_user):
    """Create a passenger user and return token."""
    from auth.jwt_handler import create_access_token
    
    user = await create_test_user("+998900000002", "passenger", "active")
    return create_access_token(user.id, user.role.value)