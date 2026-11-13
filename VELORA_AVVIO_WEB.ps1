# Avvio autorizzato dell'agente Velora dal browser (Windows).
# Installazione per utente corrente, senza privilegi amministratore.
# Nessun parametro del sito diventa un comando: e' consentito solo
# il protocollo velora-agent://start che avvia il BAT fisso nella cartella.
param(
    [switch]$Register,
    [Parameter(Position = 0)][string]$Request = ""
)

$ErrorActionPreference = "Stop"

if ($Register) {
    $batch = Join-Path $PSScriptRoot "AVVIA_AGENTE_VELORA.bat"
    if (-not (Test-Path -LiteralPath $batch -PathType Leaf)) {
        throw "AVVIA_AGENTE_VELORA.bat non presente nella cartella Velora."
    }

    $handler = $MyInvocation.MyCommand.Path
    $exe = Join-Path $PSHOME "powershell.exe"
    $root = "HKCU:\Software\Classes\velora-agent"
    $commandPath = Join-Path $root "shell\open\command"
    New-Item -Path $root -Force | Out-Null
    Set-Item -Path $root -Value "URL:Velora agente locale" 
    New-ItemProperty -Path $root -Name "URL Protocol" -PropertyType String -Value "" -Force | Out-Null
    New-Item -Path $commandPath -Force | Out-Null
    $command = ('"{0}" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{1}" "%1"' -f $exe, $handler)
    Set-Item -Path $commandPath -Value $command

    if ((Get-Item -Path $commandPath).GetValue("") -ne $command) {
        throw "Non riesco a verificare la registrazione del protocollo."
    }
    Write-Host "OK: il pulsante Avvia / Collega agente di Velora ora puo' aprire la finestra Windows." -ForegroundColor Green
    exit 0
}

# Rifiuta qualsiasi altro percorso URL, argomento, opzione o comando.
if ($Request -notmatch '(?i)^velora-agent://start/?$') {
    exit 2
}

$batch = Join-Path $PSScriptRoot "AVVIA_AGENTE_VELORA.bat"
if (-not (Test-Path -LiteralPath $batch -PathType Leaf)) { exit 3 }

# Evita di aprire due CMD se il server Velora e' gia' in ascolto.
$client = $null
try {
    $client = [System.Net.Sockets.TcpClient]::new()
    $pending = $client.BeginConnect("127.0.0.1", 8768, $null, $null)
    if ($pending.AsyncWaitHandle.WaitOne(500, $false) -and $client.Connected) {
        $client.EndConnect($pending)
        exit 0
    }
} catch {
    # Nessun server su localhost: si procede all'avvio.
} finally {
    if ($null -ne $client) { $client.Dispose() }
}

# La CMD e' visibile; l'utente puo' sempre interrompere l'agente.
# Nessun dato, credential vault o archivio viene toccato.
$args = '/d /c ""' + $batch + '""'
Start-Process -FilePath $env:ComSpec -WorkingDirectory $PSScriptRoot -ArgumentList $args -WindowStyle Normal
