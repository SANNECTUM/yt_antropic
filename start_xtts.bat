@echo off
chcp 65001 >nul
title Coqui XTTS-v2 Local Server (RTX 4060 Ti)

echo ================================================================
echo   🎙️  ЗАПУСК ЛОКАЛЬНОГО СЕРВЕРА СИНТЕЗА РЕЧИ COQUI XTTS-v2
echo   🚀  Ускорение на видеокарте NVIDIA (RTX 4060 Ti)
echo ================================================================
echo.

:: Проверка наличия Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ОШИБКА] Python не найден в системе. Установите Python 3.10 или 3.11.
    pause
    exit /b 1
)

:: Проверка наличия пакета TTS
python -c "import TTS" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [*] Библиотека Coqui TTS еще не установлена.
    echo [*] Выполняется установка torch с поддержкой CUDA и TTS...
    echo.
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    pip install TTS
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo [!] Ошибка при автоматической установке TTS.
        echo [!] Рекомендуется установить в окружение Python 3.10 или 3.11:
        echo     pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
        echo     pip install TTS
        pause
        exit /b 1
    )
)

echo [*] Запуск сервера на порту 8020...
echo [*] Адрес: http://127.0.0.1:8020/
echo.
python scripts\xtts_server.py --port 8020

pause
