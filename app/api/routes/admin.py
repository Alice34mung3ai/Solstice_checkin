from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.database import get_db
from app.schemas import (
    AdminOverrideRequest, AdminOverrideResponse, StatusEnum,
)
from app.models import Attendee, PrintJob, CheckinAudit
from app.redis_client import redis_client
import uuid
from datetime import datetime

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/override", response_model=AdminOverrideResponse)
async def manual_override(
    request: AdminOverrideRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Manual override for failed or stuck check-ins

    Actions:
    - FORCE_CHECK_IN: Force mark attendee as checked in
    - RETRY_PRINT: Reset job for retry
    - CANCEL: Cancel print job
    - RESET_LOCK: Clear Redis lock
    """
    attendee_id = uuid.UUID(request.attendee_id)

    stmt = select(Attendee).where(Attendee.id == attendee_id)
    result = await db.execute(stmt)
    attendee = result.scalar_one_or_none()

    if not attendee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendee not found"
        )

    stmt = select(PrintJob).where(
        PrintJob.attendee_id == attendee_id
    ).order_by(PrintJob.started_at.desc()).limit(1)

    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    previous_status = job.status if job else None

    if request.action == "FORCE_CHECK_IN":
        return await _force_check_in(attendee, job, request, db, previous_status)

    elif request.action == "RETRY_PRINT":
        return await _retry_print(attendee, job, request, db, previous_status)

    elif request.action == "CANCEL":
        return await _cancel_job(attendee, job, request, db, previous_status)

    elif request.action == "RESET_LOCK":
        return await _reset_lock(attendee, job, request, db, previous_status)

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown action: {request.action}"
        )


async def _force_check_in(
    attendee: Attendee,
    job: PrintJob,
    request: AdminOverrideRequest,
    db: AsyncSession,
    previous_status: str | None
) -> AdminOverrideResponse:
    """Force mark attendee as checked in"""

    attendee.badge_printed = True
    attendee.checked_in_at = datetime.utcnow()

    if job:
        job.status = StatusEnum.SUCCESS
        job.completed_at = datetime.utcnow()
        job.vendor_response = {"manual_override": True}

    if job:
        await redis_client.set_job_success(str(attendee.id), str(job.id))
    else:
        await redis_client.set_state(str(attendee.id), StatusEnum.SUCCESS)

    audit = CheckinAudit(
        attendee_id=attendee.id,
        print_job_id=job.id if job else None,
        action="MANUAL_OVERRIDE",
        status=StatusEnum.SUCCESS,
        details={
            "action": request.action,
            "reason": request.reason,
            "previous_status": str(previous_status) if previous_status else None
        },
        operator_id=request.operator_id,
        source="admin"
    )
    db.add(audit)
    await db.commit()

    return AdminOverrideResponse(
        status="SUCCESS",
        override_id=uuid.uuid4(),
        attendee_id=attendee.id,
        previous_status=previous_status or StatusEnum.PENDING,
        new_status=StatusEnum.SUCCESS,
        timestamp=datetime.utcnow(),
        operator_id=request.operator_id
    )


async def _retry_print(
    attendee: Attendee,
    job: PrintJob,
    request: AdminOverrideRequest,
    db: AsyncSession,
    previous_status: str | None
) -> AdminOverrideResponse:
    """Reset job for retry"""

    if not job:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No print job found to retry"
        )

    job.status = StatusEnum.PENDING
    job.error_message = None
    job.error_type = None
    job.attempt_count = 0
    job.completed_at = None
    job.vendor_job_id = None

    await redis_client.delete_state(str(attendee.id))

    audit = CheckinAudit(
        attendee_id=attendee.id,
        print_job_id=job.id,
        action="MANUAL_OVERRIDE",
        status=StatusEnum.PENDING,
        details={
            "action": request.action,
            "reason": request.reason
        },
        operator_id=request.operator_id,
        source="admin"
    )
    db.add(audit)
    await db.commit()

    return AdminOverrideResponse(
        status="RETRY_SCHEDULED",
        override_id=uuid.uuid4(),
        attendee_id=attendee.id,
        previous_status=previous_status,
        new_status=StatusEnum.PENDING,
        timestamp=datetime.utcnow(),
        operator_id=request.operator_id
    )


async def _cancel_job(
    attendee: Attendee,
    job: PrintJob,
    request: AdminOverrideRequest,
    db: AsyncSession,
    previous_status: str | None
) -> AdminOverrideResponse:
    """Cancel print job"""

    if job:
        job.status = StatusEnum.FAILED
        job.error_message = f"Cancelled by operator: {request.reason}"
        job.completed_at = datetime.utcnow()

    await redis_client.delete_state(str(attendee.id))
    await redis_client.release_lock(str(attendee.id), "admin")

    audit = CheckinAudit(
        attendee_id=attendee.id,
        print_job_id=job.id if job else None,
        action="MANUAL_OVERRIDE",
        status=StatusEnum.FAILED,
        details={
            "action": request.action,
            "reason": request.reason
        },
        operator_id=request.operator_id,
        source="admin"
    )
    db.add(audit)
    await db.commit()

    return AdminOverrideResponse(
        status="CANCELLED",
        override_id=uuid.uuid4(),
        attendee_id=attendee.id,
        previous_status=previous_status or StatusEnum.PENDING,
        new_status=StatusEnum.FAILED,
        timestamp=datetime.utcnow(),
        operator_id=request.operator_id
    )


async def _reset_lock(
    attendee: Attendee,
    job: PrintJob,
    request: AdminOverrideRequest,
    db: AsyncSession,
    previous_status: str | None
) -> AdminOverrideResponse:
    """Reset Redis lock"""

    released = await redis_client.release_lock(str(attendee.id), "admin")

    audit = CheckinAudit(
        attendee_id=attendee.id,
        print_job_id=job.id if job else None,
        action="MANUAL_OVERRIDE",
        status="LOCK_RESET",
        details={
            "action": request.action,
            "reason": request.reason,
            "lock_released": released
        },
        operator_id=request.operator_id,
        source="admin"
    )
    db.add(audit)
    await db.commit()

    return AdminOverrideResponse(
        status="LOCK_RESET",
        override_id=uuid.uuid4(),
        attendee_id=attendee.id,
        previous_status=previous_status or StatusEnum.PENDING,
        new_status=previous_status or StatusEnum.PENDING,
        timestamp=datetime.utcnow(),
        operator_id=request.operator_id
    )