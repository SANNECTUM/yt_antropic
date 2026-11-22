@echo off
chcp 65001 >nul
title Установка Fooocus для RTX 4060 Ti
powershell.exe -ExecutionPolicy Bypass -File "%~dp0setup_fooocus.ps1"
pause
