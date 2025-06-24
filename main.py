# File: main.py (Complete updated version with admin auth and fixed CORS)

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text  # ADD THIS IMPORT
from sqlalchemy.ext.asyncio import AsyncSession

# Import existing routers
from routers import (
    auth, 
    users, 
    cars, 
    trips, 
    bookings, 
    admin,
    preferences,
    emergency,
    ratings,
    notifications,
    messaging,
    negotiations
)

# Import NEW admin auth router
from routers import admin_auth

from config import settings
from database import engine, get_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("🚀 Starting AutoPort API...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Database URL: {str(settings.DATABASE_URL)[:50]}...")
    
    # Test database connection
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))  # FIX: Add text() wrapper
        logger.info("✅ Database connection successful")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down AutoPort API...")
    await engine.dispose()

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AutoPort - Modern Ride Sharing Platform for Uzbekistan",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan
)

# CORS middleware - UPDATED FOR ADMIN CONSOLE AND DEPLOYMENT
cors_origins = getattr(settings, 'BACKEND_CORS_ORIGINS', None) or []

# Add specific origins for admin console and development
additional_origins = [
    "http://localhost:3000",           # React dev server
    "http://localhost:8080",           # Vue/other dev server
    "http://127.0.0.1:3000",          # Alternative localhost
    "http://127.0.0.1:8080",          # Alternative localhost
    "http://localhost:5173",           # Vite dev server
    "http://localhost:19006",          # Expo/React Native dev server
    "http://127.0.0.1:19006",          # Alternative localhost for Expo
    "null"                             # For file:// protocol (local HTML files)
]

# If we have configured origins, combine them with additional ones
if cors_origins and cors_origins != []:
    if isinstance(cors_origins, str):
        cors_origins = [cors_origins]
    all_origins = list(set(cors_origins + additional_origins))
else:
    # No configured origins - allow all for development
    all_origins = ["*"]

# Remove 'null' if we're allowing all origins (they conflict)
if "*" in all_origins and "null" in all_origins:
    all_origins.remove("null")

app.add_middleware(
    CORSMiddleware,
    allow_origins=all_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Accept-Language", 
        "Content-Language",
        "Content-Type",
        "Authorization",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers",
        "X-Requested-With",
    ],
)

# Log CORS configuration
logger.info(f"🌐 CORS Origins configured: {all_origins}")

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    start_time = time.time()
    
    # Log request
    logger.info(f"📨 {request.method} {request.url.path} - {request.client.host}")
    
    # Process request
    response = await call_next(request)
    
    # Log response
    process_time = time.time() - start_time
    logger.info(f"📤 {request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
    
    return response

# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(f"❌ Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred. Please try again later.",
            "error_id": str(id(exc))  # Simple error tracking
        }
    )

# Include routers with proper prefixes

# === AUTHENTICATION ROUTERS ===
app.include_router(
    auth.router, 
    prefix=settings.API_V1_STR,
    tags=["Authentication"]
)

app.include_router(
    admin_auth.router, 
    prefix=settings.API_V1_STR,
    tags=["Admin Authentication"]
)

# === USER MANAGEMENT ROUTERS ===
app.include_router(
    users.router, 
    prefix=settings.API_V1_STR,
    tags=["Users"]
)

app.include_router(
    preferences.router, 
    prefix=settings.API_V1_STR,
    tags=["User Preferences"]
)

# === DRIVER & CAR MANAGEMENT ===
app.include_router(
    cars.router, 
    prefix=settings.API_V1_STR,
    tags=["Cars"]
)

# === TRIP & BOOKING MANAGEMENT ===
app.include_router(
    trips.router, 
    prefix=settings.API_V1_STR,
    tags=["Trips"]
)

app.include_router(
    bookings.router, 
    prefix=settings.API_V1_STR,
    tags=["Bookings"]
)

app.include_router(
    negotiations.router, 
    prefix=settings.API_V1_STR,
    tags=["Price Negotiations"]
)

# === COMMUNICATION & SOCIAL ===
app.include_router(
    messaging.router, 
    prefix=settings.API_V1_STR,
    tags=["Messaging"]
)

app.include_router(
    ratings.router, 
    prefix=settings.API_V1_STR,
    tags=["Ratings & Reviews"]
)

app.include_router(
    notifications.router, 
    prefix=settings.API_V1_STR,
    tags=["Notifications"]
)

# === SAFETY & EMERGENCY ===
app.include_router(
    emergency.router, 
    prefix=settings.API_V1_STR,
    tags=["Emergency & Safety"]
)

# === ADMIN MANAGEMENT ===
app.include_router(
    admin.router, 
    prefix=settings.API_V1_STR,
    tags=["Admin Management"]
)

# === ROOT ENDPOINTS ===

@app.get("/", tags=["Root"])
async def root():
    """API root endpoint with basic information."""
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "status": "operational",
        "docs": f"{settings.API_V1_STR}/docs",
        "admin_docs": f"{settings.API_V1_STR}/docs#tag/Admin-Authentication",
        "cors_origins": len(all_origins)
    }

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for monitoring."""
    try:
        # Test database connection
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))  # FIX: Add text() wrapper
        
        return {
            "status": "healthy",
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "database": "connected",
            "cors_configured": True,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "version": settings.APP_VERSION,
                "database": "disconnected",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

@app.get("/info", tags=["Info"])
async def api_info():
    """API information and available endpoints."""
    return {
        "api_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "features": {
            "user_authentication": "OTP-based SMS authentication",
            "admin_authentication": "Email + Password + MFA",
            "ride_sharing": "Trip creation and booking system",
            "real_time_messaging": "In-trip communication",
            "price_negotiation": "Flexible pricing system",
            "safety_features": "Emergency alerts and contacts",
            "rating_system": "Driver and passenger reviews",
            "admin_panel": "Comprehensive admin management"
        },
        "authentication": {
            "users": "SMS OTP",
            "admins": "Email + Password + MFA"
        },
        "endpoints": {
            "api_docs": f"{settings.API_V1_STR}/docs",
            "health_check": "/health",
            "user_auth": f"{settings.API_V1_STR}/auth",
            "admin_auth": f"{settings.API_V1_STR}/auth/admin",
            "admin_panel": f"{settings.API_V1_STR}/admin"
        },
        "cors": {
            "configured_origins": len(all_origins),
            "allows_credentials": True,
            "admin_console_supported": True
        }
    }

if __name__ == "__main__":
    import uvicorn
    
    # Development server configuration
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True if settings.ENVIRONMENT == "development" else False,
        log_level="info",
        access_log=True
    )