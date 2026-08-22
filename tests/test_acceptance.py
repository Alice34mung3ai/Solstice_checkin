import os
from dotenv import load_dotenv

load_dotenv()

# Print environment
print(f"DATABASE_URL: {os.getenv('DATABASE_URL')}")
print(f"REDIS_URL: {os.getenv('REDIS_URL')}")

# Test PostgreSQL
try:
    import asyncpg
    import asyncio
    
    async def test_postgres():
        try:
            conn = await asyncpg.connect(
                host='localhost',
                port=5432,
                user='postgres',
                password='postgres',
                database='solstice'
            )
            result = await conn.fetch('SELECT version()')
            print(f"✅ PostgreSQL connected: {result[0]['version'][:50]}...")
            await conn.close()
            return True
        except Exception as e:
            print(f"❌ PostgreSQL error: {e}")
            print("   Make sure PostgreSQL is running")
            print("   Create database: createdb solstice")
            return False
    
    asyncio.run(test_postgres())
    
except ImportError:
    print("⚠️  asyncpg not installed, skipping PostgreSQL test")