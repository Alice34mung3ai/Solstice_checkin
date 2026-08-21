import os
import sys
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()

    print("=" * 60)
    print("🚀 Starting Solstice Check-in Service")
    print("=" * 60)
    print(f"📁 Working Directory: {os.getcwd()}")
    print(f"🐍 Python: {sys.executable}")

    # Check database
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("⚠️  DATABASE_URL not found, using SQLite")
        os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./solstice.db"

    print(f"📊 Database: {os.getenv('DATABASE_URL')}")

    # Check Redis
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        print(f"📦 Redis: {redis_url}")
    else:
        print("⚠️  REDIS_URL not found, using default")
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"

    print("✅ Starting uvicorn...")
    print("📖 API Docs: http://localhost:8000/docs")
    print("🔍 Health: http://localhost:8000/health")
    print("=" * 60)

    sys.path.insert(0, os.getcwd())

    try:
        import uvicorn
    except ImportError as e:
        print(f"❌ Failed to import uvicorn: {e}")
        print("   Did you activate the venv / install requirements.txt?")
        sys.exit(1)

    try:
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=8000,
            reload=False,
            workers=1,
            log_level="info",
        )
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()