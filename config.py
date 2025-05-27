# config.py
import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, validator


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


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "AutoPort API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "AutoPort"
    
    # Database - now using the helper function
    DATABASE_URL: str = get_database_url()
    
    # JWT
    JWT_SECRET_KEY: str = "your-secret-key-here-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []
    
    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: str | List[str]) -> List[str] | str:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)
    
    # First Admin (for CLI setup)
    FIRST_ADMIN_PHONE: Optional[str] = None
    FIRST_ADMIN_NAME: Optional[str] = None
    
    # SMS Gateway (for future)
    SMS_GATEWAY_API_KEY: Optional[str] = None
    SMS_GATEWAY_URL: Optional[str] = None
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Create a single instance to be imported
settings = Settings()