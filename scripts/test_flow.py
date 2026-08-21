"""
Complete flow test for the async check-in system
Run: python scripts/test_flow.py
"""

import asyncio
import httpx
import uuid
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

# Test attendee IDs (from seed data)
TEST_ATTENDEES = {
    "alice": "11111111-1111-1111-1111-111111111111",
    "bob": "22222222-2222-2222-2222-222222222222",
    "carol": "33333333-3333-3333-3333-333333333333"
}


async def test_checkin_flow():
    """Test complete check-in flow with async workflow"""
    
    print("=" * 60)
    print("🧪 Testing Async Check-in Flow")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        
        # Test 1: Alice - Normal check-in
        print("\n1️⃣ Testing Alice - Normal Check-in")
        scan_id = f"test-alice-{uuid.uuid4()}"
        
        response = await client.post(
            f"{BASE_URL}/api/v1/scan",
            json={
                "attendee_id": TEST_ATTENDEES["alice"],
                "kiosk_id": "kiosk-01",
                "scan_id": scan_id,
                "badge_data": {
                    "name": "Alice Johnson",
                    "company": "TechCorp Inc.",
                    "role": "Speaker"
                }
            }
        )
        
        print(f"   Status: {response.status_code}")
        data = response.json()
        print(f"   Response: {json.dumps(data, indent=2)}")
        
        if data["status"] == "PENDING":
            print("   ✅ Alice check-in submitted, waiting for webhook...")
            print(f"   Print Job ID: {data['print_job_id']}")
            
            # Simulate webhook (in real system, vendor would call)
            await simulate_webhook(client, data["attendee_id"], data["print_job_id"])
        else:
            print(f"   ❌ Unexpected status: {data['status']}")
            return
        
        # Test 2: Bob - Check-in
        print("\n2️⃣ Testing Bob - Normal Check-in")
        scan_id = f"test-bob-{uuid.uuid4()}"
        
        response = await client.post(
            f"{BASE_URL}/api/v1/scan",
            json={
                "attendee_id": TEST_ATTENDEES["bob"],
                "kiosk_id": "kiosk-01",
                "scan_id": scan_id,
                "badge_data": {
                    "name": "Bob Smith",
                    "company": "DataWorks",
                    "role": "Attendee"
                }
            }
        )
        
        data = response.json()
        print(f"   Status: {data['status']}")
        
        if data["status"] == "PENDING":
            print("   ✅ Bob check-in submitted")
            await simulate_webhook(client, data["attendee_id"], data["print_job_id"])
        
        # Test 3: Carol - Normal Check-in
        print("\n3️⃣ Testing Carol - Normal Check-in")
        scan_id = f"test-carol-{uuid.uuid4()}"
        
        response = await client.post(
            f"{BASE_URL}/api/v1/scan",
            json={
                "attendee_id": TEST_ATTENDEES["carol"],
                "kiosk_id": "kiosk-01",
                "scan_id": scan_id,
                "badge_data": {
                    "name": "Carol White",
                    "company": "CloudWare",
                    "role": "Exhibitor"
                }
            }
        )
        
        data = response.json()
        print(f"   Status: {data['status']}")
        
        if data["status"] == "PENDING":
            print("   ✅ Carol check-in submitted")
            await simulate_webhook(client, data["attendee_id"], data["print_job_id"])
        
        # Test 4: Duplicate scan (Alice again)
        print("\n4️⃣ Testing Duplicate Scan - Alice (should fail)")
        scan_id = f"test-alice-duplicate-{uuid.uuid4()}"
        
        response = await client.post(
            f"{BASE_URL}/api/v1/scan",
            json={
                "attendee_id": TEST_ATTENDEES["alice"],
                "kiosk_id": "kiosk-02",
                "scan_id": scan_id,
                "badge_data": {
                    "name": "Alice Johnson",
                    "company": "TechCorp Inc."
                }
            }
        )
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 409:
            data = response.json()
            print(f"   ✅ Duplicate detected: {data['status']}")
            print(f"   Message: {data['message']}")
        else:
            print(f"   ❌ Should have returned 409, got {response.status_code}")
        
        # Test 5: Check all attendees
        print("\n5️⃣ Verifying All Attendees Checked In")
        for name, attendee_id in TEST_ATTENDEES.items():
            response = await client.get(
                f"{BASE_URL}/api/v1/attendee/{attendee_id}/status"
            )
            if response.status_code == 200:
                data = response.json()
                print(f"   {name}: {data['badge_printed']} - {data.get('checked_in_at')}")
            else:
                print(f"   {name}: Error - {response.status_code}")
        
        print("\n" + "=" * 60)
        print("✅ Test Complete!")
        print("=" * 60)


async def simulate_webhook(client, attendee_id: str, print_job_id: str):
    """Simulate vendor webhook callback"""
    
    # Wait a moment
    await asyncio.sleep(1)
    
    # Generate vendor job ID
    vendor_job_id = f"vendor-{uuid.uuid4().hex[:8]}"
    
    # Send webhook
    response = await client.post(
        f"{BASE_URL}/webhook/print-callback",
        json={
            "job_id": vendor_job_id,
            "attendee_id": attendee_id,
            "status": "SUCCESS",
            "printed_at": datetime.utcnow().isoformat(),
            "badge_url": f"http://vendor.com/badges/{vendor_job_id}.pdf"
        }
    )
    
    if response.status_code == 200:
        print(f"   ✅ Webhook sent for {attendee_id}")
    else:
        print(f"   ❌ Webhook failed for {attendee_id}: {response.status_code}")


if __name__ == "__main__":
    asyncio.run(test_checkin_flow())