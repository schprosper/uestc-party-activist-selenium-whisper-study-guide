param(
    [switch]$NoTranscribe,
    [string]$TranscriptModel = "medium",
    [string]$TranscriptLanguage = "zh",
    [string]$PythonExe,
    [string]$CondaExe,
    [string]$CondaEnv = "dxpx_auto_play",
    [string]$OutputRoot,
    [string]$RunName
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $repoRoot "config.local.ps1"
if (Test-Path -LiteralPath $configPath) {
    . $configPath
}

if ([string]::IsNullOrWhiteSpace($PythonExe)) { $PythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe" }
if ([string]::IsNullOrWhiteSpace($CondaExe)) { $CondaExe = $env:CONDA_EXE }
if ([string]::IsNullOrWhiteSpace($OutputRoot)) { $OutputRoot = Join-Path $repoRoot "output\dxpx_notes" }
if ([string]::IsNullOrWhiteSpace($RunName)) { $RunName = "积极分子_自动播放转写" }

$client = New-Object System.Net.Sockets.TcpClient
try {
    $connect = $client.BeginConnect("127.0.0.1", 9222, $null, $null)
    $portOpen = $connect.AsyncWaitHandle.WaitOne(1000)
    if ($portOpen) { $client.EndConnect($connect) }
} catch {
    $portOpen = $false
} finally {
    $client.Close()
}

if (-not $portOpen) {
    throw "Chrome debug port 9222 is not open. Run .\launch_chrome_debug.ps1 first, then log in."
}

Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUNBUFFERED = "1"
$env:DXPX_TRANSCRIBE = if ($NoTranscribe) { "0" } else { "1" }
$env:DXPX_TRANSCRIBE_MODEL = $TranscriptModel
$env:DXPX_TRANSCRIBE_LANGUAGE = $TranscriptLanguage
$env:DXPX_TRANSCRIBE_OUTPUT = $OutputRoot
$env:DXPX_TRANSCRIBE_RUN_NAME = $RunName
if ($env:VIDEO2MD_SCRIPT) { $env:DXPX_TRANSCRIBE_VIDEO2MD_SCRIPT = $env:VIDEO2MD_SCRIPT }
if ($env:FFMPEG_PATH) { $env:DXPX_TRANSCRIBE_FFMPEG_EXE = $env:FFMPEG_PATH }
if ($env:WHISPER_EXE_PATH) { $env:DXPX_TRANSCRIBE_WHISPER_EXE = $env:WHISPER_EXE_PATH }
if ($env:YTDLP_PATH) { $env:DXPX_TRANSCRIBE_YT_DLP = $env:YTDLP_PATH }

if (Test-Path -LiteralPath $PythonExe) {
    Write-Host "Starting jjfz.py with venv Python..."
    & $PythonExe -u .\jjfz.py
    exit $LASTEXITCODE
}

if (-not [string]::IsNullOrWhiteSpace($CondaExe) -and (Test-Path -LiteralPath $CondaExe)) {
    Write-Host "Starting jjfz.py with conda env $CondaEnv..."
    & $CondaExe run --no-capture-output -n $CondaEnv python -u .\jjfz.py
    exit $LASTEXITCODE
}

throw "Python runtime was not found. Run ..\setup.ps1 first, or pass -PythonExe / -CondaExe."
