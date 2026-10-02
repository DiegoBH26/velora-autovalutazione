@echo off
setlocal
cd /d "%~dp0"
title Velora - Agente locale

echo.
echo ==================================================
echo   VELORA - AGENTE LOCALE GRATUITO
echo.
echo   Lascia aperta questa finestra mentre usi
echo   Velora online nel browser.
echo ==================================================
echo.

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" local_audit_server.py
  goto :end
)

where py >nul 2>nul
if %errorlevel%==0 (
  echo Ambiente .venv non trovato. Provo con Python installato sul PC...
  py -3 local_audit_server.py
  goto :end
)

where python >nul 2>nul
if %errorlevel%==0 (
  echo Ambiente .venv non trovato. Provo con Python installato sul PC...
  python local_audit_server.py
  goto :end
)

echo.
echo Python non trovato. Esegui prima INSTALLA_AGENTE_VELORA.bat.

:end
echo.
echo Agente Velora terminato. Premi un tasto per chiudere.
pause >nul
