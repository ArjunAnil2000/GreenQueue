#!/usr/bin/env bash
set -e

# Kill any existing process on port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

# Navigate to backend
cd "$(dirname "$0")/backend"

# Create venv if it doesn't exist
if [ ! -d "../.venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv ../.venv
fi

# Activate venv
source ../.venv/bin/activate

# Install dependencies
pip install -q -r requirements.txt

# Start the server
echo "Starting GreenQueue on http://127.0.0.1:8000"
python server.py
