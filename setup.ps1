param(
    [string]$Python = "python",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$venvDir = Join-Path $repoRoot ".venv"
$pythonInVenv = Join-Path $venvDir "Scripts\python.exe"
$requirements = Join-Path $repoRoot "scripts\requirements.txt"
$wheelDir = Join-Path $repoRoot "vendor\wheels"

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
$wheelCount = 0
if (Test-Path -LiteralPath $wheelDir) {
    $wheelCount = @(Get-ChildItem -LiteralPath $wheelDir -Filter *.whl -File -ErrorAction SilentlyContinue).Count
}
if ($wheelCount -gt 0) {
    & $pythonInVenv -m pip install --no-index --find-links $wheelDir -r $requirements
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Offline wheel install failed. Falling back to online pip install."
        & $pythonInVenv -m pip install -r $requirements
    }
}
else {
    & $pythonInVenv -m pip install -r $requirements
}
if ($LASTEXITCODE -ne 0) { throw "Python dependency install failed." }

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
