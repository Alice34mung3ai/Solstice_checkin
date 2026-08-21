"""
Services package
"""

# Temporarily comment out webhook_service import
# from app.services.webhook_service import WebhookService, WebhookServiceFactory
from app.services.checkin_service import CheckinService
from app.services.queue_service import queue_service
from app.services.notification_service import notification_service

# Create placeholder classes if needed
class WebhookService:
    def __init__(self, db): pass
    async def process_webhook(self, payload, headers): 
        return {"status": "success", "message": "Webhook processed"}

class WebhookServiceFactory:
    @staticmethod
    def create(db):
        return WebhookService(db)

__all__ = [
    'WebhookService',
    'WebhookServiceFactory',
    'CheckinService',
    'queue_service',
    'notification_service'
]