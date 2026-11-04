@echo off
setlocal enabledelayedexpansion
title SinyalAbidnet Kliper Pro - Mobile Server
cd /d "%~dp0"

set "BACKEND=%~dp0resources\backend\cheat-clip-backend.exe"
set "WEBDIR=%~dp0resources\web"
set "DATADIR=%APPDATA%\SinyalAbidnet Kliper Pro\data"

if not exist "%BACKEND%" (
    echo [ERROR] Backend tidak ditemukan:
    echo   %BACKEND%
    echo.
    echo Pastikan file ini berada di folder instalasi SinyalAbidnet Kliper Pro.
    pause
    exit /b 1
)

if not exist "%WEBDIR%\index.html" (
    echo [ERROR] Web assets tidak ditemukan:
    echo   %WEBDIR%
    pause
    exit /b 1
)

set "HOST=0.0.0.0"
set "PORT=8000"
set "RELOAD=0"
set "PYTHONUNBUFFERED=1"
set "PYTHONIOENCODING=utf-8"
set "CHEAT_CLIP_WEB_DIR=%WEBDIR%"
set "CHEAT_CLIP_DATA_DIR=%DATADIR%"
set "PATH=%~dp0resources\backend;%PATH%"

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set "LANIP=%%a"
    set "LANIP=!LANIP: =!"
    goto :gotip
)
:gotip
if not defined LANIP set "LANIP=IP-PC-ANDA"

echo ===================================================
echo   SinyalAbidnet Kliper Pro - Mobile Server
echo ===================================================
echo   Buka di HP: http://!LANIP!:8000
echo   APK Android: SinyalAbidnet-Kliper-Pro-Mobile-1.0.3.apk
echo.
echo   Izinkan port 8000 di Windows Firewall jika diminta.
echo   Tutup aplikasi desktop dulu agar tidak bentrok memakai data yang sama.
echo   Tekan Ctrl+C untuk menghentikan server.
echo ===================================================
echo.

pushd "%~dp0resources\backend"
"%BACKEND%"
set "EXITCODE=%errorlevel%"
popd

if not "%EXITCODE%"=="0" (
    echo.
    echo [WARNING] Server berhenti dengan error code %EXITCODE%.
    pause
)
