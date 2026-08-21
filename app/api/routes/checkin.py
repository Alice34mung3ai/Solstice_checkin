from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.schemas import (
    PrintJob, Attendee,
    ScanRequest, ScanResponse, StatusResponse
)
from app.services.checkin_service import CheckinService
from app.redis_client import redis_client
import uuid

router = APIRouter(prefix="/api/v1", tags=["checkin"])


@router.post(
    "/scan",
    response_model=ScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Print job submitted, waiting for confirmation"},
        409: {"description": "Attendee already checked in"},
        500: {"description": "Internal error"}
    }
)
async def scan_attendee(
    request: ScanRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Process attendee check-in scan

    This endpoint:
    1. Validates attendee
    2. Checks for duplicates (Redis + DB)
    3. Acquires distributed lock
    4. Creates print job
    5. Publishes to vendor queue
    6. Returns PENDING status

    The kiosk UI should show "Processing..." and wait for webhook callback.
    """
    service = CheckinService(db)
    response = await service.process_scan(request)

    if response.status == "DUPLICATE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=response.model_dump()
        )

    return response


@router.get("/scan/{scan_id}/status", response_model=StatusResponse)
async def get_scan_status(
    scan_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get status of a specific scan

    Used for polling fallback if SSE is not available.
    """
    stmt = select(PrintJob).where(PrintJob.scan_id == scan_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found"
        )

    service = CheckinService(db)
    status_data = await service.get_job_status(job.id)

    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )

    return status_data


@router.get("/attendee/{attendee_id}/status")
async def get_attendee_status(
    attendee_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get latest check-in status for attendee
    """
    stmt = select(Attendee).where(Attendee.id == uuid.UUID(attendee_id))
    result = await db.execute(stmt)
    attendee = result.scalar_one_or_none()

    if not attendee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendee not found"
        )

    stmt = select(PrintJob).where(
        PrintJob.attendee_id == uuid.UUID(attendee_id)
    ).order_by(PrintJob.started_at.desc()).limit(1)

    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    redis_state = await redis_client.get_state(attendee_id)

    return {
        "attendee_id": attendee_id,
        "full_name": attendee.full_name,
        "email": attendee.email,
        "badge_printed": attendee.badge_printed,
        "checked_in_at": attendee.checked_in_at,
        "redis_state": redis_state.get("state") if redis_state else None,
        "latest_job": {
            "status": job.status if job else None,
            "print_job_id": str(job.id) if job else None,
            "created_at": job.started_at if job else None,
            "completed_at": job.completed_at if job else None
        } if job else None
    }