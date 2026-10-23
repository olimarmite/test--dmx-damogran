@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py damogran.py --lan %*) || (python damogran.py --lan %*)
pause
