# File: database.py (Corrected to pass string URL to engine)

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from config import settings # Import settings

# Database URL is now from settings
engine = create_async_engine(
    str(settings.DATABASE_URL), # Convert Pydantic DSN object to string for SQLAlchemy
    echo=True,  # Keep True for development/debugging for now
    poolclass=NullPool, # Good for Alembic and some async setups
)

# Create async session factory
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False, # Good default for FastAPI
    autocommit=False,       # Explicitly False (SQLAlchemy default)
    autoflush=False         # Explicitly False (SQLAlchemy default is True)
)

# Create base class for all SQLAlchemy models
Base = declarative_base()

# FastAPI dependency to get a database session
# This version manages the transaction at the dependency level (commits on success, rolls back on error)
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session: Optional[AsyncSession] = None
    try:
        session = async_session() # Create a new session from the factory
        # The transaction context will be implicitly handled by SQLAlchemy's async session
        # or explicitly by a "async with session.begin():" block if used by the caller,
        # though with this get_db pattern, the caller typically doesn't manage transactions.
        yield session
        # If the endpoint function (and all its operations) completed without raising an exception,
        # commit the transaction here.
        if session.is_active: # Check if session is still active (i.e., no rollback happened due to earlier exception)
             await session.commit()
    except Exception:
        # If any exception occurred in the endpoint or during the commit above,
        # roll back the transaction.
        if session is not None and session.is_active:
            await session.rollback()
        raise # Re-raise the exception so FastAPI can handle it and return an appropriate error response
    finally:
        # Always close the session when the request is done.
        if session is not None and session.is_active:
            await session.close()