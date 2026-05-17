param(
    [string]$Python = "python",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$venvDir = Join-Path $repoRoot ".venv"
$pythonInVenv = Join-Path $venvDir "Scripts\python.exe"
$requirements = Join-Path $repoRoot "scripts\requirements.txt"

if ((Test-Path -LiteralPath $pythonInVenv) -and -not $Force) {
    Write-Host "Using existing virtual environment: $venvDir"
}
else {
    Write-Host "Creating virtual environment: $venvDir"
    & $Python -m venv $venvDir
}

if (-not (Test-Path -LiteralPath $pythonInVenv)) {
    throw "Virtual environment was not created: $pythonInVenv"
}

Write-Host "Installing Python dependencies..."
& $pythonInVenv -m pip install --upgrade pip
& $pythonInVenv -m pip install -r $requirements

$config = Join-Path $repoRoot "config.local.ps1"
$configExample = Join-Path $repoRoot "config.example.ps1"
if (-not (Test-Path -LiteralPath $config) -and (Test-Path -LiteralPath $configExample)) {
    Copy-Item -LiteralPath $configExample -Destination $config
    Write-Host "Created config.local.ps1 from config.example.ps1. Edit it before full transcription."
}

Write-Host ""
Write-Host "Base deployment is ready."
Write-Host "Next:"
Write-Host "  1. Edit config.local.ps1 and set VIDEO2MD_SCRIPT / FFMPEG_PATH / Whisper paths."
Write-Host "  2. Run: powershell -ExecutionPolicy Bypass -File .\scripts\launch_chrome_debug.ps1"
Write-Host "  3. Log in to https://dxpx.uestc.edu.cn/ in the opened Chrome."
Write-Host "  4. Test one item: powershell -ExecutionPolicy Bypass -File .\scripts\run_dxpx_md_transcribe.ps1 -MaxVideos 1"
