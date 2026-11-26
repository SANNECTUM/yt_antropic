@echo off
chcp 65001 >nul
title Coqui XTTS-v2 Local Server (RTX 4060 Ti)

echo ================================================================
echo   🎙️  ЗАПУСК ЛОКАЛЬНОГО СЕРВЕРА СИНТЕЗА РЕЧИ COQUI XTTS-v2
echo   🚀  Ускорение на видеокарте NVIDIA (RTX 4060 Ti)
echo ================================================================
echo.

set "PY_XTTS=.venv_xtts\Scripts\python.exe"
set "PIP_XTTS=.venv_xtts\Scripts\pip.exe"

:: Создаем выделенное окружение Python 3.11 для Coqui XTTS, если оно еще не создано
if not exist "%PY_XTTS%" (
    echo [*] Создание выделенного окружения .venv_xtts на базе Python 3.11...
    if exist "C:\Users\berze\AppData\Local\Programs\Python\Python311\python.exe" (
        "C:\Users\berze\AppData\Local\Programs\Python\Python311\python.exe" -m venv .venv_xtts
    ) else (
        py -3.11 -m venv .venv_xtts
    )
)

if not exist "%PY_XTTS%" (
    echo [ОШИБКА] Не удалось найти или создать окружение Python 3.11 (.venv_xtts).
    pause
    exit /b 1
)

:: Проверяем наличие coqui-tts и torch с поддержкой CUDA
"%PY_XTTS%" -c "import torch, TTS; assert torch.cuda.is_available()" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [*] Проверка и установка PyTorch CUDA 12.1 и Coqui TTS в .venv_xtts...
    "%PIP_XTTS%" install coqui-tts
    "%PIP_XTTS%" install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
)

set COQUI_TOS_AGREED=1
echo [*] Запуск сервера на порту 8020...
echo [*] Адрес: http://127.0.0.1:8020/
echo.
"%PY_XTTS%" scripts\xtts_server.py --port 8020

pause
