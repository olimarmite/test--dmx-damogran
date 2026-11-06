@echo off
setlocal
cd /d "%~dp0"
rem Lance Damogran. Sans Python sur le PC, telecharge une seule fois le Python portable officiel
rem (python.org, 11 Mo, dans le dossier python\ : aucune installation, aucun droit admin).

set "EMB=%~dp0python\python.exe"
if exist "%EMB%" goto embedded
py -3 -c "import sys" >nul 2>&1 && (set PY=py -3& goto run)
python -c "import sys; sys.exit(sys.version_info < (3, 8))" >nul 2>&1 && (set PY=python& goto run)

echo Premier lancement : telechargement de Python portable depuis python.org, 11 Mo...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop'; [Net.ServicePointManager]::SecurityProtocol = 'Tls12';" ^
  "$z = Join-Path $env:TEMP 'damogran-python.zip';" ^
  "Invoke-WebRequest -UseBasicParsing 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-embed-amd64.zip' -OutFile $z;" ^
  "if ((Get-FileHash $z -Algorithm SHA256).Hash -ne '0D57BB6CB078B74D23DBFE91F77D6780D45BED328911609F1F7EE2BA1606BF44') { Remove-Item $z; throw 'fichier telecharge corrompu' };" ^
  "Expand-Archive -Force $z 'python'; Remove-Item $z"
if exist "%EMB%" goto embedded
echo.
echo Impossible de recuperer Python. Sur python.org, telecharge le "Windows embeddable package 64-bit"
echo de Python 3.12 et extrais-le dans un dossier "python" a cote de ce fichier.
pause
exit /b 1

:embedded
set PY="%EMB%"
:run
%PY% damogran.py %*
if errorlevel 1 pause
