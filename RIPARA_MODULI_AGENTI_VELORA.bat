@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Velora - Ripara i moduli dei 12 agenti
echo.
echo ========================================================
echo   VELORA - RIPARAZIONE MODULI AGENTI
echo ========================================================
echo.
if not exist "local_audit_server.py" (
  echo ERRORE: questo BAT deve stare nella cartella con local_audit_server.py.
  pause
  exit /b 1
)
echo Chiudi prima la finestra CMD dell'agente Velora con Ctrl+C.
pause
echo.
echo [1/3] Scarico ESCLUSIVAMENTE i due moduli mancanti...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $base='https://raw.githubusercontent.com/DiegoBH26/velora-autovalutazione/main/'; foreach($f in @('velora_agent_network.py','velora_portal_sessions.py')) { $out=$f+'.new'; Invoke-WebRequest -UseBasicParsing -Uri ($base+$f+'?nocache='+[guid]::NewGuid()) -OutFile $out; if((Get-Item $out).Length -lt 1500){throw ('File troppo piccolo: '+$f)}; Write-Host ('Scaricato: '+$f) }; if(-not (Select-String -Path 'velora_agent_network.py.new' -Pattern 'NETWORK_SCHEMA' -Quiet)){throw 'Modulo agenti non valido'}; if(-not (Select-String -Path 'velora_portal_sessions.py.new' -Pattern 'ManualPortalSessions' -Quiet)){throw 'Modulo sessioni non valido'}"
if errorlevel 1 goto errore
echo.
echo [2/3] Salvo copie di sicurezza e installo i moduli...
for %%F in (velora_agent_network.py velora_portal_sessions.py) do (
  if exist "%%F" copy /Y "%%F" "%%F.bak" >nul
  move /Y "%%F.new" "%%F" >nul
  if errorlevel 1 goto errore
)
if exist "__pycache__" (
  del /Q "__pycache__\velora_agent_network*.pyc" 2>nul
  del /Q "__pycache__\velora_portal_sessions*.pyc" 2>nul
)
echo.
echo [3/3] Verifico importazione reale dei 12 agenti, di Giove e delle sessioni...
if exist ".venv\Scripts\python.exe" goto verifica_venv
where py >nul 2>nul
if not errorlevel 1 goto verifica_py
where python >nul 2>nul
if not errorlevel 1 goto verifica_python
echo ERRORE: Python non disponibile. Esegui INSTALLA_AGENTE_VELORA.bat.
goto errore
:verifica_venv
".venv\Scripts\python.exe" -c "import velora_agent_network as n; import velora_portal_sessions as p; assert len(n.AGENTS)==12; assert n.REVIEWER_NAME=='Giove'; assert set(p.PORTALS)=={'expedia','vrbo','holidu'}; print('OK: 12/12 agenti, Giove, Expedia, Vrbo e Holidu caricati')"
if errorlevel 1 goto errore
goto successo
:verifica_py
py -3 -c "import velora_agent_network as n; import velora_portal_sessions as p; assert len(n.AGENTS)==12; assert n.REVIEWER_NAME=='Giove'; assert set(p.PORTALS)=={'expedia','vrbo','holidu'}; print('OK: 12/12 agenti, Giove, Expedia, Vrbo e Holidu caricati')"
if errorlevel 1 goto errore
goto successo
:verifica_python
python -c "import velora_agent_network as n; import velora_portal_sessions as p; assert len(n.AGENTS)==12; assert n.REVIEWER_NAME=='Giove'; assert set(p.PORTALS)=={'expedia','vrbo','holidu'}; print('OK: 12/12 agenti, Giove, Expedia, Vrbo e Holidu caricati')"
if errorlevel 1 goto errore
goto successo
:successo
echo.
echo ========================================================
echo   RIPARAZIONE COMPLETATA
echo   Avvia AVVIA_AGENTE_VELORA.bat e verifica 12/12.
echo ========================================================
echo.
pause
exit /b 0
:errore
echo.
echo ========================================================
echo   RIPARAZIONE NON RIUSCITA
echo   NON avviare ancora i test Expedia.
echo   Leggi o fotografa il messaggio di errore qui sopra.
echo ========================================================
echo.
pause
exit /b 1
