#!/usr/bin/env bash
echo "==================================================="
echo "            Launching WebAgent AI Assistant"
echo "==================================================="

if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Checking dependencies..."
pip install -q -r requirements.txt piper-tts

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
fi

echo ""
echo "Starting WebAgent Server on http://localhost:8000 ..."
echo "Press Ctrl+C to stop."
echo ""

python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
