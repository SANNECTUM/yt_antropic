<#
.SYNOPSIS
Автоматическая установка Fooocus для генерации фотореалистичных кадров на RTX 4060 Ti.
#>

param(
    [string]$InstallDir = "C:\Fooocus"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Установка Fooocus (SDXL для YouTube Production)" -ForegroundColor Cyan
Write-Host "  Целевая папка: $InstallDir" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

$7zExe = "C:\Program Files\7-Zip\7z.exe"
if (-not (Test-Path $7zExe)) {
    $7zExe = (Get-Command 7z -ErrorAction SilentlyContinue).Source
}
if (-not $7zExe -or -not (Test-Path $7zExe)) {
    Write-Host "[ОШИБКА] 7-Zip не найден! Установите 7-Zip (https://www.7-zip.org/) и повторите запуск." -ForegroundColor Red
    pause
    exit 1
}

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

$archiveName = "Fooocus_win64_2-5-0.7z"
$archivePath = Join-Path $InstallDir $archiveName
$downloadUrl = "https://github.com/lllyasviel/Fooocus/releases/download/v2.5.0/Fooocus_win64_2-5-0.7z"

if (-not (Test-Path $archivePath)) {
    Write-Host "`n[1/3] Скачивание официального архива Fooocus (~1.8 ГБ)..." -ForegroundColor Green
    Write-Host "URL: $downloadUrl" -ForegroundColor Gray
    curl.exe -L -o $archivePath $downloadUrl --progress-bar
} else {
    Write-Host "`n[1/3] Архив $archiveName уже скачан!" -ForegroundColor Green
}

Write-Host "`n[2/3] Распаковка архива через 7-Zip в $InstallDir..." -ForegroundColor Green
& $7zExe x $archivePath "-o$InstallDir" -y

# Создаем удобный батник запуска
$startBat = Join-Path $InstallDir "start_realistic.bat"
$batContent = @"
@echo off
title Fooocus Realistic (RTX 4060 Ti)
cd /d "%~dp0Fooocus"
call ..\python_embeded\python.exe -s Fooocus\entry_with_update.py --preset realistic
pause
"@
Set-Content -Path $startBat -Value $batContent -Encoding Ascii

# Также создаем shortcut в корне проекта
$projBat = Join-Path $PSScriptRoot "start_fooocus.bat"
$projBatContent = @"
@echo off
title Fooocus Launcher
cd /d "$InstallDir"
if exist "run_realistic.bat" (
    call run_realistic.bat
) else (
    call start_realistic.bat
)
"@
Set-Content -Path $projBat -Value $projBatContent -Encoding Ascii

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "  ✅ Fooocus успешно установлен в $InstallDir!" -ForegroundColor Green
Write-Host "  Для запуска дважды кликните по start_fooocus.bat в проекте" -ForegroundColor Yellow
Write-Host "  или запустите $InstallDir\run_realistic.bat" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan
