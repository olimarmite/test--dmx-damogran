@echo off
setlocal
cd /d "%~dp0"
rem Lance Damogran avec uv (astral.sh). Tout reste dans le dossier uv\ a cote de ce fichier :
rem aucune installation systeme, aucun droit admin. Le premier lancement a besoin d'Internet.

rem Dossier python\ fourni avec certains ZIP (PC sans Internet) : on s'en sert directement.
if exist "%~dp0python\python.exe" (
  "%~dp0python\python.exe" damogran.py %*
  goto done
)

set "UV_INSTALL_DIR=%~dp0uv"
set "UV_PYTHON_INSTALL_DIR=%~dp0uv\python"
set "UV_CACHE_DIR=%~dp0uv\cache"
set "UV_NO_MODIFY_PATH=1"
set "UV=%~dp0uv\uv.exe"

if not exist "%UV%" (
  echo Premier lancement : installation de uv dans le dossier uv, sans droits admin...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/0.13.5/install.ps1 | iex"
)
if not exist "%UV%" (
  echo.
  echo Impossible d'installer uv : ce PC a-t-il Internet ? Voir le README, section Demarrage.
  pause
  exit /b 1
)

"%UV%" run --python-preference only-managed damogran.py %*

:done
if errorlevel 1 pause
