[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$M3u8Url,

    [string]$CourseTitle = 'DXPX',
    [string]$VideoTitle,
    [string]$PageUrl,
    [string]$Referer,
    [string]$UserAgent,
    [string]$CookieHeader,
    [string[]]$AddHeader,
    [int]$Index = 0,
    [string]$Duration,
    [string]$RunName,
    [string]$OutputRoot,
    [string]$WorkRoot,
    [string]$Video2MdScript,
    [string]$Language = 'zh',
    [string]$Model = 'medium',
    [string]$SubtitleEditShortcut,
    [string]$WhisperExePath,
    [string]$FfmpegPath,
    [string]$YtDlpPath,
    [switch]$NoAutoDownloadYtDlp,
    [switch]$KeepWork,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $repoRoot 'config.local.ps1'
if (Test-Path -LiteralPath $configPath) {
    . $configPath
}

if ([string]::IsNullOrWhiteSpace($OutputRoot)) { $OutputRoot = Join-Path $repoRoot 'output\dxpx_notes' }
if ([string]::IsNullOrWhiteSpace($WorkRoot)) { $WorkRoot = Join-Path $repoRoot '.tmp\dxpx_auto_play_transcribe' }
if ([string]::IsNullOrWhiteSpace($Video2MdScript)) { $Video2MdScript = $env:VIDEO2MD_SCRIPT }
if ([string]::IsNullOrWhiteSpace($WhisperExePath)) {
    if ($env:WHISPER_EXE_PATH) { $WhisperExePath = $env:WHISPER_EXE_PATH }
    else { $WhisperExePath = Join-Path $PSScriptRoot 'whisper_cpp_cublas_adapter.ps1' }
}
if ([string]::IsNullOrWhiteSpace($FfmpegPath)) { $FfmpegPath = $env:FFMPEG_PATH }
if ([string]::IsNullOrWhiteSpace($YtDlpPath)) { $YtDlpPath = $env:YTDLP_PATH }

function Ensure-Directory {
    param([Parameter(Mandatory = $true)][string]$Path)
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function New-SafePathName {
    param(
        [string]$Text,
        [string]$Default = 'untitled',
        [int]$MaxLength = 80
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        $Text = $Default
    }

    $invalid = [Regex]::Escape((-join [System.IO.Path]::GetInvalidFileNameChars()))
    $safe = $Text -replace "[$invalid]", '_'
    $safe = $safe -replace '\s+', '_'
    $safe = $safe.Trim(' ', '.', '_')
    if ($safe.Length -gt $MaxLength) {
        $safe = $safe.Substring(0, $MaxLength).Trim(' ', '.', '_')
    }
    if ([string]::IsNullOrWhiteSpace($safe)) {
        $safe = $Default
    }
    return $safe
}

function Remove-SafeDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $resolvedRoot = (Resolve-Path -LiteralPath $Root).ProviderPath.TrimEnd('\')
    $resolvedPath = (Resolve-Path -LiteralPath $Path).ProviderPath.TrimEnd('\')
    $expectedPrefix = $resolvedRoot + '\'
    if (-not $resolvedPath.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove directory outside work root: $resolvedPath"
    }

    Remove-Item -LiteralPath $resolvedPath -Recurse -Force
}

function Write-Log {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [string]$Level = 'INFO'
    )

    $line = '[{0}] [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Add-Content -LiteralPath $script:TranscribeLog -Value $line -Encoding UTF8
    Write-Host $line
}

function Write-Meta {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [string]$ErrorMessage,
        [string]$MarkdownPath,
        [string]$SubtitlePath
    )

    $meta = [ordered]@{
        courseTitle = $CourseTitle
        videoTitle = $VideoTitle
        pageUrl = $PageUrl
        m3u8Url = $M3u8Url
        duration = $Duration
        index = $Index
        status = $Status
        startedAt = $script:StartedAt
        updatedAt = (Get-Date).ToString('s')
        outputDirectory = $script:VideoDir
        markdownPath = $MarkdownPath
        subtitlePath = $SubtitlePath
        errorMessage = $ErrorMessage
    }

    $meta | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $script:MetaPath -Encoding UTF8
}

function Get-LatestFile {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [Parameter(Mandatory = $true)][string]$Filter
    )

    Get-ChildItem -LiteralPath $Directory -Filter $Filter -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

if (-not (Test-Path -LiteralPath $Video2MdScript)) {
    throw "video2md script not found: $Video2MdScript"
}

if ([string]::IsNullOrWhiteSpace($VideoTitle)) {
    $VideoTitle = 'DXPX视频'
}

Ensure-Directory -Path $OutputRoot
Ensure-Directory -Path $WorkRoot

$safeCourse = New-SafePathName -Text $CourseTitle -Default 'DXPX' -MaxLength 40
if ([string]::IsNullOrWhiteSpace($RunName)) {
    $RunName = '{0}_{1}' -f (Get-Date -Format 'yyyy-MM-dd'), $safeCourse
}
else {
    $RunName = New-SafePathName -Text $RunName -Default ('{0}_{1}' -f (Get-Date -Format 'yyyy-MM-dd'), $safeCourse) -MaxLength 80
}

$runDir = Join-Path $OutputRoot $RunName
$logDir = Join-Path $runDir 'logs'
Ensure-Directory -Path $runDir
Ensure-Directory -Path $logDir

$script:TranscribeLog = Join-Path $logDir 'transcribe.log'
$failedTasksLog = Join-Path $logDir 'failed_tasks.log'

$safeVideoTitle = New-SafePathName -Text $VideoTitle -Default 'video' -MaxLength 80
if ($Index -gt 0) {
    $videoFolder = ('{0:d3}_{1}' -f $Index, $safeVideoTitle)
}
else {
    $videoFolder = ('000_{0}' -f $safeVideoTitle)
}

$script:VideoDir = Join-Path $runDir $videoFolder
Ensure-Directory -Path $script:VideoDir

$notePath = Join-Path $script:VideoDir '笔记.md'
$subtitlePath = Join-Path $script:VideoDir '字幕.srt'
$script:MetaPath = Join-Path $script:VideoDir 'meta.json'
$script:StartedAt = (Get-Date).ToString('s')

if (-not $Force -and (Test-Path -LiteralPath $script:MetaPath)) {
    try {
        $existingMeta = Get-Content -LiteralPath $script:MetaPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $hasFinalOutput = (Test-Path -LiteralPath $notePath) -or (Test-Path -LiteralPath $subtitlePath)
        if ($hasFinalOutput -and $existingMeta.status -match '^(completed|partial_)') {
            if ([string]$existingMeta.m3u8Url -ne $M3u8Url) {
                Write-Log "已有成果存在，当前 m3u8 与 meta 不完全一致，仍按同一视频目录跳过: $VideoTitle" 'WARN'
            }
            Write-Log "跳过已完成转写: $VideoTitle"
            [PSCustomObject]@{
                Status = 'skipped_existing'
                VideoDir = $script:VideoDir
                Markdown = if (Test-Path -LiteralPath $notePath) { $notePath } else { $null }
                Subtitle = if (Test-Path -LiteralPath $subtitlePath) { $subtitlePath } else { $null }
                Meta = $script:MetaPath
            } | Format-List
            return
        }
    }
    catch {
        Write-Log "读取既有 meta 失败，将重新转写: $($_.Exception.Message)" 'WARN'
    }
}

$taskId = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), ([guid]::NewGuid().ToString('N').Substring(0, 8))
$taskWorkRoot = Join-Path $WorkRoot $taskId
$tempOutputDir = Join-Path $taskWorkRoot 'video2md-output'
$tempVideo2MdWorkRoot = Join-Path $taskWorkRoot 'video2md-work'

Ensure-Directory -Path $taskWorkRoot
Ensure-Directory -Path $tempOutputDir
Ensure-Directory -Path $tempVideo2MdWorkRoot

$status = 'running'
$finalMarkdownPath = $null
$finalSubtitlePath = $null

try {
    Write-Meta -Status $status
    Write-Log "开始转写: $VideoTitle"
    Write-Log "页面: $PageUrl"
    Write-Log "m3u8: $M3u8Url"

    $sourceForMarkdown = if ([string]::IsNullOrWhiteSpace($PageUrl)) { $M3u8Url } else { $PageUrl }
    $video2mdArgs = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $Video2MdScript,
        '-Url', $M3u8Url,
        '-Title', $VideoTitle,
        '-Source', $sourceForMarkdown,
        '-OutputDir', $tempOutputDir,
        '-WorkRoot', $tempVideo2MdWorkRoot,
        '-Language', $Language,
        '-Model', $Model
    )

    if (-not [string]::IsNullOrWhiteSpace($SubtitleEditShortcut)) {
        $video2mdArgs += @('-SubtitleEditShortcut', $SubtitleEditShortcut)
    }
    if (-not [string]::IsNullOrWhiteSpace($WhisperExePath)) {
        $video2mdArgs += @('-WhisperExePath', $WhisperExePath)
    }
    if (-not [string]::IsNullOrWhiteSpace($FfmpegPath)) {
        $video2mdArgs += @('-FfmpegPath', $FfmpegPath)
    }

    if (-not [string]::IsNullOrWhiteSpace($Referer)) {
        $video2mdArgs += @('-Referer', $Referer)
    }
    if (-not [string]::IsNullOrWhiteSpace($UserAgent)) {
        $video2mdArgs += @('-UserAgent', $UserAgent)
    }
    if (-not [string]::IsNullOrWhiteSpace($CookieHeader)) {
        $video2mdArgs += @('-CookieHeader', $CookieHeader)
    }
    foreach ($header in @($AddHeader)) {
        if (-not [string]::IsNullOrWhiteSpace($header)) {
            $video2mdArgs += @('-AddHeader', $header)
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($YtDlpPath)) {
        $video2mdArgs += @('-YtDlpPath', $YtDlpPath)
    }
    if ($NoAutoDownloadYtDlp) {
        $video2mdArgs += '-NoAutoDownloadYtDlp'
    }

    Write-Log "调用 video2md 临时输出目录: $tempOutputDir"
    & powershell @video2mdArgs 2>&1 | ForEach-Object {
        Add-Content -LiteralPath $script:TranscribeLog -Value ([string]$_) -Encoding UTF8
        Write-Host $_
    }
    if ($LASTEXITCODE -ne 0) {
        throw "video2md failed with exit code $LASTEXITCODE"
    }

    $markdown = Get-LatestFile -Directory $tempOutputDir -Filter '*.md'
    $subtitle = Get-LatestFile -Directory $tempOutputDir -Filter '*.srt'

    if ($markdown) {
        Copy-Item -LiteralPath $markdown.FullName -Destination $notePath -Force
        $finalMarkdownPath = $notePath
    }
    else {
        Write-Log 'MD 未生成，只保留 SRT。' 'WARN'
    }

    if ($subtitle) {
        Copy-Item -LiteralPath $subtitle.FullName -Destination $subtitlePath -Force
        $finalSubtitlePath = $subtitlePath
    }
    else {
        Write-Log 'SRT 未生成。' 'WARN'
    }

    if (-not $finalMarkdownPath -and -not $finalSubtitlePath) {
        throw 'video2md 未生成可保留的 md 或 srt 成果。'
    }

    if ($finalMarkdownPath -and $finalSubtitlePath) {
        $status = 'completed'
    }
    elseif ($finalSubtitlePath) {
        $status = 'partial_missing_md'
    }
    else {
        $status = 'partial_missing_srt'
    }

    Write-Meta -Status $status -MarkdownPath $finalMarkdownPath -SubtitlePath $finalSubtitlePath
    Write-Log "完成转写: $VideoTitle -> $script:VideoDir"

    [PSCustomObject]@{
        Status = $status
        VideoDir = $script:VideoDir
        Markdown = $finalMarkdownPath
        Subtitle = $finalSubtitlePath
        Meta = $script:MetaPath
    } | Format-List
}
catch {
    $status = 'failed'
    $message = $_.Exception.Message
    Write-Log "转写失败: $VideoTitle - $message" 'ERROR'
    Add-Content -LiteralPath $failedTasksLog -Value ("[{0}] {1} | {2} | {3}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $VideoTitle, $PageUrl, $message) -Encoding UTF8
    Write-Meta -Status $status -ErrorMessage $message -MarkdownPath $finalMarkdownPath -SubtitlePath $finalSubtitlePath
    throw
}
finally {
    if (-not $KeepWork) {
        try {
            Remove-SafeDirectory -Path $taskWorkRoot -Root $WorkRoot
            Write-Log "已清理临时目录: $taskWorkRoot"
        }
        catch {
            Write-Log "清理临时目录失败: $($_.Exception.Message)" 'WARN'
        }
    }
    else {
        Write-Log "保留临时目录: $taskWorkRoot"
    }
}




