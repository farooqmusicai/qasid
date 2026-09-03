@echo off
cd /d "%~dp0"
title Qasid
where py >nul 2>&1 || (echo Python not found. Install it from python.org and tick "Add to PATH". & pause & exit /b 1)
py -3 -m qasid
echo.
pause
