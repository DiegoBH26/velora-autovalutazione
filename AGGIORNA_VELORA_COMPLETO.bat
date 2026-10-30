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

for %%F in (local_audit_server.py browser_audit_pilot.py site_audit_builder.py booking_engine.py velora_quote_history.py velora_agent_network.py velora_portal_sessions.py ota_public_source_hints.json) do (
  if exist "%%F" copy /Y "%%F" "%%F.bak" >nul 2>nul
)

echo [1/8] Scarico local_audit_server.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri '%BASE%/local_audit_server.py?nocache=%RANDOM%' -OutFile 'local_audit_server.py.new'"
if errorlevel 1 goto :errore

echo [2/8] Scarico browser_audit_pilot.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri '%BASE%/browser_audit_pilot.py?nocache=%RANDOM%' -OutFile 'browser_audit_pilot.py.new'"
if errorlevel 1 goto :errore

echo [3/8] Scarico site_audit_builder.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri '%BASE%/site_audit_builder.py?nocache=%RANDOM%' -OutFile 'site_audit_builder.py.new'"
if errorlevel 1 goto :errore

echo [4/8] Scarico booking_engine.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri '%BASE%/booking_engine.py?nocache=%RANDOM%' -OutFile 'booking_engine.py.new'"
if errorlevel 1 goto :errore

echo [5/8] Scarico velora_quote_history.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri '%BASE%/velora_quote_history.py?nocache=%RANDOM%' -OutFile 'velora_quote_history.py.new'"
if errorlevel 1 goto :errore

echo [6/8] Scarico rete agenti specialisti...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri '%BASE%/velora_agent_network.py?nocache=%RANDOM%' -OutFile 'velora_agent_network.py.new'"
if errorlevel 1 goto :errore

echo [7/8] Scarico il modulo di sessioni OTA autorizzate...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri '%BASE%/velora_portal_sessions.py?nocache=%RANDOM%' -OutFile 'velora_portal_sessions.py.new'"
if errorlevel 1 goto :errore

echo [8/8] Scarico riferimenti pubblici OTA forniti dall'utente...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri '%BASE%/ota_public_source_hints.json?nocache=%RANDOM%' -OutFile 'ota_public_source_hints.json.new'"
if errorlevel 1 goto :errore
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try{$h=Get-Content 'ota_public_source_hints.json.new' -Raw | ConvertFrom-Json; if($h.schema -ne 'velora-public-ota-source-hints-v1'){exit 2}}catch{exit 2}"
if errorlevel 1 goto :errore

for %%F in (local_audit_server.py.new browser_audit_pilot.py.new site_audit_builder.py.new booking_engine.py.new velora_quote_history.py.new velora_agent_network.py.new velora_portal_sessions.py.new) do (
  for %%S in ("%%F") do if %%~zS LSS 1000 goto :errore
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=Get-Content 'local_audit_server.py.new' -Raw; $p=Get-Content 'browser_audit_pilot.py.new' -Raw; $sv=[regex]::Match($s,'velora-local-agent-v(\d+)').Groups[1].Value; $pv=[regex]::Match($p,'velora-browser-pilot-v(\d+)').Groups[1].Value; if(-not $sv -or -not $pv -or $sv -ne $pv){ Write-Host ('ERRORE VERSIONI: agente v'+$sv+' / pilot v'+$pv); exit 2 } else { Write-Host ('Versioni scaricate sincronizzate: v'+$sv) }"
if errorlevel 1 goto :errore

move /Y "local_audit_server.py.new" "local_audit_server.py" >nul
move /Y "browser_audit_pilot.py.new" "browser_audit_pilot.py" >nul
move /Y "site_audit_builder.py.new" "site_audit_builder.py" >nul
move /Y "booking_engine.py.new" "booking_engine.py" >nul
move /Y "velora_quote_history.py.new" "velora_quote_history.py" >nul
move /Y "velora_agent_network.py.new" "velora_agent_network.py" >nul
move /Y "velora_portal_sessions.py.new" "velora_portal_sessions.py" >nul
move /Y "ota_public_source_hints.json.new" "ota_public_source_hints.json" >nul

if exist "__pycache__" (
  del /Q "__pycache__\browser_audit_pilot*.pyc" 2>nul
  del /Q "__pycache__\local_audit_server*.pyc" 2>nul
  del /Q "__pycache__\velora_agent_network*.pyc" 2>nul
  del /Q "__pycache__\velora_portal_sessions*.pyc" 2>nul
)

rem Verifica reale: file scaricati non significa agenti importabili.
set "VELORA_PY="
if exist ".venv\Scripts\python.exe" set "VELORA_PY=.venv\Scripts\python.exe"
if defined VELORA_PY goto :verifica_import
where py >nul 2>nul
if not errorlevel 1 set "VELORA_PY=py -3"
if defined VELORA_PY goto :verifica_import
where python >nul 2>nul
if not errorlevel 1 set "VELORA_PY=python"
:verifica_import
if not defined VELORA_PY goto :errore_import
echo.
echo Verifico import e registrazione dei 12 agenti e di Giove...
%VELORA_PY% -c "import velora_agent_network as n; import velora_portal_sessions as p; assert len(n.AGENTS)==12, 'Attesi 12 specialisti'; assert n.REVIEWER_NAME=='Giove', 'Revisore Giove mancante'; assert all(n.AGENTS[k]['ready'] for k in n.AGENTS); print('OK: 12/12 agenti importabili e Giove presente. Sessioni Chrome:', ', '.join(p.PORTALS))"
if errorlevel 1 goto :errore_import

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

:errore_import
echo.
echo ==========================================================
echo   ERRORE: RETE AGENTI NON CARICABILE
echo ==========================================================
echo.
echo I file sono stati scaricati ma Python non riesce a importare
echo tutti gli specialisti. Controlla l'errore mostrato qui sopra.
echo Se manca una libreria, esegui INSTALLA_AGENTE_VELORA.bat,
echo poi ripeti AGGIORNA_VELORA_COMPLETO.bat.
echo Non avviare i test finche non leggi OK: 12/12.
echo.
pause
exit /b 1

:errore
echo.
echo ==========================================================
echo   ERRORE DURANTE L'AGGIORNAMENTO
echo ==========================================================
echo.
echo I vecchi file sono stati salvati come .bak.
del /Q "*.py.new" 2>nul
del /Q "ota_public_source_hints.json.new" 2>nul
echo.
echo Mandami una foto di questa schermata.
echo.
pause
exit /b 1
