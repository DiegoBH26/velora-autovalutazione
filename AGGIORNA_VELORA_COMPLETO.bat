@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Velora - Aggiornamento completo

echo.
echo ==========================================================
echo   VELORA - AGGIORNAMENTO COMPLETO
echo ==========================================================
echo.
echo CARTELLA IN USO:
echo %CD%
echo.
echo Chiudi l'agente Velora prima di continuare.
echo.
pause

set "BASE=https://raw.githubusercontent.com/DiegoBH26/velora-autovalutazione/main"

for %%F in (local_audit_server.py browser_audit_pilot.py site_audit_builder.py booking_engine.py) do (
  if exist "%%F" copy /Y "%%F" "%%F.bak" >nul 2>nul
)

echo [1/4] Scarico local_audit_server.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri '%BASE%/local_audit_server.py?nocache=%RANDOM%' -OutFile 'local_audit_server.py.new'"
if errorlevel 1 goto :errore

echo [2/4] Scarico browser_audit_pilot.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri '%BASE%/browser_audit_pilot.py?nocache=%RANDOM%' -OutFile 'browser_audit_pilot.py.new'"
if errorlevel 1 goto :errore

echo [3/4] Scarico site_audit_builder.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri '%BASE%/site_audit_builder.py?nocache=%RANDOM%' -OutFile 'site_audit_builder.py.new'"
if errorlevel 1 goto :errore

echo [4/4] Scarico booking_engine.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri '%BASE%/booking_engine.py?nocache=%RANDOM%' -OutFile 'booking_engine.py.new'"
if errorlevel 1 goto :errore

for %%F in (local_audit_server.py.new browser_audit_pilot.py.new site_audit_builder.py.new booking_engine.py.new) do (
  for %%S in ("%%F") do if %%~zS LSS 1000 goto :errore
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=Get-Content 'local_audit_server.py.new' -Raw; $p=Get-Content 'browser_audit_pilot.py.new' -Raw; $sv=[regex]::Match($s,'velora-local-agent-v(\d+)').Groups[1].Value; $pv=[regex]::Match($p,'velora-browser-pilot-v(\d+)').Groups[1].Value; if(-not $sv -or -not $pv -or $sv -ne $pv){ Write-Host ('ERRORE VERSIONI: agente v'+$sv+' / pilot v'+$pv); exit 2 } else { Write-Host ('Versioni scaricate sincronizzate: v'+$sv) }"
if errorlevel 1 goto :errore

move /Y "local_audit_server.py.new" "local_audit_server.py" >nul
move /Y "browser_audit_pilot.py.new" "browser_audit_pilot.py" >nul
move /Y "site_audit_builder.py.new" "site_audit_builder.py" >nul
move /Y "booking_engine.py.new" "booking_engine.py" >nul

if exist "__pycache__" (
  del /Q "__pycache__\browser_audit_pilot*.pyc" 2>nul
  del /Q "__pycache__\local_audit_server*.pyc" 2>nul
)

echo.
echo ==========================================================
echo   AGGIORNAMENTO COMPLETATO
echo ==========================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=Get-Content 'local_audit_server.py' -Raw; $p=Get-Content 'browser_audit_pilot.py' -Raw; $sv=[regex]::Match($s,'velora-local-agent-v(\d+)').Groups[1].Value; $pv=[regex]::Match($p,'velora-browser-pilot-v(\d+)').Groups[1].Value; Write-Host ('Agente: v'+$sv); Write-Host ('Pilot:  v'+$pv)"
echo.
echo Ora chiudi questa finestra e avvia AVVIA_AGENTE_VELORA.bat
echo dalla stessa cartella.
echo.
pause
exit /b 0

:errore
echo.
echo ==========================================================
echo   ERRORE DURANTE L'AGGIORNAMENTO
echo ==========================================================
echo.
echo I vecchi file sono stati salvati come .bak.
del /Q "*.py.new" 2>nul
echo.
echo Mandami una foto di questa schermata.
echo.
pause
exit /b 1
