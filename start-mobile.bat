@echo off
setlocal enabledelayedexpansion
title SinyalAbidnet Kliper Pro - Mobile Server
cd /d "%~dp0"

echo ===================================================
echo   SinyalAbidnet Kliper Pro - Mobile / LAN Server
echo ===================================================

if exist "%~dp0venv\Scripts" (
    set "PATH=%~dp0venv\Scripts;%PATH%"
) else if exist "%~dp0.venv\Scripts" (
    set "PATH=%~dp0.venv\Scripts;%PATH%"
)

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python tidak ditemukan.
    echo Install Python 3.11+ atau jalankan start.bat sekali.
    pause
    exit /b 1
)

if not exist "dist\index.html" (
    echo [INFO] Frontend belum dibuild. Menjalankan npm run build...
    call npm run build
    if errorlevel 1 (
        echo [ERROR] Build frontend gagal.
        pause
        exit /b 1
    )
)

set "HOST=0.0.0.0"
set "PORT=8000"
set "RELOAD=0"
set "PYTHONUNBUFFERED=1"
set "PYTHONIOENCODING=utf-8"

echo.
echo Mencari IP LAN...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set "LANIP=%%a"
    set "LANIP=!LANIP: =!"
    goto :gotip
)
:gotip
if not defined LANIP set "LANIP=IP-PC-ANDA"

echo.
echo ===================================================
echo   Buka di HP (satu Wi-Fi dengan PC ini):
echo     http://!LANIP!:8000
echo.
echo   APK Android: SinyalAbidnet-Kliper-Pro-Mobile-1.0.3.apk
echo   Masukkan alamat di atas saat aplikasi meminta server.
echo.
echo   Jika HP tidak bisa connect:
echo     1. Pastikan PC dan HP di Wi-Fi yang sama.
echo     2. Izinkan port 8000 di Windows Firewall.
echo        Jalankan PowerShell sebagai Administrator:
echo        netsh advfirewall firewall add rule name="SinyalAbidnet Kliper Pro" dir=in action=allow protocol=TCP localport=8000
echo     3. Tutup aplikasi desktop dulu agar tidak bentrok memakai data yang sama.
echo ===================================================
echo.

python -m backend.main
if errorlevel 1 (
    echo.
    echo [WARNING] Server berhenti dengan error code %errorlevel%.
    pause
)
