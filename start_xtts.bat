@echo off
title Coqui XTTS-v2 Local Server (RTX 4060 Ti)

echo ================================================================
echo   COQUI XTTS-v2 LOCAL SERVER (NVIDIA RTX 4060 Ti)
echo ================================================================
echo.

set "PY_XTTS=.venv_xtts\Scripts\python.exe"
set "PIP_XTTS=.venv_xtts\Scripts\pip.exe"

if not exist "%PY_XTTS%" (
    echo [*] Creating Python 3.11 environment .venv_xtts...
    if exist "C:\Users\berze\AppData\Local\Programs\Python\Python311\python.exe" (
        "C:\Users\berze\AppData\Local\Programs\Python\Python311\python.exe" -m venv .venv_xtts
    ) else (
        py -3.11 -m venv .venv_xtts
    )
)

if not exist "%PY_XTTS%" (
    echo [ERROR] Python 3.11 environment .venv_xtts not found.
    pause
    exit /b 1
)

"%PY_XTTS%" -c "import torch, six, TTS" >nul 2>&1
if errorlevel 1 (
    echo [*] Installing PyTorch CUDA 12.1 and Coqui TTS into .venv_xtts...
    "%PIP_XTTS%" install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
    "%PIP_XTTS%" install six coqui-tts
)

set COQUI_TOS_AGREED=1
echo [*] Starting XTTS server on http://127.0.0.1:8020/ ...
echo.
"%PY_XTTS%" scripts\xtts_server.py --port 8020

pause
