#!/usr/bin/env bash
# Kaveri Spares & Hydraulics - Supply Chain Copilot Launcher
set -e

echo "=========================================================="
echo "  Kaveri Spares & Hydraulics - Supply Chain Copilot       "
echo "  Hackathon Challenge 01 (Agentic AI for Supply Chain)    "
echo "=========================================================="

echo "[1/3] Seeding benchmark scenario operational records..."
python engine/mock_data_gen.py

echo "[2/3] Running automated pytest test suite..."
pytest tests/test_decisions.py -v

echo "[3/3] Launching FastAPI Backend and Streamlit Dashboard..."
python -m uvicorn app.server:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!

trap "kill $SERVER_PID 2>/dev/null || true" EXIT

python -m streamlit run app/dashboard.py --server.port 8501
