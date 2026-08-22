import asyncio
import logging
from typing import Optional

import httpx
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)


class PublishResult(BaseModel):
    submitted: bool
    vendor_job_id: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None


class QueueService:
    """Message queue service for print requests"""

    def __init__(self):
        self.queue_type = settings.QUEUE_TYPE
        self.queue_name = settings.QUEUE_NAME

    async def connect(self):
        """Connect to queue"""
        logger.info(f"📨 Using {self.queue_type} queue")
        return True

    async def publish_print_job(self, message) -> PublishResult:
       
        if not settings.VENDOR_API_URL:
            logger.error("❌ VENDOR_API_URL not configured")
            return PublishResult(
                submitted=False,
                error_type="CONFIG_ERROR",
                error_message="VENDOR_API_URL is not set in .env",
            )

        payload = {
            "job_id": str(message.job_id),
            "attendee_id": str(message.attendee_id),
            "scan_id": message.scan_id,
            "kiosk_id": message.kiosk_id,
            "badge_data": message.badge_data,
            "webhook_url": message.webhook_url,
        }
        headers = {"Idempotency-Key": message.idempotency_key}
        if settings.VENDOR_API_KEY:
            headers["Authorization"] = f"Bearer {settings.VENDOR_API_KEY}"

        timeout = httpx.Timeout(
            connect=settings.VENDOR_CONNECTION_TIMEOUT,
            read=settings.VENDOR_READ_TIMEOUT,
            write=settings.VENDOR_READ_TIMEOUT,
            pool=settings.VENDOR_TOTAL_TIMEOUT,
        )

        last_error: Optional[Exception] = None
        last_status: Optional[int] = None

        for attempt in range(1, settings.VENDOR_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        f"{settings.VENDOR_API_URL}/print-jobs",
                        json=payload,
                        headers=headers,
                    )

                if response.status_code in (200, 201, 202):
                    data = response.json()
                    logger.info(
                        f"📨 Vendor accepted job {message.job_id} "
                        f"(vendor_job_id={data.get('vendor_job_id')}, attempt {attempt})"
                    )
                    return PublishResult(
                        submitted=True,
                        vendor_job_id=data.get("vendor_job_id"),
                    )

                last_status = response.status_code

                # Permanent (4xx other than 429) - don't retry
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    logger.error(
                        f"❌ Vendor rejected job {message.job_id} permanently "
                        f"(status {response.status_code}): {response.text}"
                    )
                    return PublishResult(
                        submitted=False,
                        error_type="VENDOR_ERROR",
                        error_message=f"Vendor returned {response.status_code}: {response.text}",
                    )

                # Transient (5xx or 429) - fall through and retry
                logger.warning(
                    f"⚠️  Vendor transient error for job {message.job_id} "
                    f"(status {response.status_code}, attempt {attempt}/{settings.VENDOR_MAX_RETRIES})"
                )

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
                logger.warning(
                    f"⚠️  Vendor connection issue for job {message.job_id} "
                    f"(attempt {attempt}/{settings.VENDOR_MAX_RETRIES}): {e}"
                )

            if attempt < settings.VENDOR_MAX_RETRIES:
                backoff = settings.VENDOR_RETRY_BACKOFF_BASE * attempt
                await asyncio.sleep(backoff)

        error_message = str(last_error) if last_error else f"HTTP {last_status}"
        logger.error(
            f"❌ Vendor submission failed after {settings.VENDOR_MAX_RETRIES} attempts: {error_message}"
        )
        return PublishResult(
            submitted=False,
            error_type="TIMEOUT_ERROR" if last_error else "VENDOR_ERROR",
            error_message=f"Vendor unreachable after {settings.VENDOR_MAX_RETRIES} attempts: {error_message}",
        )

    async def close(self):
        pass


queue_service = QueueService()