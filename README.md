# 方案三：轻量部署，只自动刷课 + 现成 SRT

普通 Windows 用户按这个走就够了：脚本自动准备 Selenium，启动一个独立 Chrome，你手动登录学校平台，然后脚本自动刷“入党积极分子”课程。字幕已经整理好，直接打开 `srt/` 就能拿到 131 个 SRT。

1. 下载或克隆本仓库。
2. 在仓库目录运行：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\go.ps1
   ```

3. 弹出 Chrome 后登录：

   ```text
   https://dxpx.uestc.edu.cn/
   ```

4. 登录完成后回到 PowerShell 窗口，按提示继续。
5. 需要字幕就打开：

   ```text
   srt/
   ```

轻量版不做新视频转写，不需要安装 Whisper、ffmpeg、yt-dlp 或 video2md。缺 Python 或 Chrome 时，脚本会优先尝试用 `winget` 自动安装；失败时会给出明确提示。

## 三种入口

不装 Git，直接下载 Release：

```powershell
Invoke-WebRequest -Uri "https://github.com/schprosper/uestc-party-activist-selenium-whisper-study-guide/releases/latest/download/dxpx-light-study-srt-v0.2.0.zip" -OutFile ".\dxpx-light-study-srt-v0.2.0.zip"
Expand-Archive ".\dxpx-light-study-srt-v0.2.0.zip" -DestinationPath ".\dxpx-light-study-srt-v0.2.0" -Force
cd ".\dxpx-light-study-srt-v0.2.0"
powershell -ExecutionPolicy Bypass -File .\go.ps1
```

装了 Git：

```powershell
git clone https://github.com/schprosper/uestc-party-activist-selenium-whisper-study-guide.git
cd .\uestc-party-activist-selenium-whisper-study-guide
powershell -ExecutionPolicy Bypass -File .\go.ps1
```

双击图形界面：

```text
开始使用.bat
```

GUI 会优先读取 `assets/launcher-icon.png` 作为展示图和图标。你可以把那张图裁掉右侧文字后保存成这个文件；没有这个文件时，启动器会绘制一个无文字的深色金色图标。

## 常用命令

默认刷入党积极分子：

```powershell
powershell -ExecutionPolicy Bypass -File .\go.ps1
```

只检查环境：

```powershell
powershell -ExecutionPolicy Bypass -File .\go.ps1 -Check
```

打开字幕目录：

```powershell
powershell -ExecutionPolicy Bypass -File .\go.ps1 -OpenSrt
```

只启动登录浏览器：

```powershell
powershell -ExecutionPolicy Bypass -File .\go.ps1 -LoginOnly
```

刷发展对象课程：

```powershell
powershell -ExecutionPolicy Bypass -File .\go.ps1 -Course fzdx
```

打开高级转写入口提示：

```powershell
powershell -ExecutionPolicy Bypass -File .\go.ps1 -AdvancedTranscribe
```

## 参数解释

`go.ps1` 常用参数：

```powershell
-Course jjfz          # 默认：入党积极分子
-Course fzdx          # 发展对象
-Check                # 只报告 Chrome/Python/.venv/wheels/SRT 状态
-OpenSrt              # 打开 srt 目录
-LoginOnly            # 只启动带调试端口的 Chrome
-AdvancedTranscribe   # 显示完整转写入口和命令
-Python <python.exe>  # 指定 Python
-NoInstall            # 缺 Python/Chrome 时不尝试 winget 安装
-ForceVenv            # 重建 .venv
```

## 不懂就复制给国产模型

```text
我在 Windows 上要运行这个仓库：
https://github.com/schprosper/uestc-party-activist-selenium-whisper-study-guide

目标：只自动刷电子科技大学党员教育培训平台的入党积极分子课程，并打开现成 SRT 字幕；不要让我配置 Whisper、ffmpeg、yt-dlp、video2md。

请根据我的电脑情况解释或改写这些命令：
1. powershell -ExecutionPolicy Bypass -File .\go.ps1 -Check
2. powershell -ExecutionPolicy Bypass -File .\go.ps1
3. powershell -ExecutionPolicy Bypass -File .\go.ps1 -OpenSrt

如果报错，请先判断是 Chrome、Python、PowerShell 执行策略、学校网页登录、还是网络问题。
```

## 仓库内容

```text
.
  README.md
  go.ps1                       # 默认轻量入口
  开始使用.bat                 # 双击 GUI
  setup.ps1                    # 基础 Python 依赖安装，兼容高级方案
  config.example.ps1           # 高级转写本机工具路径模板
  scripts/
    simple_launcher.ps1        # WinForms 图形启动器
    run_light_study.ps1        # 轻量刷课封装，只播放不转写
    launch_chrome_debug.ps1    # 启动独立调试 Chrome
    run_jjfz.ps1 / jjfz.py     # 入党积极分子自动播放
    run_fzdx.ps1 / fzdx.py     # 发展对象自动播放
    run_dxpx_md_transcribe.ps1 # 高级完整转写入口
    dxpx_md_transcriber.py
    dxpx_transcribe.ps1 / dxpx_transcribe.py
  vendor/wheels/               # Selenium 及 Python 依赖 wheel 缓存
  srt/                         # 已整理的入党积极分子最终 SRT
  docs/
```

本仓库不包含 Chrome 安装包、Python 安装包、Whisper 模型、ffmpeg、yt-dlp、video2md、浏览器 Cookie、账号信息、浏览器 profile、运行日志、下载视频或音频缓存。

## 已整理字幕

最终字幕在 `srt/`，合计 131 个 `.srt`：

```text
第1章_党的伟大成就                         50
第2章_党的性质和宗旨                         4
第3章_党的指导思想                           5
第4章_共产主义理想                           2
第5章_中国式现代化与民族复兴                 8
第6章_党的作风建设与纪律规矩                 9
第7章_党的组织制度                           9
第8章_党员权利和义务                         8
第9章_发展党员工作                          10
第10章_共产党员修养与入党动机               16
第11章_二十大党章公开课                     10
```

## 高级方案：完整转写

完整转写保留给已经有本地工具链的人。它需要 video2md、ffmpeg、yt-dlp、Whisper 或 whisper.cpp。

1. 准备 Python 3.10+、Google Chrome、ffmpeg、yt-dlp、Whisper/video2md。
2. 初始化依赖：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup.ps1
   ```

3. 复制并编辑本机配置：

   ```powershell
   Copy-Item .\config.example.ps1 .\config.local.ps1
   notepad .\config.local.ps1
   ```

4. 启动登录浏览器：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\launch_chrome_debug.ps1
   ```

5. 先验证 1 个视频：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\run_dxpx_md_transcribe.ps1 -MaxVideos 1
   ```

6. 跑积极分子全量：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\run_dxpx_md_transcribe.ps1
   ```

高级入口常用参数：

```powershell
-Course jjfz          # jjfz 积极分子，fzdx 发展对象，both 两个都跑
-MaxVideos 1          # 只跑几个视频；0 表示全量
-RunName "补转"       # 指定本轮输出目录名
-Force                # 已完成条目也重新转写
-NoResume             # 关闭断点续跑
-KeepWork             # 保留临时下载/音频，只建议排查时使用
-SniffTimeout 20      # 网络慢时调大
-TriggerWait 4        # 播放器加载慢时调大
```

## 大文件和发布

半离线包只把 Selenium wheels 放进仓库。Chrome、Python 安装包、Whisper 模型、ffmpeg、yt-dlp、video2md 都不放进 Git history。

GitHub 普通仓库对大文件有限制：超过 50 MiB 会警告，超过 100 MiB 会阻止推送；需要分发较大二进制时应使用 Release 资产或 Git LFS。参考 GitHub Docs: https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github

计划发布资产：

```text
dxpx-light-study-srt-v0.2.0.zip  # 轻量刷课 + GUI + SRT + wheels
srt-only-v0.2.0.zip              # 只含最终字幕
```

## 隐私清理清单

公开发布前确认：

```powershell
git status --ignored --short
```

不要提交：

- `chrome-profile/`、`chrome-transcribe-profile*/`、任何浏览器用户数据目录。
- `config.local.ps1`。
- `.venv/`、`.tmp/`、`output/`、`logs/`。
- `manifest.jsonl`、`meta.json`、`transcribe.log`、`failed_tasks.log`。
- 下载视频、音频、Whisper 中间 JSON/TXT、截图。

本仓库的 `.gitignore` 默认排除这些内容，只保留 `srt/**/*.srt` 作为最终字幕。

## 合规和限制

这个项目不是平台官方工具。自动刷课仍然需要你手动登录学校平台，脚本不会保存账号密码。课程平台账号、课程内容、学校规则、版权和使用责任由使用者自行确认。

DXPX 页面结构如果更新，Selenium 选择器可能需要维护。现成 SRT 是保守校对，不是逐字精校；我们只修了高置信错字、专名、标题和明显术语错误，没有润色或改写课程内容。
