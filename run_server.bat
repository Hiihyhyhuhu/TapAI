@echo off
chcp 65001 > nul
title Tap AI Merchant Portal Server

echo =====================================================================
echo           TAP AI - DIRECT MERCHANT PORTAL SERVER
echo =====================================================================
echo.
echo [1/2] Đang khởi động Backend FastAPI & Web Portal...
echo.

REM Kiểm tra Python
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set PY_CMD=python
) else (
    set PY_CMD="C:\Users\LENOVO\AppData\Local\Programs\Python\Python312\python.exe"
)

REM Khởi chạy Uvicorn Backend Server và tự động mở trình duyệt
start "" "http://localhost:8000/portal/index.standalone.html"
%PY_CMD% -m uvicorn main:app --host 127.0.0.1 --port 8000 --app-dir backend --reload

pause
