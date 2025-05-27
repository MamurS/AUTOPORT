# File: main.py

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import all your routers
from routers import admin, auth, bookings, cars, trips, users
from config import settings # Import settings

# Basic Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:     %(asctime)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API for the AutoPort intercity ride-sharing platform, enabling users to book trips, manage profiles, and for admins to verify drivers and cars.",
    contact={
        "name": f"{settings.APP_NAME} Support",
        "email": getattr(settings, "ADMIN_EMAIL", "support@example.com"), # Use setting if available
    },
    license_info={ # Example, can be removed or configured via settings too
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    # You can add root_path from settings if deploying behind a proxy:
    # root_path=settings.API_ROOT_PATH 
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development. In production, restrict to your specific frontend origins.
    allow_credentials=True,
    allow_methods=["*"], # Allows all standard methods.
    allow_headers=["*"], # Allows all headers.
)

# Include all the routers
app.include_router(auth.router, prefix="/api/v1") # Example: Adding a global API version prefix
app.include_router(users.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(cars.router, prefix="/api/v1")
app.include_router(trips.router, prefix="/api/v1")
app.include_router(bookings.router, prefix="/api/v1")

@app.get("/api/v1", tags=["Root"]) # Root for the API v1
async def read_root():
    """
    Root endpoint for the API.
    Returns a welcome message and API status.
    """
    return {
        "message": f"Welcome to the {settings.APP_NAME}!",
        "status": "healthy",
        "version": settings.APP_VERSION,
        "docs_url": app.docs_url, # Dynamically get docs URL
        "redoc_url": app.redoc_url # Dynamically get redoc URL
    }

# Health check endpoint (optional, but good practice)
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}


# Standard Uvicorn run block for easy execution during development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        log_level="info"
    )