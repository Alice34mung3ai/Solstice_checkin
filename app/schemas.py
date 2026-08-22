import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field

# Cross-module references to satisfy database hooks
from app.database import PrintJob, Attendee, WebhookEvent, StatusEnum

class QueueMessage(BaseModel):
    """Message payload published to the print job queue"""
    job_id: uuid.UUID
    attendee_id: uuid.UUID
    scan_id: str
    kiosk_id: str
    badge_data: dict[str, Any]
    webhook_url: str
    idempotency_key: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorType:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DB_ERROR = "DB_ERROR"
    QUEUE_ERROR = "QUEUE_ERROR"
    VENDOR_ERROR = "VENDOR_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class ScanRequest(BaseModel):
    """Incoming scan request from a kiosk"""
    attendee_id: uuid.UUID
    scan_id: str
    kiosk_id: str
    badge_data: Optional[dict[str, Any]] = None


class ScanResponse(BaseModel):
    """Response returned after processing a scan"""
    status: str
    message: str
    attendee_id: uuid.UUID
    print_job_id: Optional[uuid.UUID] = None
    vendor_job_id: Optional[str] = None
    checked_in_at: Optional[datetime] = None
    estimated_wait_time: Optional[int] = None
    error_type: Optional[str] = None
    manual_override_available: bool = False


class StatusResponse(BaseModel):
    """Print job status, used for polling fallback"""
    print_job_id: str
    attendee_id: str
    status: str
    vendor_job_id: Optional[str] = None
    attempt_count: int
    created_at: Optional[datetime] = None
    processing_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class AdminOverrideRequest(BaseModel):
    """Manual override request from an admin"""
    attendee_id: str
    action: str  # FORCE_CHECK_IN, RETRY_PRINT, CANCEL, RESET_LOCK
    reason: Optional[str] = None
    operator_id: Optional[str] = None


class AdminOverrideResponse(BaseModel):
    """Response after a manual override action"""
    status: str
    override_id: uuid.UUID
    attendee_id: uuid.UUID
    previous_status: Optional[str] = None
    new_status: str
    timestamp: datetime
    operator_id: Optional[str] = None


class WebhookPayload(BaseModel):
    """Payload received from the print vendor's webhook callback"""
    attendee_id: uuid.UUID
    job_id: str  # vendor's job id
    status: str  # SUCCESS or FAILED (case-insensitive)
    printed_at: Optional[datetime] = None
    badge_url: Optional[str] = None
    error_message: Optional[str] = None


class WebhookResponse(BaseModel):
    """Response schema returned by the webhook endpoint"""
    status: str
    message: str
    processed_at: datetime = Field(default_factory=datetime.utcnow)
