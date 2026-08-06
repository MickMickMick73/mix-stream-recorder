@echo off
cd /d "%~dp0"
title MiX Stream Recorder
python -m pip install -r requirements.txt -q
python app.py
if errorlevel 1 pause
