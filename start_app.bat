@echo off
title YouTube Production Assistant (Streamlit Web UI)

echo ================================================================
echo   YOUTUBE PRODUCTION ASSISTANT - LOCAL WEB UI
echo ================================================================
echo.

if exist ".venv\Scripts\streamlit.exe" (
    ".venv\Scripts\streamlit.exe" run web_ui.py --server.port 8501
) else (
    streamlit run web_ui.py --server.port 8501
)
pause
