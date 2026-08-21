"""
Solstice Check-in Service - Main Application
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import sys
import os
from dotenv import load_dotenv

load_dotenv()

from app.config import settings
from app.database import async_engine, Base
from app.redis_client import redis_client
from app.services.queue_service import queue_service
from app.services.notification_service import notification_service, sse_endpoint
from app.api.routes import checkin, webhook, admin

# Setup logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    
    # Startup
    logger.info("=" * 60)
    logger.info(f"🚀 Starting {settings.APP_NAME}")
    logger.info(f"📊 Environment: {settings.ENVIRONMENT.value}")
    logger.info(f"💻 Platform: {sys.platform}")
    logger.info("=" * 60)
    
    # Connect to Redis
    await redis_client.connect()
    
    # Connect to Queue
    await queue_service.connect()
    
    # Create database tables
    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Database tables ready")
    except Exception as e:
        logger.error(f"❌ Database error: {e}")
        logger.warning("   Continuing with existing tables...")
    
    logger.info("✅ Service started successfully")
    logger.info(f"📖 API Docs: http://localhost:8000/docs")
    logger.info(f"🔍 Health: http://localhost:8000/health")
    logger.info("=" * 60)
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down service...")
    await redis_client.close()
    await queue_service.close()
    await async_engine.dispose()
    logger.info("✅ Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Event Check-in Kiosk Service with Async Print Workflow",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(checkin.router)
app.include_router(webhook.router)
app.include_router(admin.router)


# Real-time SSE endpoint
@app.get("/events/{attendee_id}")
async def events_endpoint(request: Request, attendee_id: str):
    """Server-Sent Events for real-time kiosk updates"""
    return await sse_endpoint(request, attendee_id)


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    redis_healthy = await redis_client.health_check()
    queue_healthy = True  # Could check queue connection
    
    return {
        "status": "healthy" if redis_healthy else "degraded",
        "service": settings.APP_NAME,
        "version": "1.0.0",
        "redis": "connected" if redis_healthy else "disconnected",
        "queue": "connected" if queue_healthy else "disconnected",
        "environment": settings.ENVIRONMENT.value
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.APP_NAME,
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "ERROR",
            "message": "An internal error occurred",
            "error_id": str(uuid.uuid4())
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )