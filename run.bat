@echo off
echo ==========================================================
echo   Kaveri Spares & Hydraulics - Supply Chain Copilot
echo   Hackathon Challenge 01 (Agentic AI for Supply Chain)
echo ==========================================================

cd /d "%~dp0kaveri_copilot"

echo [1/3] Seeding benchmark scenario operational records...
python engine\mock_data_gen.py

echo [2/3] Running automated pytest test suite...
pytest tests\test_decisions.py -v

echo [3/3] Launching Streamlit Executive Dashboard...
python -m streamlit run app\dashboard.py --server.port 8501
