import json
import time
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging
import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client with distributed lock and state management"""
    
    def __init__(self):
        self.client = None
        self.lock_ttl = settings.REDIS_LOCK_TTL
        self.state_ttl = settings.REDIS_STATE_TTL
    
    async def connect(self):
        """Establish Redis connection"""
        try:
            self.client = await aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                max_connections=50
            )
            await self.client.ping()
            logger.info("✅ Connected to Redis")
            return True
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            return False
    
    async def acquire_lock(
        self,
        attendee_id: str,
        owner_id: str,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Acquire distributed lock for attendee
        
        Args:
            attendee_id: The attendee ID to lock
            owner_id: Owner identifier (kiosk_id or job_id)
            ttl: Lock TTL in seconds (default: 30)
        
        Returns:
            True if lock acquired, False if already locked
        """
        if not self.client:
            logger.warning("Redis not connected, lock acquisition skipped")
            return True
        
        lock_key = f"lock:checkin:{attendee_id}"
        lock_value = f"{owner_id}:{time.time()}"
        ttl = ttl or self.lock_ttl
        
        try:
            # Atomic SET NX with TTL
            acquired = await self.client.set(
                lock_key,
                lock_value,
                nx=True,  # Only set if not exists
                ex=ttl
            )
            
            if acquired:
                logger.debug(f"🔒 Lock acquired for {attendee_id} by {owner_id}")
                return True
            else:
                logger.debug(f"🔓 Lock already held for {attendee_id}")
                return False
                
        except Exception as e:
            logger.error(f"Lock acquisition error: {e}")
            return False
    
    async def release_lock(self, attendee_id: str, owner_id: str) -> bool:
        """
        Release lock if owned by owner_id
        
        Returns:
            True if lock was released, False if not owned
        """
        if not self.client:
            return True
        
        lock_key = f"lock:checkin:{attendee_id}"
        
        try:
            current = await self.client.get(lock_key)
            
            if current and current.startswith(owner_id):
                await self.client.delete(lock_key)
                logger.debug(f"🔓 Lock released for {attendee_id} by {owner_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Lock release error: {e}")
            return False
    
    async def get_lock_info(self, attendee_id: str) -> Optional[Dict[str, Any]]:
        """Get lock information for an attendee"""
        if not self.client:
            return None
        
        lock_key = f"lock:checkin:{attendee_id}"
        
        try:
            value = await self.client.get(lock_key)
            if value:
                parts = value.split(":")
                return {
                    "owner_id": parts[0],
                    "acquired_at": float(parts[1]) if len(parts) > 1 else None,
                    "ttl": await self.client.ttl(lock_key)
                }
            return None
            
        except Exception as e:
            logger.error(f"Get lock info error: {e}")
            return None
    
    async def set_state(
        self,
        attendee_id: str,
        state: str,
        metadata: Optional[Dict[str, Any]] = None,
        ttl: Optional[int] = None
    ):
        """Store check-in state in Redis with TTL"""
        if not self.client:
            return
        
        state_key = f"state:checkin:{attendee_id}"
        ttl = ttl or self.state_ttl
        
        data = {
            "state": state,
            "updated_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        
        try:
            await self.client.setex(
                state_key,
                ttl,
                json.dumps(data)
            )
            logger.debug(f"📝 State set for {attendee_id}: {state}")
        except Exception as e:
            logger.error(f"State set error: {e}")
    
    async def get_state(self, attendee_id: str) -> Optional[Dict[str, Any]]:
        """Get check-in state from Redis"""
        if not self.client:
            return None
        
        state_key = f"state:checkin:{attendee_id}"
        
        try:
            data = await self.client.get(state_key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"State get error: {e}")
            return None
    
    async def delete_state(self, attendee_id: str):
        """Delete check-in state"""
        if not self.client:
            return
        
        state_key = f"state:checkin:{attendee_id}"
        
        try:
            await self.client.delete(state_key)
        except Exception as e:
            logger.error(f"State delete error: {e}")
    
    async def set_job_pending(
        self,
        attendee_id: str,
        print_job_id: str,
        kiosk_id: str
    ):
        """Convenience method to set PENDING state with job info"""
        await self.set_state(
            attendee_id,
            "PENDING",
            metadata={
                "print_job_id": print_job_id,
                "kiosk_id": kiosk_id,
                "started_at": datetime.utcnow().isoformat()
            }
        )
    
    async def set_job_success(self, attendee_id: str, print_job_id: str):
        """Convenience method to set SUCCESS state"""
        await self.set_state(
            attendee_id,
            "SUCCESS",
            metadata={
                "print_job_id": print_job_id,
                "completed_at": datetime.utcnow().isoformat()
            }
        )
    
    async def set_job_failed(self, attendee_id: str, print_job_id: str, error: str):
        """Convenience method to set FAILED state"""
        await self.set_state(
            attendee_id,
            "FAILED",
            metadata={
                "print_job_id": print_job_id,
                "error": error,
                "failed_at": datetime.utcnow().isoformat()
            }
        )
    
    async def health_check(self) -> bool:
        """Check Redis connectivity"""
        if not self.client:
            return False
        
        try:
            await self.client.ping()
            return True
        except Exception:
            return False
    
    async def close(self):
        """Close Redis connection"""
        if self.client:
            await self.client.close()
            logger.info("Redis connection closed")


# Singleton instance
redis_client = RedisClient()