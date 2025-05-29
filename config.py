# File: config.py

import os
from typing import List, Optional, Any

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, field_validator, PostgresDsn, ValidationInfo

class Settings(BaseSettings):
    # Application Metadata (can be overridden by env vars)
    APP_NAME: str = "AutoPort API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development" # Default if not set by env
    API_V1_STR: str = "/api/v1"
    # PROJECT_NAME: str = "AutoPort" # Can be removed if APP_NAME is sufficient

    # Database Configuration
    # These are primarily for constructing a default DATABASE_URL if it's not fully provided by env.
    # For Render, DATABASE_URL will be fully provided by Render's fromDatabase directive.
    # For local Docker Compose, DATABASE_URL will be provided by docker-compose.yml environment.
    # For local direct 'python main.py' run, .env or these defaults will be used.
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_SERVER: str = "localhost:5433" # Default for local direct run connecting to Docker DB on host port 5433
    POSTGRES_DB: str = "autoport"
    
    # DATABASE_URL will be assembled by the validator below if not set in the environment.
    # If DATABASE_URL is set in the environment (e.g., by Render or docker-compose), that value takes precedence.
    DATABASE_URL: Optional[PostgresDsn] = None # Type hint for validation

    @field_validator("DATABASE_URL", mode='before')
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], info: ValidationInfo) -> Any:
        if isinstance(v, str) and v: # If DATABASE_URL is set in env and is a non-empty string
            db_url_to_check = v
        else: # Construct from parts if DATABASE_URL is not set or is empty in env
            values = info.data # Get other field values from the settings model
            user = values.get("POSTGRES_USER")
            password = values.get("POSTGRES_PASSWORD")
            server = values.get("POSTGRES_SERVER")
            db_name = values.get("POSTGRES_DB")
            db_url_to_check = f"postgresql://{user}:{password}@{server}/{db_name}"
            print(f"DEBUG [config.py]: DATABASE_URL not found in env, constructed default: {db_url_to_check}")
        
        # Ensure the +asyncpg driver is specified for SQLAlchemy async engine
        if "postgresql+asyncpg://" not in db_url_to_check and "postgresql://" in db_url_to_check:
            validated_url = db_url_to_check.replace("postgresql://", "postgresql+asyncpg://")
            print(f"DEBUG [config.py]: Modified DATABASE_URL to include +asyncpg: {validated_url}")
            return validated_url
        elif "postgresql+asyncpg://" in db_url_to_check:
            print(f"DEBUG [config.py]: DATABASE_URL already has +asyncpg: {db_url_to_check}")
            return db_url_to_check
        
        raise ValueError(f"Invalid or missing PostgreSQL DATABASE_URL format: {db_url_to_check}")

    # JWT Settings
    JWT_SECRET_KEY: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7" # Default DEV key
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS Settings
    # Expects a comma-separated string from environment variable
    BACKEND_CORS_ORIGINS_STR: str = "http://localhost:3000,http://127.0.0.1:3000" # Example for local frontend
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode='before')
    @classmethod
    def assemble_cors_origins(cls, v: Any, info: ValidationInfo) -> List[AnyHttpUrl]:
        # v will be the default [] if BACKEND_CORS_ORIGINS is not in env
        # We use BACKEND_CORS_ORIGINS_STR from env to build the list.
        origins_str = info.data.get("BACKEND_CORS_ORIGINS_STR")
        if isinstance(origins_str, str) and origins_str:
            return [origin.strip() for origin in origins_str.split(",") if origin.strip()]
        return [] # Return empty list if string is empty or not provided

    # Other optional settings
    # ADMIN_EMAIL: Optional[str] = "admin@example.com"
    # LOG_LEVEL: str = "INFO"
    
    model_config = SettingsConfigDict(
        env_file=".env",              # Load .env file
        env_file_encoding='utf-8',
        extra='ignore',               # Ignore extra fields from environment
        case_sensitive=False          # Env var names are typically case-insensitive on some systems
    )

settings = Settings()

# Optional: Add a print statement here during startup to see loaded settings
# print(f"DEBUG [config.py]: Loaded settings - DB URL: {settings.DATABASE_URL}")
# print(f"DEBUG [config.py]: Loaded settings - JWT Secret Key (partial): {settings.JWT_SECRET_KEY[:10]}...")
# print(f"DEBUG [config.py]: Loaded settings - CORS Origins: {settings.BACKEND_CORS_ORIGINS}")