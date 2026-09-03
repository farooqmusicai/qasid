@echo off
setlocal
cd /d "%~dp0"
title Qasid - daily schedule
set "TASKNAME=qasid"
set "RUNNER=%~dp0scheduled-run.bat"

echo ============================================================
echo   Qasid - the daily schedule
echo ============================================================
echo.
echo  1  Is it installed?    - just look, change nothing
echo  2  Install + PROVE it  - registers it, then runs it once for real
echo  3  Remove it           - stop all automatic posting
echo.
set /p pick=Choose 1, 2 or 3:

if "%pick%"=="1" goto :check
if "%pick%"=="2" goto :install
if "%pick%"=="3" goto :remove
goto :done

:check
echo.
schtasks /Query /TN "%TASKNAME%" >nul 2>&1
if errorlevel 1 ( echo   [X] NOT INSTALLED - nothing will post on its own. & goto :done )
schtasks /Query /TN "%TASKNAME%" /V /FO LIST | findstr /C:"Status" /C:"Next Run Time" /C:"Last Run Time" /C:"Last Result" /C:"Task To Run"
echo.
if exist "logs\task.log" (
  echo   Proof it has really run:
  powershell -NoProfile -Command "Get-Content 'logs\task.log' -Tail 8"
) else (
  echo   [!] Registered, but it has NEVER run. Registered is not working.
  echo       Choose 2 to install and prove it in one go.
)
goto :done

:install
echo.
echo   Registering ...
schtasks /Create /F /TN "%TASKNAME%" /SC MINUTE /MO 15 /TR "%RUNNER%"
if errorlevel 1 (
  echo.
  echo   [X] Could not register it. Nothing is scheduled.
  echo       If it says access denied, right-click this file and choose
  echo       "Run as administrator".
  goto :done
)
echo.
echo   Registered. Now proving it runs, instead of assuming ...
if exist "logs\task.log" del /q "logs\task.log"
schtasks /Run /TN "%TASKNAME%" >nul 2>&1
powershell -NoProfile -Command "Start-Sleep -Seconds 25"
echo.
if exist "logs\task.log" (
  echo   ==========================================================
  echo     WORKING - the task ran and reported back:
  echo   ==========================================================
  powershell -NoProfile -Command "Get-Content 'logs\task.log' -Tail 8"
  echo   ==========================================================
  echo   It now checks every 15 minutes and posts each channel at
  echo   its own time. The computer must be awake.
  echo.
  echo   To pause without removing it, make an empty file named
  echo   PAUSE in this folder. Delete it to carry on.
) else (
  echo   ==========================================================
  echo     [X] NOT WORKING - the task exists but produced no log.
  echo   ==========================================================
  echo   Do not rely on it. Here is what Windows thinks it runs:
  schtasks /Query /TN "%TASKNAME%" /V /FO LIST | findstr /C:"Task To Run" /C:"Last Result"
)
goto :done

:remove
echo.
schtasks /Delete /F /TN "%TASKNAME%"
echo   Removed - nothing posts automatically now.
goto :done

:done
echo.
pause
