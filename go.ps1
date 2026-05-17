param(
    [ValidateSet("jjfz", "fzdx")]
    [string]$Course = "jjfz",
    [string]$Python = "",
    [switch]$Check,
    [switch]$OpenSrt,
    [switch]$LoginOnly,
    [switch]$AdvancedTranscribe,
    [switch]$ForceVenv,
    [switch]$NoInstall
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Join-Path $repoRoot "scripts"
$venvDir = Join-Path $repoRoot ".venv"
$pythonInVenv = Join-Path $venvDir "Scripts\python.exe"
$requirementsPath = Join-Path $scriptsDir "requirements.txt"
$wheelDir = Join-Path $repoRoot "vendor\wheels"
$srtDir = Join-Path $repoRoot "srt"
$profileDir = Join-Path $repoRoot "chrome-profile"

Set-Location -LiteralPath $repoRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message ==" -ForegroundColor Cyan
}

function Test-RealCommand {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) { return $null }
    if ($cmd.CommandType -ne "Application") { return $null }
    if ($cmd.Source -like "*\Microsoft\WindowsApps\*") { return $null }
    return $cmd.Source
}

function Add-PythonCandidate {
    param(
        [System.Collections.ArrayList]$List,
        [string]$Exe,
        [string[]]$Args = @()
    )
    if ([string]::IsNullOrWhiteSpace($Exe)) { return }

    $source = $Exe
    if (-not (Test-Path -LiteralPath $Exe)) {
        $source = Test-RealCommand $Exe
        if (-not $source) { return }
    }
    elseif ($Exe -like "*\Microsoft\WindowsApps\*") {
        return
    }

    $key = "$source $($Args -join ' ')"
    foreach ($item in $List) {
        if ($item.Key -eq $key) { return }
    }

    [void]$List.Add([pscustomobject]@{
        Key = $key
        Exe = $source
        Args = $Args
    })
}

function Get-PythonCandidate {
    param([string]$Preferred = "")

    $candidates = New-Object System.Collections.ArrayList
    if (-not [string]::IsNullOrWhiteSpace($Preferred)) {
        Add-PythonCandidate -List $candidates -Exe $Preferred
    }

    Add-PythonCandidate -List $candidates -Exe "py" -Args @("-3")
    Add-PythonCandidate -List $candidates -Exe "python"
    Add-PythonCandidate -List $candidates -Exe "python3"

    $known = @(
        "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "$env:ProgramFiles\Python314\python.exe",
        "$env:ProgramFiles\Python313\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "$env:ProgramFiles\Python310\python.exe",
        "$env:USERPROFILE\anaconda3\python.exe",
        "$env:USERPROFILE\miniconda3\python.exe",
        "C:\ProgramData\anaconda3\python.exe",
        "C:\ProgramData\miniconda3\python.exe",
        "D:\anaconda\python.exe",
        "D:\miniconda3\python.exe"
    )
    foreach ($path in $known) {
        Add-PythonCandidate -List $candidates -Exe $path
    }

    $probe = "import sys; print(sys.executable); print('{}.{}.{}'.format(*sys.version_info[:3])); raise SystemExit(0 if sys.version_info >= (3,10) else 9)"
    foreach ($candidate in $candidates) {
        try {
            $args = @($candidate.Args) + @("-c", $probe)
            $output = & $candidate.Exe @args 2>$null
            if ($LASTEXITCODE -eq 0 -and $output.Count -ge 2) {
                return [pscustomobject]@{
                    Exe = $candidate.Exe
                    Args = $candidate.Args
                    Path = [string]$output[0]
                    Version = [string]$output[1]
                }
            }
        }
        catch {
        }
    }

    return $null
}

function Invoke-Python {
    param(
        [pscustomobject]$Candidate,
        [string[]]$Arguments
    )
    $allArgs = @($Candidate.Args) + $Arguments
    & $Candidate.Exe @allArgs
    return $LASTEXITCODE
}

function Get-ChromePath {
    $paths = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    foreach ($path in $paths) {
        if (Test-Path -LiteralPath $path) { return $path }
    }

    $cmd = Test-RealCommand "chrome.exe"
    if ($cmd) { return $cmd }

    $cmd = Test-RealCommand "chrome"
    if ($cmd) { return $cmd }

    return $null
}

function Test-PortOpen {
    param([int]$Port = 9222)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $opened = $connect.AsyncWaitHandle.WaitOne(700)
        if ($opened) { $client.EndConnect($connect) }
        return [bool]$opened
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Install-WingetPackage {
    param(
        [string]$Id,
        [string]$Name
    )

    $winget = Test-RealCommand "winget.exe"
    if (-not $winget) {
        throw "$Name was not found, and winget is not available. Install $Name manually, then run this script again."
    }

    Write-Host "Trying winget install for $Name..."
    & $winget install --id $Id -e --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget could not install $Name. Install it manually, then run this script again."
    }
}

function Ensure-Chrome {
    $chrome = Get-ChromePath
    if ($chrome) { return $chrome }
    if ($NoInstall) {
        throw "Chrome was not found. Install Google Chrome or rerun without -NoInstall."
    }

    Install-WingetPackage -Id "Google.Chrome" -Name "Google Chrome"
    $chrome = Get-ChromePath
    if (-not $chrome) {
        throw "Chrome still was not found after winget. Install Google Chrome manually, then run this script again."
    }
    return $chrome
}

function Ensure-Python {
    $candidate = Get-PythonCandidate -Preferred $Python
    if ($candidate) { return $candidate }
    if ($NoInstall) {
        throw "Python 3.10+ was not found. Install Python or rerun without -NoInstall."
    }

    Install-WingetPackage -Id "Python.Python.3.12" -Name "Python 3.12"
    $candidate = Get-PythonCandidate -Preferred $Python
    if (-not $candidate) {
        throw "Python 3.10+ still was not found after winget. Install Python manually, then run this script again."
    }
    return $candidate
}

function Ensure-Venv {
    param([pscustomobject]$PythonCandidate)

    if ((Test-Path -LiteralPath $pythonInVenv) -and -not $ForceVenv) {
        Write-Host "Using existing virtual environment: $venvDir"
    }
    else {
        Write-Host "Creating virtual environment: $venvDir"
        $args = @("-m", "venv")
        if ($ForceVenv) { $args += "--clear" }
        $args += $venvDir
        $code = Invoke-Python -Candidate $PythonCandidate -Arguments $args
        if ($code -ne 0) { throw "Failed to create virtual environment." }
    }

    if (-not (Test-Path -LiteralPath $pythonInVenv)) {
        throw "Virtual environment was not created: $pythonInVenv"
    }
}

function Install-PythonDependencies {
    if (-not (Test-Path -LiteralPath $requirementsPath)) {
        throw "Missing requirements file: $requirementsPath"
    }

    Write-Host "Checking pip..."
    & $pythonInVenv -m pip --version | Out-Host
    if ($LASTEXITCODE -ne 0) {
        & $pythonInVenv -m ensurepip --upgrade
        if ($LASTEXITCODE -ne 0) { throw "pip is not available in .venv." }
    }

    $wheelCount = 0
    if (Test-Path -LiteralPath $wheelDir) {
        $wheelCount = @(Get-ChildItem -LiteralPath $wheelDir -Filter *.whl -File -ErrorAction SilentlyContinue).Count
    }

    if ($wheelCount -gt 0) {
        Write-Host "Installing Selenium dependencies from vendor\wheels ($wheelCount wheels)..."
        & $pythonInVenv -m pip install --no-index --find-links $wheelDir -r $requirementsPath
        if ($LASTEXITCODE -eq 0) { return }

        Write-Warning "Offline wheel install failed. Falling back to online pip install."
    }
    else {
        Write-Warning "vendor\wheels is empty. Falling back to online pip install."
    }

    & $pythonInVenv -m pip install -r $requirementsPath
    if ($LASTEXITCODE -ne 0) { throw "Python dependency install failed." }
}

function Show-Check {
    Write-Step "Environment check"

    $chrome = Get-ChromePath
    if ($chrome) { Write-Host "Chrome: OK  $chrome" }
    else { Write-Host "Chrome: MISSING  winget install --id Google.Chrome -e --source winget" -ForegroundColor Yellow }

    $pythonCandidate = Get-PythonCandidate -Preferred $Python
    if ($pythonCandidate) { Write-Host "Python: OK  $($pythonCandidate.Version)  $($pythonCandidate.Path)" }
    else { Write-Host "Python: MISSING  winget install --id Python.Python.3.12 -e --source winget" -ForegroundColor Yellow }

    if (Test-Path -LiteralPath $pythonInVenv) {
        Write-Host ".venv: OK  $pythonInVenv"
        & $pythonInVenv -c "import selenium; print('Selenium: OK  ' + selenium.__version__)" 2>$null
        if ($LASTEXITCODE -ne 0) { Write-Host "Selenium: MISSING in .venv" -ForegroundColor Yellow }
    }
    else {
        Write-Host ".venv: MISSING  run .\go.ps1 to create it" -ForegroundColor Yellow
    }

    $wheelCount = 0
    if (Test-Path -LiteralPath $wheelDir) {
        $wheelCount = @(Get-ChildItem -LiteralPath $wheelDir -Filter *.whl -File -ErrorAction SilentlyContinue).Count
    }
    Write-Host "vendor\wheels: $wheelCount wheels"

    $srtCount = 0
    if (Test-Path -LiteralPath $srtDir) {
        $srtCount = @(Get-ChildItem -LiteralPath $srtDir -Recurse -Filter *.srt -File -ErrorAction SilentlyContinue).Count
    }
    Write-Host "srt: $srtCount files"

    if (Test-PortOpen -Port 9222) { Write-Host "Chrome debug port 9222: OPEN" }
    else { Write-Host "Chrome debug port 9222: CLOSED" }
}

function Start-LoginChrome {
    $launcher = Join-Path $scriptsDir "launch_chrome_debug.ps1"
    if (-not (Test-Path -LiteralPath $launcher)) { throw "Missing Chrome launcher: $launcher" }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -ProfileDir $profileDir
    if ($LASTEXITCODE -ne 0) { throw "Failed to launch Chrome." }
}

function Show-AdvancedTranscribe {
    Write-Step "Advanced transcription"
    Write-Host "Full transcription is kept for advanced use only. It needs video2md, ffmpeg, yt-dlp and Whisper."
    Write-Host "1. Edit config.local.ps1 with your local tool paths."
    Write-Host "2. Start login Chrome:"
    Write-Host "   powershell -ExecutionPolicy Bypass -File .\scripts\launch_chrome_debug.ps1"
    Write-Host "3. Verify one video:"
    Write-Host "   powershell -ExecutionPolicy Bypass -File .\scripts\run_dxpx_md_transcribe.ps1 -MaxVideos 1"
    Write-Host "4. Run all jjfz videos:"
    Write-Host "   powershell -ExecutionPolicy Bypass -File .\scripts\run_dxpx_md_transcribe.ps1"
}

if ($OpenSrt) {
    if (-not (Test-Path -LiteralPath $srtDir)) { throw "SRT directory was not found: $srtDir" }
    Invoke-Item -LiteralPath $srtDir
    return
}

if ($AdvancedTranscribe) {
    Show-AdvancedTranscribe
    return
}

if ($Check) {
    Show-Check
    return
}

Write-Step "Checking Chrome"
$chromePath = Ensure-Chrome
Write-Host "Chrome: $chromePath"

if ($LoginOnly) {
    Write-Step "Starting login browser"
    Start-LoginChrome
    Write-Host "Log in to https://dxpx.uestc.edu.cn/ in the opened Chrome. Keep that Chrome window open."
    return
}

Write-Step "Checking Python"
$pythonCandidate = Ensure-Python
Write-Host "Python: $($pythonCandidate.Version)  $($pythonCandidate.Path)"

Write-Step "Preparing Selenium"
Ensure-Venv -PythonCandidate $pythonCandidate
Install-PythonDependencies

Write-Step "Starting login browser"
Start-LoginChrome
Write-Host "In the opened Chrome, log in to:"
Write-Host "  https://dxpx.uestc.edu.cn/"
Write-Host "After the page shows your account/course list, come back here."
[void](Read-Host "Press Enter to start auto study")

Write-Step "Starting light auto study"
$lightRunner = Join-Path $scriptsDir "run_light_study.ps1"
if (-not (Test-Path -LiteralPath $lightRunner)) { throw "Missing light runner: $lightRunner" }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $lightRunner -Course $Course -PythonExe $pythonInVenv
exit $LASTEXITCODE
