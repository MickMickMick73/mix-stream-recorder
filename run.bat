@echo off
title MiX Stream Recorder
cd /d "%~dp0"

echo.
echo  ========================================
echo   MiX Stream Recorder
echo  ========================================
echo   If this is the first run, Python packages
echo   will install - wait for the window.
echo.
echo   Need help? Open START-HERE.txt
echo  ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo  ERROR: Python not found.
  echo  Install from https://www.python.org/downloads/
  echo  and TICK "Add python.exe to PATH"
  echo.
  pause
  exit /b 1
)

python -m pip install -r requirements.txt -q
if errorlevel 1 (
  echo  Could not install packages. Check internet / Python install.
  pause
  exit /b 1
)

python app.py
if errorlevel 1 (
  echo.
  echo  App exited with an error.
  echo  Common fix: install ffmpeg  -^>  winget install Gyan.FFmpeg
  echo  Then close this window and run run.bat again.
  echo.
  pause
)
