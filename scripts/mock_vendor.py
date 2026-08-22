import asyncio
import logging
import os
import uuid
from datetime import datetime

import httpx
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s - mock_vendor - %(levelname)s - %(message)s")
logger = logging.getLogger("mock_vendor")

app = FastAPI(title="Mock Badge Printer Vendor")


async def send_webhook_callback(webhook_url: str, attendee_id: str, vendor_job_id: str, status: str, delay: float):
    """Simulate the printer taking a moment, then confirm the result."""
    await asyncio.sleep(delay)
    payload = {
        "attendee_id": attendee_id,
        "job_id": vendor_job_id,
        "status": status,
        "printed_at": datetime.utcnow().isoformat() if status == "SUCCESS" else None,
        "badge_url": f"http://mock-vendor.local/badges/{vendor_job_id}.pdf" if status == "SUCCESS" else None,
        "error_message": None if status == "SUCCESS" else "Simulated printer failure",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=payload)
        logger.info(f"📨 Callback sent for {vendor_job_id} -> {status} (webhook responded {resp.status_code})")
    except Exception as e:
        logger.error(f"❌ Failed to deliver callback for {vendor_job_id}: {e}")


@app.post("/print-jobs")
async def create_print_job(
    request: Request,
    x_mock_scenario: str = Header(default="success", alias="X-Mock-Scenario"),
):
    body = await request.json()
    job_id = body.get("job_id")
    attendee_id = body.get("attendee_id")
    webhook_url = body.get("webhook_url")
    vendor_job_id = f"vendor-{uuid.uuid4().hex[:8]}"

    logger.info(f"📥 Received job {job_id} for attendee {attendee_id} (scenario={x_mock_scenario})")

    if x_mock_scenario == "error_4xx":
        return JSONResponse(status_code=422, content={"error": {"code": "INVALID_TEMPLATE", "retryable": False}})

    if x_mock_scenario == "error_5xx":
        return JSONResponse(status_code=503, content={"error": {"code": "PRINTER_JAM", "retryable": True}})

    if x_mock_scenario == "timeout":
        # Never respond - the caller's own timeout should fire
        await asyncio.sleep(9999)
        return

    # success or delayed: accept immediately, confirm via webhook shortly after
    delay = 4.0 if x_mock_scenario == "delayed" else 1.5
    if webhook_url:
        asyncio.create_task(
            send_webhook_callback(webhook_url, attendee_id, vendor_job_id, "SUCCESS", delay)
        )
    else:
        logger.warning(f"⚠️  No webhook_url provided for job {job_id}, skipping callback")

    return JSONResponse(
        status_code=202,
        content={"vendor_job_id": vendor_job_id, "accepted": True},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("VENDOR_MOCK_PORT", "9000"))
    logger.info(f"🖨️  Mock vendor starting on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")