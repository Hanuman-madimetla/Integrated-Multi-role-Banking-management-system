@echo off
setlocal
cd /d "%~dp0"
python customer_portal.py
if errorlevel 1 pause
