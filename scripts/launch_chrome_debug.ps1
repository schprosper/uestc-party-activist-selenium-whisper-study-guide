param(
    [string]$Url = "https://dxpx.uestc.edu.cn/",
    [int]$Port = 9222,
    [string]$ProfileDir = (Join-Path (Split-Path -Parent $PSScriptRoot) "chrome-profile")
)

$ErrorActionPreference = "Stop"

$chromeCandidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)

$chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chrome) {
    throw "Chrome was not found. Install Chrome or add chrome.exe to PATH."
}

New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null

$args = @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=$ProfileDir",
    "--no-first-run",
    $Url
)

Start-Process -FilePath $chrome -ArgumentList $args
Write-Host "Started debug Chrome at 127.0.0.1:$Port"
Write-Host "Log in to dxpx.uestc.edu.cn in that Chrome window, then run run_fzdx.ps1 or run_jjfz.ps1."
