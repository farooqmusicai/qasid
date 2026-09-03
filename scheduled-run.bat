@echo off
rem What the Windows task actually runs. Its own file on purpose: putting this
rem command inside schtasks /TR needs nested quotes, and a badly quoted /TR
rem registers a task that looks installed and never runs even once.
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
echo. >> "logs\task.log"
echo ---- %DATE% %TIME% ---- >> "logs\task.log"
py -3 -m qasid --run >> "logs\task.log" 2>&1
