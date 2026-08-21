"""
Quick test to verify system is working
Run: python quick_test.py
"""

import asyncio
import httpx
import uuid

BASE_URL = "http://localhost:8000"
ATTENDEE_ID = "00000000-0000-0000-0000-000000000001"

async def test_checkin():
    """Test single check-in"""
    async with httpx.AsyncClient() as client:
        # Health check
        health = await client.get(f"{BASE_URL}/health")
        print(f"Health: {health.json()}")
        
        # Check-in
        response = await client.post(
            f"{BASE_URL}/api/v1/scan",
            json={
                "attendee_id": ATTENDEE_ID,
                "kiosk_id": "test-kiosk",
                "scan_id": f"scan-{uuid.uuid4()}",
                "badge_data": {
                    "name": "Test User",
                    "company": "TestCo"
                }
            }
        )
        
        print(f"Check-in response: {response.status_code}")
        print(response.json())

async def test_duplicate():
    """Test duplicate scan"""
    async with httpx.AsyncClient() as client:
        # Same attendee again
        response = await client.post(
            f"{BASE_URL}/api/v1/scan",
            json={
                "attendee_id": ATTENDEE_ID,
                "kiosk_id": "test-kiosk-2",
                "scan_id": f"scan-{uuid.uuid4()}",
                "badge_data": {
                    "name": "Test User",
                    "company": "TestCo"
                }
            }
        )
        
        print(f"Duplicate response: {response.status_code}")
        print(response.json())

if __name__ == "__main__":
    print("Testing Solstice Check-in Service...")
    asyncio.run(test_checkin())
    asyncio.run(test_duplicate())