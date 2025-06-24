# File: config.py (Complete updated version with admin security settings)

import os
from typing import List, Optional, Any

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, field_validator, PostgresDsn, ValidationInfo, EmailStr

class Settings(BaseSettings):
    # ===== APPLICATION METADATA =====
    APP_NAME: str = "AutoPort API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"  # development, staging, production
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # ===== DATABASE CONFIGURATION =====
    # Primary database URL (will be set by Render/Docker or constructed from parts)
    DATABASE_URL: Optional[PostgresDsn] = None
    
    # Database components (for local development)
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_SERVER: str = "localhost:5433"
    POSTGRES_DB: str = "autoport"
    
    # Database pool settings
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    @field_validator("DATABASE_URL", mode='before')
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], info: ValidationInfo) -> Any:
        """Assemble database URL from components if not provided."""
        if isinstance(v, str) and v:
            db_url_to_check = v
        else:
            values = info.data
            user = values.get("POSTGRES_USER")
            password = values.get("POSTGRES_PASSWORD")
            server = values.get("POSTGRES_SERVER")
            db_name = values.get("POSTGRES_DB")
            db_url_to_check = f"postgresql://{user}:{password}@{server}/{db_name}"
        
        # Ensure async driver
        if "postgresql+asyncpg://" not in db_url_to_check and "postgresql://" in db_url_to_check:
            return db_url_to_check.replace("postgresql://", "postgresql+asyncpg://")
        elif "postgresql+asyncpg://" in db_url_to_check:
            return db_url_to_check
        
        raise ValueError(f"Invalid PostgreSQL DATABASE_URL format: {db_url_to_check}")

    # ===== JWT CONFIGURATION =====
    JWT_SECRET_KEY: str = "your-super-secret-jwt-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ===== ADMIN SECURITY CONFIGURATION =====
    # Admin password policy
    ADMIN_MIN_PASSWORD_LENGTH: int = 12
    ADMIN_PASSWORD_HISTORY_COUNT: int = 5
    ADMIN_ACCOUNT_LOCKOUT_ATTEMPTS: int = 5
    ADMIN_ACCOUNT_LOCKOUT_DURATION_MINUTES: int = 30
    
    # Admin MFA settings
    ADMIN_MFA_CODE_EXPIRE_MINUTES: int = 5
    ADMIN_INVITATION_EXPIRE_HOURS: int = 24
    
    # Admin session settings
    ADMIN_SESSION_TIMEOUT_MINUTES: int = 60
    ADMIN_REQUIRE_MFA: bool = True

    # ===== EMAIL CONFIGURATION =====
    # SMTP settings for admin MFA and invitations
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: EmailStr = "noreply@autoport.uz"
    SMTP_FROM_NAME: str = "AutoPort Admin"
    SMTP_USE_TLS: bool = True
    
    # Email template settings
    EMAIL_TEMPLATES_DIR: str = "templates/emails"
    FRONTEND_URL: str = "https://autoport.uz"
    ADMIN_FRONTEND_URL: str = "https://admin.autoport.uz"

    # ===== CORS CONFIGURATION =====
    BACKEND_CORS_ORIGINS_STR: str = "http://localhost:3000,http://127.0.0.1:3000,https://autoport.uz,https://admin.autoport.uz"
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode='before')
    @classmethod
    def assemble_cors_origins(cls, v: Any, info: ValidationInfo) -> List[AnyHttpUrl]:
        """Parse CORS origins from comma-separated string."""
        origins_str = info.data.get("BACKEND_CORS_ORIGINS_STR")
        if isinstance(origins_str, str) and origins_str:
            return [origin.strip() for origin in origins_str.split(",") if origin.strip()]
        return []

    # ===== SMS CONFIGURATION =====
    # SMS provider settings (for OTP)
    SMS_PROVIDER: str = "eskiz"  # eskiz, playmobile, etc.
    SMS_API_URL: str = "https://notify.eskiz.uz/api"
    SMS_API_TOKEN: str = ""
    SMS_FROM_NUMBER: str = "4546"
    
    # OTP settings
    OTP_EXPIRE_MINUTES: int = 5
    OTP_MAX_ATTEMPTS: int = 3
    OTP_RATE_LIMIT_PER_HOUR: int = 10

    # ===== SECURITY SETTINGS =====
    # General security
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    BCRYPT_ROUNDS: int = 12
    
    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000
    
    # Session settings
    SESSION_EXPIRE_HOURS: int = 24
    REMEMBER_ME_EXPIRE_DAYS: int = 30

    # ===== FILE UPLOAD CONFIGURATION =====
    # File storage settings
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_IMAGE_EXTENSIONS: List[str] = [".jpg", ".jpeg", ".png", ".webp"]
    ALLOWED_DOCUMENT_EXTENSIONS: List[str] = [".pdf", ".doc", ".docx"]
    
    # Cloud storage (optional)
    USE_CLOUD_STORAGE: bool = False
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_BUCKET_NAME: str = ""
    AWS_REGION: str = "us-east-1"

    # ===== EXTERNAL SERVICES =====
    # Payment processing
    PAYMENT_PROVIDER: str = "payme"  # payme, click, uzcard
    PAYME_MERCHANT_ID: str = ""
    PAYME_SECRET_KEY: str = ""
    
    # Maps and geolocation
    GOOGLE_MAPS_API_KEY: str = ""
    YANDEX_MAPS_API_KEY: str = ""
    
    # Push notifications
    FCM_SERVER_KEY: str = ""
    FCM_SENDER_ID: str = ""

    # ===== LOGGING CONFIGURATION =====
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE: Optional[str] = None
    
    # Sentry for error tracking (optional)
    SENTRY_DSN: Optional[str] = None

    # ===== PERFORMANCE SETTINGS =====
    # Caching
    REDIS_URL: Optional[str] = None
    CACHE_EXPIRE_SECONDS: int = 300
    
    # Background tasks
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None

    # ===== FEATURE FLAGS =====
    # Enable/disable features
    ENABLE_REGISTRATION: bool = True
    ENABLE_PRICE_NEGOTIATION: bool = True
    ENABLE_TRIP_RECURRING: bool = True
    ENABLE_EMERGENCY_FEATURES: bool = True
    ENABLE_RATING_SYSTEM: bool = True
    ENABLE_MESSAGING: bool = True
    
    # Admin features
    ENABLE_ADMIN_REGISTRATION: bool = False  # Only via invitation
    ENABLE_ADMIN_API_DOCS: bool = True
    ADMIN_REQUIRE_EMAIL_VERIFICATION: bool = True

    # ===== BUSINESS LOGIC SETTINGS =====
    # Trip settings
    MAX_TRIP_SEATS: int = 8
    MIN_TRIP_PRICE: float = 1000.0  # UZS
    MAX_TRIP_PRICE: float = 1000000.0  # UZS
    TRIP_CANCELLATION_HOURS: int = 2
    
    # Booking settings
    BOOKING_CONFIRMATION_MINUTES: int = 30
    AUTO_CANCEL_UNPAID_BOOKINGS_HOURS: int = 24
    
    # Rating settings
    MIN_RATING: int = 1
    MAX_RATING: int = 5
    RATING_DEADLINE_HOURS: int = 72

    # ===== MONITORING & HEALTH CHECKS =====
    HEALTH_CHECK_INTERVAL_SECONDS: int = 30
    ENABLE_METRICS: bool = True
    METRICS_PORT: int = 9090

    # ===== DEVELOPMENT SETTINGS =====
    # Only used in development
    MOCK_SMS: bool = False  # Mock SMS sending in development
    MOCK_EMAIL: bool = False  # Mock email sending in development
    FAKE_PAYMENTS: bool = False  # Use fake payment processing
    
    # Testing
    TEST_DATABASE_URL: Optional[str] = None
    PYTEST_TIMEOUT: int = 300

    # ===== MODEL CONFIGURATION =====
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        extra='ignore',
        case_sensitive=False,
        # Nested environment variables support
        env_nested_delimiter='__'
    )

    # ===== VALIDATION METHODS =====
    
    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment setting."""
        allowed = ["development", "staging", "production"]
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of: {allowed}")
        return v
    
    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level setting."""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of: {allowed}")
        return v.upper()

    # ===== COMPUTED PROPERTIES =====
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.ENVIRONMENT == "development"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.ENVIRONMENT == "production"
    
    @property
    def database_url_str(self) -> str:
        """Get database URL as string."""
        return str(self.DATABASE_URL)
    
    @property
    def admin_invite_url_template(self) -> str:
        """Template for admin invitation URLs."""
        return f"{self.ADMIN_FRONTEND_URL}/accept-invite?token={{token}}"

# Create settings instance
settings = Settings()

# ===== ENVIRONMENT-SPECIFIC OVERRIDES =====

if settings.is_production:
    # Production overrides - REQUIRE real credentials
    settings.DEBUG = False
    settings.MOCK_SMS = False
    settings.MOCK_EMAIL = False
    settings.FAKE_PAYMENTS = False
    settings.ENABLE_ADMIN_API_DOCS = False
    
    # Validate critical security credentials (these are absolutely required)
    if settings.JWT_SECRET_KEY == "your-super-secret-jwt-key-change-in-production":
        raise ValueError("JWT_SECRET_KEY must be changed from default in production")
    if settings.SECRET_KEY == "your-super-secret-key-change-in-production":
        raise ValueError("SECRET_KEY must be changed from default in production")
    
    # Log warnings for missing service credentials (but don't fail startup)
    if not settings.SMS_API_TOKEN:
        logger.warning("⚠️  SMS_API_TOKEN not configured - SMS services will be disabled")
        settings.MOCK_SMS = True
    if not settings.SMTP_PASSWORD:
        logger.warning("⚠️  SMTP_PASSWORD not configured - Email services will be disabled") 
        settings.MOCK_EMAIL = True
    
elif settings.is_development:
    # Development overrides
    settings.DEBUG = True
    settings.LOG_LEVEL = "DEBUG"
    
    # For development, still require real credentials but don't fail if missing
    settings.MOCK_SMS = not bool(settings.SMS_API_TOKEN)
    settings.MOCK_EMAIL = not bool(settings.SMTP_PASSWORD)

# ===== LOGGING CONFIGURATION =====

import logging
import sys

# Configure logging based on settings
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format=settings.LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        *([logging.FileHandler(settings.LOG_FILE)] if settings.LOG_FILE else [])
    ]
)

# Configure specific loggers
if settings.is_development:
    # More verbose logging in development
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
    logging.getLogger("uvicorn").setLevel(logging.DEBUG)
else:
    # Less verbose in production
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# Startup logging
logger = logging.getLogger(__name__)
logger.info(f"🔧 AutoPort API Configuration Loaded")
logger.info(f"📍 Environment: {settings.ENVIRONMENT}")
logger.info(f"🗄️  Database: {settings.database_url_str[:50]}...")
logger.info(f"🔐 Admin MFA: {'Enabled' if settings.ADMIN_REQUIRE_MFA else 'Disabled'}")
if settings.is_production:
    logger.info(f"📧 Email: {'Production Ready' if settings.SMTP_PASSWORD else 'Disabled - Configure SMTP_PASSWORD'}")
    logger.info(f"📱 SMS: {'Production Ready' if settings.SMS_API_TOKEN else 'Disabled - Configure SMS_API_TOKEN'}")
else:
    logger.info(f"📧 Email: {'Configured' if settings.SMTP_PASSWORD else 'Mock Mode'}")
    logger.info(f"📱 SMS: {'Configured' if settings.SMS_API_TOKEN else 'Mock Mode'}")

# ===== EXPORT COMMONLY USED VALUES =====

# For easy access in other modules
DATABASE_URL = settings.database_url_str
JWT_SECRET = settings.JWT_SECRET_KEY
ENVIRONMENT = settings.ENVIRONMENT
API_PREFIX = settings.API_V1_STR