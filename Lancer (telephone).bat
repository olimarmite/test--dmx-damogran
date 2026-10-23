@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0damogran.ps1" -Lan %*
if errorlevel 1 pause
