@echo off
echo ============================================================
echo 🚀 Starting Solstice Check-in Service
echo ============================================================

REM Activate virtual environment
if exist venv (
    call venv\Scripts\activate
)

REM Install dependencies
pip install -r requirements.txt

REM Seed test data
python scripts\seed_test_data.py

REM Start the service
python run.py