"""
Database connection and models - Complete Version
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ DATABASE_URL not found in .env file")
    print("   Please create .env with:")
    print("   DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/solstice")
    sys.exit(1)

print(f"📊 Database: {DATABASE_URL}")

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, JSON, ForeignKey, Float, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID
import uuid
from datetime import datetime

# Async engine
async_engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True
)

AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

# Sync engine for scripts (optional)
try:
    from sqlalchemy import create_engine
    SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")
    sync_engine = create_engine(SYNC_DATABASE_URL, echo=False)
    SyncSessionLocal = sessionmaker(sync_engine, autocommit=False, autoflush=False)
except:
    sync_engine = None
    SyncSessionLocal = None

Base = declarative_base()


# ============ STATUS ENUM ============
class StatusEnum:
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"
    LOCKED = "LOCKED"


# ============ MODELS ============

class Attendee(Base):
    __tablename__ = "attendees"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)
    role = Column(String(100), nullable=True)
    badge_printed = Column(Boolean, default=False)
    checked_in_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_attendees_email", "email"),
         {"extend_existing": True} 
    )


class PrintJob(Base):
    __tablename__ = "print_jobs"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attendee_id = Column(PGUUID(as_uuid=True), ForeignKey("attendees.id"), nullable=False)
    idempotency_key = Column(String(255), unique=True, nullable=False)
    kiosk_id = Column(String(50), nullable=False)
    scan_id = Column(String(100), unique=True, nullable=False)
    
    status = Column(String(20), default=StatusEnum.PENDING, nullable=False)
    vendor_job_id = Column(String(255), nullable=True)
    vendor_status_code = Column(Integer, nullable=True)
    vendor_response = Column(JSON, nullable=True)
    error_type = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    
    attempt_count = Column(Integer, default=0)
    locked_by = Column(String(50), nullable=True)
    locked_at = Column(DateTime, nullable=True)
    
    started_at = Column(DateTime, default=datetime.utcnow)
    processing_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    vendor_latency_ms = Column(Float, nullable=True)
    total_duration_ms = Column(Float, nullable=True)
    
    __table_args__ = (
        Index("idx_print_jobs_attendee", "attendee_id"),
        Index("idx_print_jobs_status", "status"),
        Index("idx_print_jobs_scan", "scan_id"),
        Index("idx_print_jobs_vendor", "vendor_job_id"),
        {"extend_existing": True}
    )


class CheckinAudit(Base):
    __tablename__ = "checkin_audit"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attendee_id = Column(PGUUID(as_uuid=True), ForeignKey("attendees.id"), nullable=False)
    print_job_id = Column(PGUUID(as_uuid=True), ForeignKey("print_jobs.id"), nullable=True)
    
    action = Column(String(50), nullable=False)
    status = Column(String(20), nullable=True)
    details = Column(JSON, nullable=True)
    operator_id = Column(String(50), nullable=True)
    source = Column(String(50), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_checkin_audit_attendee", "attendee_id"),
        Index("idx_checkin_audit_created", "created_at"),
        {"extend_existing": True}
    )


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attendee_id = Column(PGUUID(as_uuid=True), ForeignKey("attendees.id"), nullable=False)
    print_job_id = Column(PGUUID(as_uuid=True), ForeignKey("print_jobs.id"), nullable=True)
    
    event_type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=True)
    payload = Column(JSON, nullable=False)
    headers = Column(JSON, nullable=True)
    signature_valid = Column(Boolean, default=False)
    
    received_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    
    __table_args__ = (
        Index("idx_webhook_events_attendee", "attendee_id"),
        Index("idx_webhook_events_received", "received_at"),
        {"extend_existing": True}
    )


# ============ DATABASE FUNCTIONS ============

async def get_db():
    """Dependency for FastAPI routes"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def create_tables():
    """Create all tables if they don't exist"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Database tables created/verified")


def create_tables_sync():
    """Synchronous function to create all tables (used by startup scripts)"""
    if sync_engine:
        Base.metadata.create_all(bind=sync_engine)
        print("✅ Database tables created/verified (Sync)")
    else:
        print("❌ Cannot create tables: sync_engine is not initialized")


def get_sync_db():
    """Context manager / Generator for synchronous database sessions"""
    if not SyncSessionLocal:
        raise RuntimeError("SyncSessionLocal is not initialized. Check your database connection string.")
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============ EXPORTS ============

__all__ = [
    # Engine
    'async_engine',
    'AsyncSessionLocal',
    'sync_engine',
    'SyncSessionLocal',
    'Base',
    
    # Models
    'Attendee',
    'PrintJob',
    'CheckinAudit',
    'WebhookEvent',
    
    # Status
    'StatusEnum',
    
    # Functions
    'get_db',
    'create_tables',
    'create_tables_sync',
    'get_sync_db',
]
