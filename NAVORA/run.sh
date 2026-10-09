#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

echo "==================================================================="
echo "🚀 Starting NAVORA FastAPI Server"
echo "🖥️  Interactive Dashboard:  http://127.0.0.1:8000"
echo "📖 Swagger API Docs:       http://127.0.0.1:8000/docs"
echo "==================================================================="

exec uvicorn main:app --host 127.0.0.1 --port 8000 --reload
