# 发布前检查

这个仓库设计为可公开发布，但发布前仍建议逐项检查。

## 本地检查

```powershell
git status --ignored --short
rg -n "Cookie|Set-Cookie|Authorization|Bearer|password|C:\\Users|chrome-profile|config.local" .
Get-ChildItem -Recurse .\srt -Filter *.srt | Measure-Object
powershell -NoProfile -ExecutionPolicy Bypass -File .\go.ps1 -Check
```

允许 README 中出现示例路径；不应出现真实 Cookie、Token、浏览器 profile、个人用户名或本机绝对工程路径。

## 创建 GitHub public 仓库

如果安装了 GitHub CLI：

```powershell
gh auth login
gh repo create "UESTC入党积极分子快速且深度学习指南——基于Selenium与Whisper的自动观看和自动转写脚本" --public --source . --remote origin --push
```

如果 GitHub 拒绝中文或长仓库名，建议使用短 slug：

```text
uestc-dxpx-jjfz-auto-study-transcribe
```

然后把中文标题保留在 README 第一行和仓库描述里。

不用 GitHub CLI 时，在网页端新建 public 仓库，再执行：

```powershell
git remote add origin <你的仓库地址>
git push -u origin main
```

## v0.2.0 轻量发布包

Release 资产放在本地 `dist/`，不要提交进 Git：

```powershell
$version = "v0.2.0"
$light = "dxpx-light-study-srt-$version"
$srtOnly = "srt-only-$version"
New-Item -ItemType Directory -Force .\dist | Out-Null

Compress-Archive -Path .\README.md,.\go.ps1,.\开始使用.bat,.\setup.ps1,.\config.example.ps1,.\scripts,.\vendor,.\srt,.\assets -DestinationPath ".\dist\$light.zip" -Force
Compress-Archive -Path .\srt -DestinationPath ".\dist\$srtOnly.zip" -Force
```

如果本机有 GitHub CLI：

```powershell
git tag v0.2.0
git push origin main --tags
gh release create v0.2.0 ".\dist\dxpx-light-study-srt-v0.2.0.zip" ".\dist\srt-only-v0.2.0.zip" --title "v0.2.0 light study + SRT" --notes "Light Windows launcher, offline Selenium wheels, and 131 curated SRT files."
```
