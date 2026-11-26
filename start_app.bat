@echo off
chcp 65001 >nul
title YouTube Production Assistant (Streamlit Web UI)
echo ================================================================
echo   🎬 ЗАПУСК ЛОКАЛЬНОГО ВЕБ-ИНТЕРФЕЙСА YOUTUBE ASSISTANT
echo ================================================================
echo.
if exist .venv\Scripts\streamlit.exe (
    .venv\Scripts\streamlit.exe run web_ui.py --server.port 8501
) else (
    streamlit run web_ui.py --server.port 8501
)
pause
