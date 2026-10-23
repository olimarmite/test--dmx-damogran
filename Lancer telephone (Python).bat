@echo off
cd /d "%~dp0"
rem Python portable fourni dans le dossier python\ (aucune installation, aucun droit admin)
if exist "%~dp0python\python.exe" (
  "%~dp0python\python.exe" damogran.py --lan %*
) else (
  py damogran.py --lan %* 2>nul || python damogran.py --lan %*
)
if errorlevel 1 pause
