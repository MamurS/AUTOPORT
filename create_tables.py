# create_tables.py
import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Your Render database URL (converted to async format)
DATABASE_URL = "postgresql+asyncpg://autoport_db_user:fC2HgKlMAnQYBcm9GzMlhlvMD5Zj20sf@dpg-d0r028qdbo4c73cfdmng-a.oregon-postgres.render.com/autoport_db"

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

async def check_existing_tables():
    """Check what tables already exist"""
    print("\n🔍 Checking existing tables...")
    try:
        engine = create_async_engine(DATABASE_URL)
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """))
            tables = [row[0] for row in result.fetchall()]
            
            if tables:
                print(f"📋 Found {len(tables)} existing tables:")
                for table in tables:
                    print(f"   - {table}")
            else:
                print("📋 No tables found (empty database)")
            
        await engine.dispose()
        return tables
    except Exception as e:
        print(f"❌ Error checking tables: {e}")
        return []

async def create_tables():
    """Create all database tables"""
    print("\n🔨 Creating database tables...")
    
    try:
        # Import your SQLAlchemy models
        # Adjust these imports based on your actual project structure
        from app.database import Base
        # Import all your model classes to register them
        from app.models.user import User
        from app.models.car import Car  
        from app.models.trip import Trip
        from app.models.booking import Booking
        # Add any other model imports you have
        
        engine = create_async_engine(DATABASE_URL)
        
        async with engine.begin() as conn:
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
            print("✅ All tables created successfully!")
        
        await engine.dispose()
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("💡 Make sure you're running this from your project root directory")
        print("💡 Check that your model imports are correct")
        return False
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        return False

async def verify_tables():
    """Verify tables were created correctly"""
    print("\n✅ Verifying table creation...")
    
    expected_tables = ['users', 'cars', 'trips', 'bookings']
    
    try:
        engine = create_async_engine(DATABASE_URL)
        async with engine.begin() as conn:
            for table in expected_tables:
                result = await conn.execute(text(f"""
                    SELECT COUNT(*) as count
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = '{table}';
                """))
                count = result.fetchone()[0]
                
                if count > 0:
                    print(f"   ✅ {table} - exists")
                else:
                    print(f"   ❌ {table} - missing")
        
        await engine.dispose()
        
    except Exception as e:
        print(f"❌ Error verifying tables: {e}")

async def test_api_after_creation():
    """Test if the API works after table creation"""
    print("\n🧪 Testing API endpoint...")
    
    import aiohttp
    
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://autoport-api.onrender.com/api/v1/auth/register/request-otp"
            data = {"phone_number": "+998901111111"}
            
            async with session.post(url, json=data) as response:
                status = response.status
                text = await response.text()
                
                if status == 200:
                    print("✅ API test successful - OTP request worked!")
                elif status == 500:
                    print("❌ Still getting 500 error - check if all tables were created")
                else:
                    print(f"⚠️  Got status {status}: {text}")
                    
    except Exception as e:
        print(f"❌ API test failed: {e}")

async def main():
    """Main initialization process"""
    print("🚀 AutoPort Database Initialization")
    print("=" * 50)
    
    # Step 1: Test connection
    if not await check_connection():
        print("❌ Cannot proceed without database connection")
        sys.exit(1)
    
    # Step 2: Check existing tables
    existing_tables = await check_existing_tables()
    
    # Step 3: Create tables if needed
    if not existing_tables:
        print("\n💡 Database is empty, creating tables...")
        if await create_tables():
            await verify_tables()
        else:
            print("❌ Failed to create tables")
            sys.exit(1)
    else:
        print("\n💡 Tables already exist, skipping creation...")
    
    # Step 4: Test API
    await test_api_after_creation()
    
    print("\n🎉 Database initialization complete!")
    print("🔗 Your API should now work at: https://autoport-api.onrender.com")

if __name__ == "__main__":
    # Install required packages if needed
    try:
        import aiohttp
        import asyncpg
    except ImportError:
        print("📦 Installing required packages...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "asyncpg", "aiohttp"])
        import aiohttp
        import asyncpg
    
    asyncio.run(main())