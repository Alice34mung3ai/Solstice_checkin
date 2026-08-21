#!/bin/bash

echo "============================================================"
echo "🚀 Starting Solstice Check-in Service"
echo "============================================================"

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Install dependencies
pip install -r requirements.txt

# Seed test data
python scripts/seed_test_data.py

# Start the service
python run.py