"""
Application configuration with environment variables
"""

from pydantic_settings import BaseSettings
from typing import Optional
from enum import Enum


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class QueueType(str, Enum):
    RABBITMQ = "rabbitmq"
    SQS = "sqs"
    MOCK = "mock"


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Solstice Check-in Service"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    DEBUG: bool = True
    SECRET_KEY: str
    
    # Database
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_LOCK_TTL: int = 30
    REDIS_STATE_TTL: int = 600
    
    # Message Queue
    QUEUE_TYPE: QueueType = QueueType.MOCK
    QUEUE_URL: Optional[str] = None
    QUEUE_NAME: str = "print_jobs"
    
    # AWS SQS (if using)
    AWS_REGION: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    SQS_QUEUE_URL: Optional[str] = None
    
    # Webhook
    BASE_URL: str = "http://localhost:8000"
    WEBHOOK_PATH: str = "/webhook/print-callback"
    
    # Vendor API (fallback)
    VENDOR_API_URL: Optional[str] = None
    VENDOR_API_KEY: Optional[str] = None
    VENDOR_CONNECTION_TIMEOUT: float = 5.0
    VENDOR_READ_TIMEOUT: float = 25.0
    VENDOR_TOTAL_TIMEOUT: float = 30.0
    
    # Retry
    VENDOR_MAX_RETRIES: int = 3
    VENDOR_RETRY_BACKOFF_BASE: float = 1.0
    
    # Circuit Breaker
    CIRCUIT_FAILURE_THRESHOLD: int = 5
    CIRCUIT_RECOVERY_TIMEOUT: int = 60
    
    # Kiosk
    KIOSK_REQUEST_TIMEOUT: int = 35
    KIOSK_POLLING_INTERVAL: int = 2
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "text"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()