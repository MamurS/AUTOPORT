# render_db_fix.py
# Add this to your config.py or database.py

import os

def get_database_url():
    """
    Get database URL, converting from Render's format if necessary.
    Render provides postgresql:// but SQLAlchemy async needs postgresql+asyncpg://
    """
    db_url = os.getenv("DATABASE_URL")
    
    if db_url and db_url.startswith("postgresql://"):
        # Convert to async format
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    return db_url or "postgresql+asyncpg://postgres:postgres@localhost:5432/autoport"