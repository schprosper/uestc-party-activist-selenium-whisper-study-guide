$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$repoRoot = Split-Path -Parent $PSScriptRoot
$goScript = Join-Path $repoRoot "go.ps1"
$srtDir = Join-Path $repoRoot "srt"

function New-PointF {
    param([float]$X, [float]$Y)
    return (New-Object System.Drawing.PointF -ArgumentList $X, $Y)
}

function New-RoundedRectPath {
    param(
        [float]$X,
        [float]$Y,
        [float]$Width,
        [float]$Height,
        [float]$Radius
    )
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = $Radius * 2
    $path.AddArc($X, $Y, $d, $d, 180, 90)
    $path.AddArc($X + $Width - $d, $Y, $d, $d, 270, 90)
    $path.AddArc($X + $Width - $d, $Y + $Height - $d, $d, $d, 0, 90)
    $path.AddArc($X, $Y + $Height - $d, $d, $d, 90, 90)
    $path.CloseFigure()
    return $path
}

function New-LauncherBitmap {
    param(
        [int]$Width = 240,
        [int]$Height = 240
    )

    $bmp = New-Object System.Drawing.Bitmap -ArgumentList $Width, $Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::FromArgb(42, 36, 36))

    $scaleX = $Width / 240.0
    $scaleY = $Height / 240.0
    $g.ScaleTransform($scaleX, $scaleY)

    $gold = [System.Drawing.Color]::FromArgb(255, 181, 75)
    $soft = [System.Drawing.Color]::FromArgb(220, 207, 221)
    $skin = [System.Drawing.Color]::FromArgb(238, 180, 176)
    $line = [System.Drawing.Color]::FromArgb(8, 8, 10)
    $cloth = [System.Drawing.Color]::FromArgb(51, 49, 62)

    $blackBrush = New-Object System.Drawing.SolidBrush -ArgumentList ([System.Drawing.Color]::FromArgb(5, 5, 7))
    $clothBrush = New-Object System.Drawing.SolidBrush -ArgumentList $cloth
    $skinBrush = New-Object System.Drawing.SolidBrush -ArgumentList $skin
    $goldBrush = New-Object System.Drawing.SolidBrush -ArgumentList $gold
    $softBrush = New-Object System.Drawing.SolidBrush -ArgumentList $soft
    $linePen = New-Object System.Drawing.Pen -ArgumentList $line, 4
    $goldPen = New-Object System.Drawing.Pen -ArgumentList $gold, 4
    $thinGoldPen = New-Object System.Drawing.Pen -ArgumentList $gold, 2

    $g.FillEllipse($softBrush, 14, 25, 66, 62)
    $g.FillEllipse($blackBrush, 48, 20, 104, 74)

    $hair = New-Object System.Drawing.Drawing2D.GraphicsPath
    $hair.AddPolygon([System.Drawing.PointF[]]@(
        (New-PointF 62 72),
        (New-PointF 152 67),
        (New-PointF 147 153),
        (New-PointF 126 135),
        (New-PointF 111 166),
        (New-PointF 93 137),
        (New-PointF 73 160),
        (New-PointF 70 120)
    ))
    $g.FillPath($blackBrush, $hair)

    $g.FillEllipse($skinBrush, 76, 85, 72, 70)
    $g.DrawArc($linePen, 76, 85, 72, 70, 185, 175)

    $grayEyeBrush = New-Object System.Drawing.SolidBrush -ArgumentList ([System.Drawing.Color]::FromArgb(176, 180, 190))
    $g.FillEllipse($grayEyeBrush, 95, 116, 17, 10)
    $g.FillEllipse($goldBrush, 128, 112, 14, 17)
    $g.FillEllipse($linePen.Brush, 133, 116, 5, 8)

    $g.FillRectangle($blackBrush, 78, 43, 113, 33)
    $g.DrawLine($goldPen, 92, 76, 183, 76)
    $g.DrawLine($thinGoldPen, 145, 78, 180, 113)

    $lens1 = New-RoundedRectPath -X 98 -Y 45 -Width 41 -Height 35 -Radius 8
    $lens2 = New-RoundedRectPath -X 145 -Y 45 -Width 39 -Height 35 -Radius 8
    $lensBrush = New-Object System.Drawing.SolidBrush -ArgumentList ([System.Drawing.Color]::FromArgb(17, 18, 23))
    $g.FillPath($lensBrush, $lens1)
    $g.FillPath($lensBrush, $lens2)
    $g.FillPolygon($goldBrush, [System.Drawing.PointF[]]@(
        (New-PointF 112 52),
        (New-PointF 132 50),
        (New-PointF 132 73),
        (New-PointF 110 73)
    ))
    $g.DrawPath($linePen, $lens1)
    $g.DrawPath($linePen, $lens2)
    $g.DrawLine($linePen, 139, 61, 146, 61)

    $g.FillPolygon($clothBrush, [System.Drawing.PointF[]]@(
        (New-PointF 54 212),
        (New-PointF 87 156),
        (New-PointF 147 154),
        (New-PointF 201 212)
    ))
    $g.DrawLine($goldPen, 59, 205, 91, 158)
    $g.DrawLine($goldPen, 149, 157, 197, 205)
    $g.DrawLine($linePen, 88, 162, 147, 162)

    $g.DrawArc($linePen, 174, 35, 42, 56, 190, 120)
    $g.DrawLine($linePen, 191, 79, 202, 142)
    $g.DrawLine($goldPen, 198, 138, 215, 199)

    $g.ResetTransform()
    $g.Dispose()
    return $bmp
}

function Get-LauncherImage {
    $assetDir = Join-Path $repoRoot "assets"
    $candidates = @(
        (Join-Path $assetDir "launcher-icon.png"),
        (Join-Path $assetDir "launcher-icon.jpg"),
        (Join-Path $assetDir "launcher-icon.jpeg"),
        (Join-Path $assetDir "launcher-icon.bmp")
    )

    foreach ($path in $candidates) {
        if (Test-Path -LiteralPath $path) {
            return [System.Drawing.Image]::FromFile($path)
        }
    }

    return New-LauncherBitmap -Width 260 -Height 260
}

function Start-GoConsole {
    param([string[]]$Args)
    $argList = @("-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $goScript) + $Args
    Start-Process -FilePath "powershell.exe" -ArgumentList $argList -WorkingDirectory $repoRoot
}

function New-Button {
    param(
        [string]$Text,
        [int]$X,
        [int]$Y,
        [int]$Width,
        [int]$Height
    )
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $Text
    $button.SetBounds($X, $Y, $Width, $Height)
    $button.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $button.FlatAppearance.BorderSize = 1
    $button.FlatAppearance.BorderColor = [System.Drawing.Color]::FromArgb(255, 181, 75)
    $button.BackColor = [System.Drawing.Color]::FromArgb(255, 181, 75)
    $button.ForeColor = [System.Drawing.Color]::FromArgb(24, 22, 24)
    $button.Font = New-Object System.Drawing.Font -ArgumentList "Microsoft YaHei UI", 10, ([System.Drawing.FontStyle]::Bold)
    $button.Cursor = [System.Windows.Forms.Cursors]::Hand
    return $button
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "DXPX 轻量刷课"
$form.StartPosition = "CenterScreen"
$form.ClientSize = New-Object System.Drawing.Size -ArgumentList 680, 360
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedSingle
$form.MaximizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(42, 36, 36)

$displayImage = Get-LauncherImage
$iconBmp = New-LauncherBitmap -Width 64 -Height 64
$form.Icon = [System.Drawing.Icon]::FromHandle($iconBmp.GetHicon())

$picture = New-Object System.Windows.Forms.PictureBox
$picture.SetBounds(24, 42, 260, 260)
$picture.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
$picture.Image = $displayImage
$picture.BackColor = [System.Drawing.Color]::FromArgb(42, 36, 36)
$form.Controls.Add($picture)

$title = New-Object System.Windows.Forms.Label
$title.Text = "入党积极分子"
$title.SetBounds(322, 36, 320, 36)
$title.ForeColor = [System.Drawing.Color]::FromArgb(255, 230, 188)
$title.BackColor = $form.BackColor
$title.Font = New-Object System.Drawing.Font -ArgumentList "Microsoft YaHei UI", 18, ([System.Drawing.FontStyle]::Bold)
$form.Controls.Add($title)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Text = "轻量刷课 + 现成 SRT"
$subtitle.SetBounds(324, 78, 320, 28)
$subtitle.ForeColor = [System.Drawing.Color]::FromArgb(195, 184, 184)
$subtitle.BackColor = $form.BackColor
$subtitle.Font = New-Object System.Drawing.Font -ArgumentList "Microsoft YaHei UI", 10
$form.Controls.Add($subtitle)

$status = New-Object System.Windows.Forms.Label
$status.Text = "请选择操作"
$status.SetBounds(324, 300, 320, 28)
$status.ForeColor = [System.Drawing.Color]::FromArgb(195, 184, 184)
$status.BackColor = $form.BackColor
$status.Font = New-Object System.Drawing.Font -ArgumentList "Microsoft YaHei UI", 9
$form.Controls.Add($status)

$btnStart = New-Button -Text "开始刷积极分子" -X 324 -Y 122 -Width 276 -Height 42
$btnSrt = New-Button -Text "打开 SRT 字幕" -X 324 -Y 174 -Width 132 -Height 38
$btnLogin = New-Button -Text "只启动登录浏览器" -X 468 -Y 174 -Width 132 -Height 38
$btnCheck = New-Button -Text "检查环境" -X 324 -Y 224 -Width 132 -Height 38
$btnAdvanced = New-Button -Text "高级转写入口" -X 468 -Y 224 -Width 132 -Height 38

$btnStart.Add_Click({
    $status.Text = "已打开刷课窗口"
    Start-GoConsole -Args @("-Course", "jjfz")
})

$btnSrt.Add_Click({
    if (Test-Path -LiteralPath $srtDir) {
        Invoke-Item -LiteralPath $srtDir
        $status.Text = "已打开字幕目录"
    }
    else {
        [System.Windows.Forms.MessageBox]::Show("找不到 srt 目录。", "DXPX 轻量刷课", "OK", "Warning") | Out-Null
    }
})

$btnLogin.Add_Click({
    $status.Text = "已打开登录浏览器窗口"
    Start-GoConsole -Args @("-LoginOnly")
})

$btnCheck.Add_Click({
    $status.Text = "已打开环境检查窗口"
    Start-GoConsole -Args @("-Check")
})

$btnAdvanced.Add_Click({
    $status.Text = "已打开高级转写入口"
    Start-GoConsole -Args @("-AdvancedTranscribe")
})

$form.Controls.AddRange(@($btnStart, $btnSrt, $btnLogin, $btnCheck, $btnAdvanced))

[void]$form.ShowDialog()
