@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py damogran.py %*) || (python damogran.py %*)
if errorlevel 1 (
  echo.
  echo Python est introuvable ou a plante. Installe-le depuis https://www.python.org/downloads/ ^(coche "Add python.exe to PATH"^).
  pause
)
