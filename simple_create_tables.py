# simple_create_tables.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Your Render database URL
DATABASE_URL = "postgresql+asyncpg://autoport_db_user:fC2HgKlMAnQYBcm9GzMlhlvMD5Zj20sf@dpg-d0r028qdbo4c73cfdmng-a.oregon-postgres.render.com/autoport_db"

# SQL commands to create tables based on your FastAPI models
CREATE_TABLES_SQL = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number VARCHAR(20) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(20) NOT NULL DEFAULT 'PASSENGER',
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING_SMS_VERIFICATION',
    admin_verification_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Cars table
CREATE TABLE IF NOT EXISTS cars (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL,
    make VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    license_plate VARCHAR(20) UNIQUE NOT NULL,
    color VARCHAR(50) NOT NULL,
    seats_count INTEGER NOT NULL,
    verification_status VARCHAR(50) NOT NULL DEFAULT 'PENDING_VERIFICATION',
    admin_verification_notes TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (driver_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Trips table
CREATE TABLE IF NOT EXISTS trips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL,
    car_id UUID NOT NULL,
    from_location VARCHAR(255) NOT NULL,
    to_location VARCHAR(255) NOT NULL,
    departure_datetime TIMESTAMP WITH TIME ZONE NOT NULL,
    estimated_arrival TIMESTAMP WITH TIME ZONE,
    price_per_seat DECIMAL(10, 2) NOT NULL,
    total_seats INTEGER NOT NULL,
    available_seats INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'SCHEDULED',
    additional_info TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (driver_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE
);

-- Bookings table
CREATE TABLE IF NOT EXISTS bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID NOT NULL,
    passenger_id UUID NOT NULL,
    seats_booked INTEGER NOT NULL,
    total_price DECIMAL(10, 2) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'CONFIRMED',
    booking_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE,
    FOREIGN KEY (passenger_id) REFERENCES users(id) ON DELETE CASCADE
);

-- OTP codes table (if you use it)
CREATE TABLE IF NOT EXISTS otp_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number VARCHAR(20) NOT NULL,
    otp_code VARCHAR(10) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for better performance
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone_number);
CREATE INDEX IF NOT EXISTS idx_cars_driver ON cars(driver_id);
CREATE INDEX IF NOT EXISTS idx_trips_driver ON trips(driver_id);
CREATE INDEX IF NOT EXISTS idx_trips_departure ON trips(departure_datetime);
CREATE INDEX IF NOT EXISTS idx_bookings_trip ON bookings(trip_id);
CREATE INDEX IF NOT EXISTS idx_bookings_passenger ON bookings(passenger_id);
CREATE INDEX IF NOT EXISTS idx_otp_phone ON otp_codes(phone_number);
"""

async def check_connection():
    """Test database connection"""
    print("🔍 Testing database connection...")
    try:
        engine = create_async_engine(DATABASE_URL)
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            print(f"✅ Connected to PostgreSQL: {version[:50]}...")
        await engine.dispose()
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

async def create_tables():
    """Create all tables using raw SQL"""
    print("\n🔨 Creating database tables...")
    try:
        engine = create_async_engine(DATABASE_URL)
        async with engine.begin() as conn:
            # Execute the SQL commands
            await conn.execute(text(CREATE_TABLES_SQL))
            print("✅ All tables created successfully!")
        await engine.dispose()
        return True
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        return False

async def verify_tables():
    """Check that all tables were created"""
    print("\n✅ Verifying table creation...")
    
    expected_tables = ['users', 'cars', 'trips', 'bookings', 'otp_codes']
    
    try:
        engine = create_async_engine(DATABASE_URL)
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """))
            existing_tables = [row[0] for row in result.fetchall()]
            
            print(f"📋 Found {len(existing_tables)} tables:")
            for table in expected_tables:
                if table in existing_tables:
                    print(f"   ✅ {table}")
                else:
                    print(f"   ❌ {table} - missing")
        
        await engine.dispose()
        return True
        
    except Exception as e:
        print(f"❌ Error verifying tables: {e}")
        return False

async def test_api():
    """Test the API endpoint"""
    print("\n🧪 Testing API endpoint...")
    
    try:
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            url = "https://autoport-api.onrender.com/api/v1/auth/register/request-otp"
            data = {"phone_number": "+998901111111"}
            
            async with session.post(url, json=data) as response:
                status = response.status
                text = await response.text()
                
                if status == 200:
                    print("✅ API test successful!")
                    print("🎉 Your AutoPort API is now working!")
                elif status == 500:
                    print("❌ Still getting 500 error")
                    print(f"Response: {text}")
                else:
                    print(f"⚠️  Got status {status}: {text}")
                    
    except Exception as e:
        print(f"❌ API test failed: {e}")
        print("💡 You can test manually with:")
        print('curl -X POST "https://autoport-api.onrender.com/api/v1/auth/register/request-otp" \\')
        print('  -H "Content-Type: application/json" \\')
        print('  -d \'{"phone_number": "+998901111111"}\'')

async def main():
    """Main initialization process"""
    print("🚀 AutoPort Database Initialization (Simple Version)")
    print("=" * 60)
    
    # Step 1: Test connection
    if not await check_connection():
        print("❌ Cannot proceed without database connection")
        return
    
    # Step 2: Create tables
    if await create_tables():
        # Step 3: Verify tables
        await verify_tables()
        
        # Step 4: Test API
        await test_api()
        
        print("\n🎉 Database initialization complete!")
        print("🔗 Your API should now work at: https://autoport-api.onrender.com")
        print("\n📋 Next steps:")
        print("   1. Test driver verification endpoints")
        print("   2. Create admin users")
        print("   3. Test the full workflow")
    else:
        print("❌ Failed to create tables")

if __name__ == "__main__":
    asyncio.run(main())