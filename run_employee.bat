@echo off
setlocal
cd /d "%~dp0"
python employee_portal.py
if errorlevel 1 pause
