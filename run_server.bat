@echo off
title Tap AI Backend Server
set PYTHONIOENCODING=utf-8
echo Dang khoi dong Tap AI Backend Server...
.\venv\Scripts\uvicorn.exe main:app --app-dir backend --reload --reload-dir backend --port 8000
pause
