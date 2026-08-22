import logging
from datetime import datetime
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import PrintJob, Attendee, StatusEnum
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)

class WebhookService:
    """Handles incoming status notifications from the badge-printing vendor"""
    
    async def process_callback(self, db: AsyncSession, payload) -> bool:
        """Process incoming print job updates from the vendor webhook"""
        try:
            # Look up the matching print job using the vendor's job ID
            stmt = select(PrintJob).where(PrintJob.vendor_job_id == str(payload.job_id))
            result = await db.execute(stmt)
            print_job = result.scalar_one_or_none()
            
            if not print_job:
                logger.error(f"❌ Webhook received for unknown vendor job ID: {payload.job_id}")
                return False
                
            #  job is already done, skip duplication
            if print_job.status in [StatusEnum.SUCCESS, StatusEnum.FAILED]:
                logger.info(f"🔄 Webhook ignored: Job {print_job.id} is already {print_job.status}")
                return True

            # Normalize vendor status to system StatusEnum
            vendor_status = payload.status.upper()
            
            if vendor_status == "SUCCESS":
                print_job.status = StatusEnum.SUCCESS
                print_job.completed_at = datetime.utcnow()
                
                # Fetch and update corresponding attendee status
                attendee_result = await db.execute(select(Attendee).where(Attendee.id == print_job.attendee_id))
                attendee = attendee_result.scalar_one_or_none()
                if attendee:
                    attendee.badge_printed = True
                    attendee.checked_in_at = datetime.utcnow()
                
                msg = "Badge printed and check-in finalized successfully."
                logger.info(f"✅ Print job {print_job.id} succeeded. Attendee {print_job.attendee_id} checked in.")
                
            else:
                print_job.status = StatusEnum.FAILED
                print_job.error_message = payload.error_message or "Vendor reported a print failure."
                print_job.completed_at = datetime.utcnow()
                msg = print_job.error_message
                logger.warning(f"❌ Print job {print_job.id} failed via vendor webhook notification.")

            # Save updates to database
            await db.commit()
            
          
            await notification_service.send_status_update(
                attendee_id=str(print_job.attendee_id),
                print_job_id=str(print_job.id),
                status=print_job.status,
                message=msg
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ Error processing webhook callback: {e}", exc_info=True)
            await db.rollback()
            return False


webhook_service = WebhookService()
webhook_service = WebhookService()

class WebhookServiceFactory:
    """Factory to retrieve the singleton webhook service instance"""
    @staticmethod
    def get_service() -> WebhookService:
        return webhook_service
