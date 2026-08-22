import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Attendee, PrintJob, CheckinAudit
from app.schemas import ScanRequest, ScanResponse, QueueMessage
from app.database import StatusEnum
from app.redis_client import redis_client
from app.services.queue_service import queue_service
from app.config import settings

logger = logging.getLogger(__name__)


class CheckinService:
    """Core check-in orchestration"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_scan(self, request: ScanRequest) -> ScanResponse:
        """Process attendee scan"""

        attendee_id = str(request.attendee_id)

        # Get attendee
        attendee = await self._get_attendee(attendee_id)
        if not attendee:
            return ScanResponse(
                status=StatusEnum.FAILED,
                message="Attendee not found",
                attendee_id=request.attendee_id
            )

        # Check if already checked in
        if attendee.badge_printed:
            return ScanResponse(
                status=StatusEnum.DUPLICATE,
                message="Attendee already checked in",
                attendee_id=request.attendee_id,
                checked_in_at=attendee.checked_in_at
            )

        # Check Redis state
        current_state = await redis_client.get_state(attendee_id)
        if current_state:
            state = current_state.get("state")
            if state == StatusEnum.SUCCESS:
                return ScanResponse(
                    status=StatusEnum.DUPLICATE,
                    message="Attendee already checked in",
                    attendee_id=request.attendee_id
                )
            elif state == StatusEnum.PENDING:
                return ScanResponse(
                    status=StatusEnum.PENDING,
                    message="Print job in progress, please wait",
                    attendee_id=request.attendee_id,
                    estimated_wait_time=30
                )

        # Acquire lock
        lock_acquired = await redis_client.acquire_lock(
            attendee_id,
            request.kiosk_id,
            ttl=settings.REDIS_LOCK_TTL
        )

        if not lock_acquired:
            return ScanResponse(
                status=StatusEnum.LOCKED,
                message="Another kiosk is processing this attendee",
                attendee_id=request.attendee_id
            )

        try:
            # Create print job
            print_job = await self._create_print_job(request)

            # Set Redis state
            await redis_client.set_job_pending(
                attendee_id,
                str(print_job.id),
                request.kiosk_id
            )

            # Log scan
            await self._log_audit(
                attendee_id,
                print_job.id,
                "SCAN",
                details={"kiosk_id": request.kiosk_id, "scan_id": request.scan_id}
            )

            queue_message = QueueMessage(
                job_id=print_job.id,
                attendee_id=request.attendee_id,
                scan_id=request.scan_id,
                kiosk_id=request.kiosk_id,
                badge_data=request.badge_data or {},
                webhook_url=f"{settings.BASE_URL}{settings.WEBHOOK_PATH}",
                idempotency_key=print_job.idempotency_key,
            )

            result = await queue_service.publish_print_job(queue_message)

            if not result.submitted:
                
                print_job.status = StatusEnum.FAILED
                print_job.error_type = result.error_type
                print_job.error_message = result.error_message
                print_job.completed_at = datetime.utcnow()

                await redis_client.delete_state(attendee_id)
                await self.db.commit()

                logger.error(
                    f"❌ Check-in FAILED for {attendee_id}: {result.error_message}"
                )

                return ScanResponse(
                    status=StatusEnum.FAILED,
                    message=result.error_message or "Vendor submission failed",
                    attendee_id=request.attendee_id,
                    print_job_id=print_job.id,
                    error_type=result.error_type,
                    manual_override_available=True
                )

            
            print_job.vendor_job_id = result.vendor_job_id
            print_job.processing_at = datetime.utcnow()

            await self.db.commit()

            logger.info(
                f"📨 Check-in PENDING for {attendee_id} "
                f"(vendor_job_id={result.vendor_job_id}), awaiting webhook confirmation"
            )

            return ScanResponse(
                status=StatusEnum.PENDING,
                message="Print job submitted, awaiting vendor confirmation",
                attendee_id=request.attendee_id,
                print_job_id=print_job.id,
                vendor_job_id=result.vendor_job_id,
                estimated_wait_time=30
            )

        except Exception as e:
            logger.error(f"❌ Check-in error: {e}", exc_info=True)
            await redis_client.delete_state(attendee_id)

            return ScanResponse(
                status=StatusEnum.FAILED,
                message=f"Error: {str(e)}",
                attendee_id=request.attendee_id,
                manual_override_available=True
            )

        finally:
            await redis_client.release_lock(attendee_id, request.kiosk_id)

    async def _get_attendee(self, attendee_id: str) -> Optional[Attendee]:
        """Get attendee by ID"""
        stmt = select(Attendee).where(Attendee.id == uuid.UUID(attendee_id))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _create_print_job(self, request: ScanRequest) -> PrintJob:
        """Create print job"""
        print_job = PrintJob(
            id=uuid.uuid4(),
            attendee_id=request.attendee_id,
            idempotency_key=f"{request.attendee_id}:{request.scan_id}",
            kiosk_id=request.kiosk_id,
            scan_id=request.scan_id,
            status=StatusEnum.PENDING,
            started_at=datetime.utcnow()
        )

        self.db.add(print_job)
        await self.db.commit()
        await self.db.refresh(print_job)

        return print_job

    async def _log_audit(
        self,
        attendee_id: str,
        print_job_id: uuid.UUID,
        action: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log audit entry"""
        audit = CheckinAudit(
            attendee_id=uuid.UUID(attendee_id),
            print_job_id=print_job_id,
            action=action,
            details=details,
            source="kiosk"
        )
        self.db.add(audit)
        await self.db.commit()