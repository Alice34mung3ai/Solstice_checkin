"""
Webhook service for processing vendor callbacks
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
import uuid
import hmac
import hashlib
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Attendee, PrintJob, WebhookEvent, CheckinAudit
from app.schemas import WebhookPayload, StatusEnum
from app.redis_client import redis_client
from app.config import settings

logger = logging.getLogger(__name__)


class WebhookService:
    """Service for processing webhook callbacks"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def process_webhook(
        self,
        payload: WebhookPayload,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Process webhook callback from vendor"""
        
        attendee_id = str(payload.attendee_id)
        job_id = payload.job_id
        
        logger.info(f"📨 Webhook received for {attendee_id}, job: {job_id}")
        
        # Check if already processed
        existing = await self._check_existing(job_id, attendee_id)
        if existing:
            logger.info(f"⏭️ Webhook already processed for {attendee_id}")
            return {"already_processed": True, "status": existing.status}
        
        # Get print job
        print_job = await self._get_print_job(job_id)
        if not print_job:
            logger.error(f"❌ Print job not found: {job_id}")
            return {"status": "ERROR", "message": "Print job not found"}
        
        # Process based on status
        if payload.status.upper() == "SUCCESS":
            return await self._handle_success(attendee_id, print_job, payload)
        else:
            return await self._handle_failure(attendee_id, print_job, payload)
    
    async def _check_existing(self, job_id: str, attendee_id: str) -> Optional[WebhookEvent]:
        """Check if webhook already processed"""
        stmt = select(WebhookEvent).where(
            WebhookEvent.attendee_id == uuid.UUID(attendee_id),
            WebhookEvent.payload["job_id"].astext == job_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_print_job(self, job_id: str) -> Optional[PrintJob]:
        """Get print job by vendor job ID"""
        stmt = select(PrintJob).where(PrintJob.vendor_job_id == job_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _handle_success(
        self,
        attendee_id: str,
        print_job: PrintJob,
        payload: WebhookPayload
    ) -> Dict[str, Any]:
        """Handle successful print"""
        # Update print job
        print_job.status = StatusEnum.SUCCESS
        print_job.completed_at = payload.printed_at or datetime.utcnow()
        print_job.vendor_response = payload.model_dump()
        
        # Update attendee
        stmt = select(Attendee).where(Attendee.id == uuid.UUID(attendee_id))
        result = await self.db.execute(stmt)
        attendee = result.scalar_one()
        
        if attendee:
            attendee.badge_printed = True
            attendee.checked_in_at = print_job.completed_at
        
        # Update Redis
        await redis_client.set_job_success(attendee_id, str(print_job.id))
        
        # Log audit
        audit = CheckinAudit(
            attendee_id=uuid.UUID(attendee_id),
            print_job_id=print_job.id,
            action="PRINT_SUCCESS",
            status=StatusEnum.SUCCESS,
            details={"vendor_job_id": payload.job_id},
            source="webhook"
        )
        self.db.add(audit)
        
        # Log webhook event
        event = WebhookEvent(
            attendee_id=uuid.UUID(attendee_id),
            print_job_id=print_job.id,
            event_type="PRINT_SUCCESS",
            status=StatusEnum.SUCCESS,
            payload=payload.model_dump()
        )
        self.db.add(event)
        
        await self.db.commit()
        
        logger.info(f"✅ Print SUCCESS for {attendee_id}")
        
        return {
            "status": StatusEnum.SUCCESS,
            "message": "Badge printed successfully",
            "attendee_id": attendee_id,
            "print_job_id": str(print_job.id)
        }
    
    async def _handle_failure(
        self,
        attendee_id: str,
        print_job: PrintJob,
        payload: WebhookPayload
    ) -> Dict[str, Any]:
        """Handle failed print"""
        # Update print job
        print_job.status = StatusEnum.FAILED
        print_job.error_message = payload.error_message or "Print failed"
        
        # Update Redis
        await redis_client.set_job_failed(
            attendee_id,
            str(print_job.id),
            print_job.error_message
        )
        
        # Log audit
        audit = CheckinAudit(
            attendee_id=uuid.UUID(attendee_id),
            print_job_id=print_job.id,
            action="PRINT_FAILED",
            status=StatusEnum.FAILED,
            details={"vendor_job_id": payload.job_id, "error": payload.error_message},
            source="webhook"
        )
        self.db.add(audit)
        
        # Log webhook event
        event = WebhookEvent(
            attendee_id=uuid.UUID(attendee_id),
            print_job_id=print_job.id,
            event_type="PRINT_FAILED",
            status=StatusEnum.FAILED,
            payload=payload.model_dump()
        )
        self.db.add(event)
        
        await self.db.commit()
        
        logger.error(f"❌ Print FAILED for {attendee_id}: {payload.error_message}")
        
        return {
            "status": StatusEnum.FAILED,
            "message": payload.error_message or "Print failed",
            "attendee_id": attendee_id,
            "print_job_id": str(print_job.id),
            "manual_override_available": True
        }


class WebhookServiceFactory:
    """Factory for creating webhook services"""
    
    @staticmethod
    def create(db: AsyncSession) -> WebhookService:
        return WebhookService(db)