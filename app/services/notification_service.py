import logging
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from fastapi import Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


class NotificationService:
    """Real-time notification service"""
    
    def __init__(self):
        self.subscribers: Dict[str, List] = {}
    
    async def send_status_update(
        self,
        attendee_id: str,
        print_job_id: str,
        status: str,
        message: str
    ):
        """Send status update"""
        logger.debug(f"📨 Notification for {attendee_id}: {status}")
       

notification_service = NotificationService()


async def sse_endpoint(request: Request, attendee_id: str):
    """Server-Sent Events endpoint generator used by main.py"""
    async def event_generator():
        try:
            logger.info(f"🔌 Client connected to SSE for attendee: {attendee_id}")
            
            while True:
                if await request.is_disconnected():
                    break
                
                # Using single quotes inside to avoid escaping backslash issues
                timestamp = datetime.utcnow().isoformat()
                yield f"data: {{'status': 'PING', 'time': '{timestamp}'}}\n\n"
                await asyncio.sleep(15)
                
        except asyncio.CancelledError:
            logger.info(f"🔌 Client disconnected from SSE for attendee: {attendee_id}")

    return StreamingResponse(event_generator(), media_type="text/event-stream")
