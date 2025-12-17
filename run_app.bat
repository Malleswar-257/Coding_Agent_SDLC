@echo off
echo Starting CODE AGENT...
echo.
cd /d "%~dp0"
python -m streamlit run app.py --server.port 8501 --server.address localhost
pause

