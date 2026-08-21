"""
Seed test attendees for development
Run: python scripts/seed_test_data.py
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment
from dotenv import load_dotenv
load_dotenv()

from app.database import create_tables_sync, SyncSessionLocal
from app.models import Attendee
import uuid


TEST_ATTENDEES = [
    {
        "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "email": "alice@techconf.com",
        "full_name": "Alice Johnson",
        "company": "TechCorp Inc.",
        "role": "Speaker"
    },
    {
        "id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
        "email": "bob@techconf.com",
        "full_name": "Bob Smith",
        "company": "DataWorks",
        "role": "Attendee"
    },
    {
        "id": uuid.UUID("33333333-3333-3333-3333-333333333333"),
        "email": "carol@techconf.com",
        "full_name": "Carol White",
        "company": "CloudWare",
        "role": "Exhibitor"
    }
]


def seed_test_attendees():
    """Seed database with test attendees"""
    print("=" * 60)
    print("👤 Seeding Test Attendees to PostgreSQL")
    print("=" * 60)
    
    # Create tables
    create_tables_sync()
    print("✅ Tables created/verified")
    
    with SyncSessionLocal() as db:
        from sqlalchemy import select
        
        for data in TEST_ATTENDEES:
            # Check if exists
            stmt = select(Attendee).where(Attendee.id == data["id"])
            result = db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if not existing:
                attendee = Attendee(**data)
                db.add(attendee)
                print(f"✅ Added: {data['full_name']} ({data['email']})")
            else:
                print(f"⏭️  Already exists: {data['full_name']}")
        
        db.commit()
        print("=" * 60)
        print("✅ Test attendees seeded successfully!")
        print("=" * 60)


if __name__ == "__main__":
    seed_test_attendees()