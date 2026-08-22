import asyncio
import uuid
from app.database import AsyncSessionLocal
from app.models import Attendee

TEST_ATTENDEES = [
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "email": "alice@solstice.com",
        "full_name": "Alice Johnson",
        "company": "TechCorp",
        "role": "Speaker"
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
        "email": "bob@solstice.com",
        "full_name": "Bob Smith",
        "company": "DataCorp",
        "role": "Attendee"
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000003"),
        "email": "carol@solstice.com",
        "full_name": "Carol White",
        "company": "CloudWare",
        "role": "Exhibitor"
    }
]

async def seed_test_attendees():
    async with AsyncSessionLocal() as db:
        for data in TEST_ATTENDEES:
            # Check if exists
            from sqlalchemy import select
            stmt = select(Attendee).where(Attendee.id == data["id"])
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if not existing:
                attendee = Attendee(**data)
                db.add(attendee)
                print(f"✅ Added: {data['full_name']}")
            else:
                print(f"⏭️  Already exists: {data['full_name']}")
        
        await db.commit()
        print("✅ Test attendees seeded successfully")

if __name__ == "__main__":
    asyncio.run(seed_test_attendees())