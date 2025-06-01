# create_enums.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Your Render database URL
DATABASE_URL = "postgresql+asyncpg://autoport_db_user:fC2HgKlMAnQYBcm9GzMlhlvMD5Zj20sf@dpg-d0r028qdbo4c73cfdmng-a.oregon-postgres.render.com/autoport_db"

# Create the missing ENUM types
ENUM_COMMANDS = [
    # Create UserRole enum
    """
    DO $$ 
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole') THEN
            CREATE TYPE userrole AS ENUM ('PASSENGER', 'DRIVER', 'ADMIN');
        END IF;
    END $$
    """,
    
    # Create UserStatus enum
    """
    DO $$ 
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userstatus') THEN
            CREATE TYPE userstatus AS ENUM (
                'PENDING_SMS_VERIFICATION', 
                'PENDING_PROFILE_COMPLETION', 
                'ACTIVE', 
                'BLOCKED'
            );
        END IF;
    END $$
    """,
    
    # Create CarVerificationStatus enum (if you have it)
    """
    DO $$ 
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'carverificationstatus') THEN
            CREATE TYPE carverificationstatus AS ENUM (
                'PENDING_VERIFICATION', 
                'APPROVED', 
                'REJECTED'
            );
        END IF;
    END $$
    """,
    
    # Create TripStatus enum (if you have it)
    """
    DO $$ 
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tripstatus') THEN
            CREATE TYPE tripstatus AS ENUM (
                'SCHEDULED', 
                'IN_PROGRESS', 
                'COMPLETED', 
                'CANCELLED_BY_DRIVER', 
                'FULL'
            );
        END IF;
    END $$
    """,
    
    # Create BookingStatus enum (if you have it)
    """
    DO $$ 
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'bookingstatus') THEN
            CREATE TYPE bookingstatus AS ENUM (
                'CONFIRMED', 
                'CANCELLED_BY_PASSENGER', 
                'CANCELLED_BY_DRIVER'
            );
        END IF;
    END $$
    """
]

# Update table columns to use the ENUMs
UPDATE_TABLES_COMMANDS = [
    # Update users table to use ENUMs
    """
    ALTER TABLE users 
    ALTER COLUMN role TYPE userrole USING role::userrole,
    ALTER COLUMN status TYPE userstatus USING status::userstatus
    """,
    
    # Update cars table if needed
    """
    DO $$ 
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.columns 
                  WHERE table_name = 'cars' AND column_name = 'verification_status') THEN
            ALTER TABLE cars 
            ALTER COLUMN verification_status TYPE carverificationstatus 
            USING verification_status::carverificationstatus;
        END IF;
    END $$
    """,
    
    # Update trips table if needed
    """
    DO $$ 
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.columns 
                  WHERE table_name = 'trips' AND column_name = 'status') THEN
            ALTER TABLE trips 
            ALTER COLUMN status TYPE tripstatus 
            USING status::tripstatus;
        END IF;
    END $$
    """,
    
    # Update bookings table if needed
    """
    DO $$ 
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.columns 
                  WHERE table_name = 'bookings' AND column_name = 'status') THEN
            ALTER TABLE bookings 
            ALTER COLUMN status TYPE bookingstatus 
            USING status::bookingstatus;
        END IF;
    END $$
    """
]

async def check_connection():
    """Test database connection"""
    print("🔍 Testing database connection...")
    try:
        engine = create_async_engine(DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"✅ Connected to PostgreSQL: {version[:50]}...")
        await engine.dispose()
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

async def check_existing_enums():
    """Check what ENUMs already exist"""
    print("\n🔍 Checking existing ENUMs...")
    try:
        engine = create_async_engine(DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT typname FROM pg_type 
                WHERE typtype = 'e' 
                ORDER BY typname
            """))
            enums = [row[0] for row in result.fetchall()]
            
            if enums:
                print(f"📋 Found {len(enums)} existing ENUMs:")
                for enum in enums:
                    print(f"   - {enum}")
            else:
                print("📋 No ENUMs found")
            
        await engine.dispose()
        return enums
    except Exception as e:
        print(f"❌ Error checking ENUMs: {e}")
        return []

async def create_enums():
    """Create all required ENUM types"""
    print("\n🔨 Creating ENUM types...")
    
    try:
        engine = create_async_engine(DATABASE_URL, echo=False)
        
        for i, enum_command in enumerate(ENUM_COMMANDS, 1):
            try:
                async with engine.begin() as conn:
                    await conn.execute(text(enum_command))
                
                # Extract enum name from command for display
                if "userrole" in enum_command:
                    print(f"   ✅ Created ENUM: userrole")
                elif "userstatus" in enum_command:
                    print(f"   ✅ Created ENUM: userstatus")
                elif "carverificationstatus" in enum_command:
                    print(f"   ✅ Created ENUM: carverificationstatus")
                elif "tripstatus" in enum_command:
                    print(f"   ✅ Created ENUM: tripstatus")
                elif "bookingstatus" in enum_command:
                    print(f"   ✅ Created ENUM: bookingstatus")
                    
            except Exception as e:
                if "already exists" in str(e):
                    print(f"   ⚠️  ENUM {i} already exists, skipping")
                else:
                    print(f"   ❌ Error with ENUM {i}: {e}")
                continue
        
        await engine.dispose()
        print("✅ ENUM creation completed!")
        return True
        
    except Exception as e:
        print(f"❌ Error creating ENUMs: {e}")
        return False

async def update_table_columns():
    """Update table columns to use ENUM types"""
    print("\n🔧 Updating table columns to use ENUMs...")
    
    try:
        engine = create_async_engine(DATABASE_URL, echo=False)
        
        for i, update_command in enumerate(UPDATE_TABLES_COMMANDS, 1):
            try:
                async with engine.begin() as conn:
                    await conn.execute(text(update_command))
                
                if i == 1:
                    print(f"   ✅ Updated users table columns")
                elif i == 2:
                    print(f"   ✅ Updated cars table columns")
                elif i == 3:
                    print(f"   ✅ Updated trips table columns")
                elif i == 4:
                    print(f"   ✅ Updated bookings table columns")
                    
            except Exception as e:
                print(f"   ⚠️  Update {i}: {e}")
                continue
        
        await engine.dispose()
        print("✅ Table column updates completed!")
        return True
        
    except Exception as e:
        print(f"❌ Error updating table columns: {e}")
        return False

async def verify_enums():
    """Verify ENUMs were created correctly"""
    print("\n✅ Verifying ENUM creation...")
    
    expected_enums = ['userrole', 'userstatus', 'carverificationstatus', 'tripstatus', 'bookingstatus']
    
    try:
        engine = create_async_engine(DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT typname FROM pg_type 
                WHERE typtype = 'e' 
                ORDER BY typname
            """))
            existing_enums = [row[0] for row in result.fetchall()]
            
            print(f"📋 Found {len(existing_enums)} ENUMs:")
            for enum in expected_enums:
                if enum in existing_enums:
                    print(f"   ✅ {enum}")
                else:
                    print(f"   ❌ {enum} - missing")
        
        await engine.dispose()
        return True
        
    except Exception as e:
        print(f"❌ Error verifying ENUMs: {e}")
        return False

async def test_api():
    """Test the API endpoint after ENUM creation"""
    print("\n🧪 Testing API endpoint...")
    
    try:
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            url = "https://autoport-api.onrender.com/api/v1/auth/register/request-otp"
            data = {"phone_number": "+998901111111"}
            
            async with session.post(url, json=data) as response:
                status = response.status
                text = await response.text()
                
                print(f"API Response: {status}")
                
                if status == 200:
                    print("✅ API test successful!")
                    print("🎉 Your AutoPort API is now working!")
                elif status == 400:
                    print("✅ Got 400 - API is working but may need SMS setup")
                elif status == 500:
                    print("❌ Still getting 500 error")
                    print(f"Response: {text}")
                else:
                    print(f"Response: {text}")
                    
    except ImportError:
        print("⚠️  aiohttp not installed, testing with curl...")
        print("💡 Test manually with:")
        print('curl -X POST "https://autoport-api.onrender.com/api/v1/auth/register/request-otp" \\')
        print('  -H "Content-Type: application/json" \\')
        print('  -d \'{"phone_number": "+998901111111"}\'')
    except Exception as e:
        print(f"❌ API test failed: {e}")

async def main():
    """Main ENUM creation process"""
    print("🚀 AutoPort ENUM Types Creation")
    print("=" * 50)
    
    # Step 1: Test connection
    if not await check_connection():
        print("❌ Cannot proceed without database connection")
        return
    
    # Step 2: Check existing ENUMs
    existing_enums = await check_existing_enums()
    
    # Step 3: Create ENUMs
    if await create_enums():
        # Step 4: Update table columns
        await update_table_columns()
        
        # Step 5: Verify ENUMs
        await verify_enums()
        
        # Step 6: Test API
        await test_api()
        
        print("\n🎉 ENUM creation complete!")
        print("🔗 Your API should now work at: https://autoport-api.onrender.com")
        print("\n📋 Next steps:")
        print("   1. Test authentication endpoints")
        print("   2. Test driver verification endpoints")
        print("   3. Create admin users")
    else:
        print("❌ Failed to create ENUMs")

if __name__ == "__main__":
    asyncio.run(main())