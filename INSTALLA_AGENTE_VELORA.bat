@echo off
setlocal
cd /d "%~dp0"
title Velora - Installazione agente locale

echo Creo/aggiorno l'ambiente Python locale di Velora...
where py >nul 2>nul
if not %errorlevel%==0 (
  echo Python launcher non trovato. Installa Python 3.12 o 3.13 e riprova.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements-scraping.txt
".venv\Scripts\python.exe" -m playwright install chromium

echo.
echo Installazione completata. Ora usa AVVIA_AGENTE_VELORA.bat.
pause
