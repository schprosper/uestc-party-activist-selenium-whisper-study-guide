param(
    [ValidateSet("jjfz", "fzdx")]
    [string]$Course = "jjfz",
    [string]$PythonExe,
    [string]$OutputRoot,
    [string]$RunName
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $PythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python runtime was not found: $PythonExe. Run ..\go.ps1 first."
}

$runner = Join-Path $PSScriptRoot ("run_{0}.ps1" -f $Course)
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Course runner was not found: $runner"
}

$args = @("-NoTranscribe", "-PythonExe", $PythonExe)
if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
    $args += @("-OutputRoot", $OutputRoot)
}
if (-not [string]::IsNullOrWhiteSpace($RunName)) {
    $args += @("-RunName", $RunName)
}

Write-Host "Light mode: course=$Course, transcription=off"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runner @args
exit $LASTEXITCODE
