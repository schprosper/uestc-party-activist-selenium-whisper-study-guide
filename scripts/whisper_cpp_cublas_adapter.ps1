param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$AudioPath,

    [Alias('o', 'output_dir')]
    [string]$OutputDir,

    [Alias('f', 'output_format')]
    [string[]]$OutputFormat,

    [Alias('m', 'model')]
    [string]$ModelName = "large-v3-turbo",

    [Alias('l')]
    [string]$Language = "zh",

    [switch]$standard,
    [switch]$beep_off,
    [switch]$print_progress,

    [string]$CppRoot = $env:WHISPER_CPP_ROOT,
    [string]$CppCuBlasRoot = $env:WHISPER_CPP_CUBLAS_ROOT,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($CppRoot)) {
    throw "WHISPER_CPP_ROOT is not set. Point it to the whisper.cpp directory that contains the Models folder."
}
if ([string]::IsNullOrWhiteSpace($CppCuBlasRoot)) {
    throw "WHISPER_CPP_CUBLAS_ROOT is not set. Point it to the directory that contains whisper-cli.exe."
}

$cppRoot = $CppRoot
$cppCuBlasRoot = $CppCuBlasRoot
$whisperCli = Join-Path $cppCuBlasRoot "whisper-cli.exe"

if (-not (Test-Path -LiteralPath $whisperCli)) {
    throw "whisper-cli.exe was not found: $whisperCli"
}

function Resolve-CppModel {
    param([string]$ModelName)

    if (-not [string]::IsNullOrWhiteSpace($ModelName) -and (Test-Path -LiteralPath $ModelName)) {
        return (Resolve-Path -LiteralPath $ModelName).ProviderPath
    }

    $modelDir = Join-Path $cppRoot "Models"
    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($ModelName)) {
        $candidates += @(
            (Join-Path $modelDir $ModelName),
            (Join-Path $modelDir "$ModelName.bin"),
            (Join-Path $modelDir "ggml-$ModelName.bin")
        )
    }
    $candidates += @(
        (Join-Path $modelDir "large-v3-turbo.bin"),
        (Join-Path $modelDir "tiny.bin")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).ProviderPath
        }
    }

    throw "No whisper.cpp model was found under $modelDir"
}

function Get-ValueAfter {
    param(
        [string[]]$Args,
        [string[]]$Names,
        [string]$DefaultValue = ""
    )

    for ($i = 0; $i -lt $Args.Count; $i++) {
        if ($Names -contains $Args[$i] -and $i + 1 -lt $Args.Count) {
            return $Args[$i + 1]
        }
    }
    return $DefaultValue
}

if (-not (Test-Path -LiteralPath $AudioPath)) {
    throw "Input audio file was not found: $AudioPath"
}
$audioPath = (Resolve-Path -LiteralPath $AudioPath).ProviderPath

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Split-Path -Parent $audioPath
}
$outputDir = $OutputDir
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

if ([string]::IsNullOrWhiteSpace($Language) -or $Language -eq "auto") {
    $Language = "auto"
}
$modelPath = Resolve-CppModel -ModelName $ModelName
$baseName = [System.IO.Path]::GetFileNameWithoutExtension($audioPath)
$outputBase = Join-Path $outputDir $baseName

$cppArgs = @(
    "-m", $modelPath,
    "-f", $audioPath,
    "-l", $Language,
    "-otxt",
    "-osrt",
    "-oj",
    "-pp",
    "-of", $outputBase
)

Push-Location $cppCuBlasRoot
try {
    & $whisperCli @cppArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
