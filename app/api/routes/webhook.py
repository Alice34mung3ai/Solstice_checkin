import logging
from fastapi import APIRouter, Depends, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas import WebhookPayload, WebhookResponse
from app.services.webhook_service import WebhookServiceFactory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/print-callback", response_model=WebhookResponse)
async def print_callback(
    payload: WebhookPayload,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Vendor webhook callback endpoint
    Receives print completion/failure callbacks from vendor.
    Responds immediately with 200 OK, processes in background.
    """
    logger.info(f"📨 Webhook received: {payload.job_id} for {payload.attendee_id}")

    # Process in background to respond quickly
    background_tasks.add_task(
        process_webhook_background,
        payload,
        db
    )

    return WebhookResponse(
        status="received",
        message="Webhook received and queued for processing"
    )


async def process_webhook_background(
    payload: WebhookPayload,
    db: AsyncSession
):
    """Background task to process webhook"""
    try:
        service = WebhookServiceFactory.get_service()
        success = await service.process_callback(db, payload)
        logger.info(f"✅ Webhook processed: {payload.job_id} - success={success}")
    except Exception as e:
        logger.error(f"❌ Webhook processing error: {e}", exc_info=True)
    finally:
        await db.close()