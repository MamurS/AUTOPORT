# File: database.py

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from config import settings # Import settings

# Database URL is now from settings
engine = create_async_engine(
    settings.DATABASE_URL, # Use settings
    echo=True,  # Keep True for development/debugging for now
    poolclass=NullPool,
)

async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()

# get_db with dependency-level transaction management
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session: Optional[AsyncSession] = None
    try:
        session = async_session()
        # Transaction management moved to the session yield block
        yield session
        # If endpoint was successful (no exception propagated out), commit.
        if session.is_active: # Check if session is still active and has a transaction
             await session.commit()
    except Exception:
        if session is not None and session.is_active: # Check if session exists and is active
            await session.rollback()
        raise # Re-raise exception for FastAPI to handle
    finally:
        if session is not None and session.is_active: # Check if session exists and is active
            await session.close()