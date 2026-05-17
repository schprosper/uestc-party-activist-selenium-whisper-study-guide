param(
    [ValidateSet("jjfz", "fzdx", "both")]
    [string]$Course = "jjfz",
    [int]$Port = 9222,
    [int]$MaxVideos = 0,
    [double]$SniffTimeout = 12,
    [double]$TriggerWait = 2,
    [int]$LoginTimeout = 600,
    [int]$TranscribeTimeout = 14400,
    [string]$OutputRoot,
    [string]$WorkRoot,
    [string]$RunName,
    [string]$TranscriptModel = "medium",
    [string]$TranscriptLanguage = "zh",
    [string]$Url = "https://dxpx.uestc.edu.cn/",
    [string]$ProfileDir,
    [string]$TranscribeScript,
    [string]$Video2MdScript,
    [string]$YtDlpPath,
    [string]$WhisperExePath,
    [string]$FfmpegPath,
    [string]$PythonExe,
    [string]$CondaExe,
    [string]$CondaEnv = "dxpx_auto_play",
    [switch]$Force,
    [switch]$KeepWork,
    [switch]$NoAutoDownloadYtDlp,
    [switch]$NoRefreshOnMiss,
    [switch]$NoResume
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $repoRoot "config.local.ps1"
if (Test-Path -LiteralPath $configPath) {
    . $configPath
}

if ([string]::IsNullOrWhiteSpace($OutputRoot)) { $OutputRoot = Join-Path $repoRoot "output\dxpx_notes" }
if ([string]::IsNullOrWhiteSpace($WorkRoot)) { $WorkRoot = Join-Path $repoRoot ".tmp\dxpx_md_auto_transcribe" }
if ([string]::IsNullOrWhiteSpace($ProfileDir)) { $ProfileDir = Join-Path $repoRoot "chrome-profile" }
if ([string]::IsNullOrWhiteSpace($TranscribeScript)) { $TranscribeScript = Join-Path $PSScriptRoot "dxpx_transcribe.ps1" }
if ([string]::IsNullOrWhiteSpace($Video2MdScript)) { $Video2MdScript = $env:VIDEO2MD_SCRIPT }
if ([string]::IsNullOrWhiteSpace($YtDlpPath)) { $YtDlpPath = $env:YTDLP_PATH }
if ([string]::IsNullOrWhiteSpace($WhisperExePath)) {
    if ($env:WHISPER_EXE_PATH) { $WhisperExePath = $env:WHISPER_EXE_PATH }
    else { $WhisperExePath = Join-Path $PSScriptRoot "whisper_cpp_cublas_adapter.ps1" }
}
if ([string]::IsNullOrWhiteSpace($FfmpegPath)) { $FfmpegPath = $env:FFMPEG_PATH }
if ([string]::IsNullOrWhiteSpace($PythonExe)) { $PythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe" }
if ([string]::IsNullOrWhiteSpace($CondaExe)) { $CondaExe = $env:CONDA_EXE }

function Test-PortOpen {
    param(
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][int]$PortNumber,
        [int]$TimeoutMilliseconds = 1000
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.BeginConnect($HostName, $PortNumber, $null, $null)
        $open = $connect.AsyncWaitHandle.WaitOne($TimeoutMilliseconds)
        if ($open) {
            $client.EndConnect($connect)
        }
        return $open
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Wait-PortOpen {
    param(
        [Parameter(Mandatory = $true)][int]$PortNumber,
        [int]$TimeoutSeconds = 20
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortOpen -HostName "127.0.0.1" -PortNumber $PortNumber -TimeoutMilliseconds 500) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Get-ChromePath {
    $chromeCandidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    $chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $chrome) {
        throw "Chrome was not found. Install Chrome or add chrome.exe to PATH."
    }
    return $chrome
}

function Get-DxpxConflictingProcess {
    $patterns = @(
        "run_jjfz.ps1",
        "run_fzdx.ps1",
        "jjfz.py",
        "fzdx.py",
        "run_dxpx_md_transcribe.ps1",
        "dxpx_md_transcriber.py"
    )
    Get-CimInstance Win32_Process | Where-Object {
        if ($_.ProcessId -eq $PID) { return $false }
        $cmd = $_.CommandLine
        if ([string]::IsNullOrWhiteSpace($cmd)) { return $false }
        foreach ($pattern in $patterns) {
            if ($cmd -like "*$pattern*") { return $true }
        }
        return $false
    }
}

$runningConflicts = @(Get-DxpxConflictingProcess)
if ($runningConflicts.Count -gt 0) {
    $runningConflicts | Select-Object ProcessId,Name,CommandLine | Format-List
    throw "Another DXPX automation script is running. Stop it before starting transcription to avoid login/session conflicts."
}

if (-not (Test-Path -LiteralPath $TranscribeScript)) {
    throw "transcribe script was not found: $TranscribeScript"
}
if ([string]::IsNullOrWhiteSpace($Video2MdScript) -or -not (Test-Path -LiteralPath $Video2MdScript)) {
    throw "video2md script was not found. Set `$env:VIDEO2MD_SCRIPT or edit config.local.ps1. Current value: $Video2MdScript"
}
if (-not [string]::IsNullOrWhiteSpace($YtDlpPath) -and -not (Test-Path -LiteralPath $YtDlpPath)) {
    throw "yt-dlp was not found: $YtDlpPath"
}
if (-not [string]::IsNullOrWhiteSpace($FfmpegPath) -and -not (Test-Path -LiteralPath $FfmpegPath)) {
    throw "ffmpeg was not found: $FfmpegPath"
}

if (-not (Test-PortOpen -HostName "127.0.0.1" -PortNumber $Port -TimeoutMilliseconds 1000)) {
    $chrome = Get-ChromePath
    New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null
    $chromeArgs = @(
        "--remote-debugging-port=$Port",
        "--user-data-dir=$ProfileDir",
        "--no-first-run",
        $Url
    )

    Start-Process -FilePath $chrome -ArgumentList $chromeArgs
    Write-Host "Started debug Chrome at 127.0.0.1:$Port"
    Write-Host "If login is required, complete it in that Chrome window. The script will wait."

    if (-not (Wait-PortOpen -PortNumber $Port -TimeoutSeconds 20)) {
        throw "Chrome debug port 127.0.0.1:$Port did not open."
    }
}
else {
    Write-Host "Debug Chrome already appears to be listening at 127.0.0.1:$Port"
}

Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUNBUFFERED = "1"

$appArgs = @(
    "-u",
    ".\dxpx_md_transcriber.py",
    "--course", $Course,
    "--port", [string]$Port,
    "--max-videos", [string]$MaxVideos,
    "--output-root", $OutputRoot,
    "--work-root", $WorkRoot,
    "--transcribe-script", $TranscribeScript,
    "--video2md-script", $Video2MdScript,
    "--language", $TranscriptLanguage,
    "--model", $TranscriptModel,
    "--sniff-timeout", [string]$SniffTimeout,
    "--trigger-wait", [string]$TriggerWait,
    "--login-timeout", [string]$LoginTimeout,
    "--transcribe-timeout", [string]$TranscribeTimeout
)

if (-not [string]::IsNullOrWhiteSpace($RunName)) { $appArgs += @("--run-name", $RunName) }
if (-not [string]::IsNullOrWhiteSpace($YtDlpPath)) { $appArgs += @("--yt-dlp", $YtDlpPath) }
if (-not [string]::IsNullOrWhiteSpace($WhisperExePath)) { $appArgs += @("--whisper-exe", $WhisperExePath) }
if (-not [string]::IsNullOrWhiteSpace($FfmpegPath)) { $appArgs += @("--ffmpeg-path", $FfmpegPath) }
if ($Force) { $appArgs += "--force" }
if ($KeepWork) { $appArgs += "--keep-work" }
if ($NoAutoDownloadYtDlp) { $appArgs += "--no-auto-download-ytdlp" }
if ($NoRefreshOnMiss) { $appArgs += "--no-refresh-on-miss" }
if ($NoResume) { $appArgs += "--no-resume" }

if (Test-Path -LiteralPath $PythonExe) {
    Write-Host "Starting DXPX Markdown transcriber with venv Python..."
    & $PythonExe @appArgs
    exit $LASTEXITCODE
}

if (-not [string]::IsNullOrWhiteSpace($CondaExe) -and (Test-Path -LiteralPath $CondaExe)) {
    Write-Host "Starting DXPX Markdown transcriber with conda env $CondaEnv..."
    & $CondaExe run --no-capture-output -n $CondaEnv python @appArgs
    exit $LASTEXITCODE
}

throw "Python runtime was not found. Run .\setup.ps1 first, or pass -PythonExe / -CondaExe."
