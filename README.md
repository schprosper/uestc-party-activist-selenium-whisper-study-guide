# UESTC 入党积极分子快速且深度学习指南

基于 Selenium、Chrome DevTools 网络日志、video2md 与 Whisper 的自动观看和自动转写脚本。

这个仓库是一次真实课程资料整理工作的公开发行版：我们用登录后的调试 Chrome 自动进入电子科技大学党员教育培训平台（DXPX），遍历“入党积极分子”课程，嗅探视频媒体地址，调用本地转写工具生成字幕，再把字幕去重、分章、校对明显 ASR 错词后整理成最终 SRT。

本仓库不包含浏览器 Cookie、账号信息、浏览器 profile、运行日志、下载视频、音频缓存、`meta.json` 或个人路径配置。

## 我们实际做了什么

- 自动观看/遍历：用 Selenium 连接本机调试 Chrome，进入 DXPX 课程页，逐个打开视频页。
- 媒体发现：通过 Chrome DevTools/performance log 捕获 `.m3u8` / `.mp4` 请求。
- 转写：把运行时 Cookie、Referer、User-Agent 临时传给 `video2md` / `yt-dlp` / Whisper，生成 `字幕.srt` 和学习笔记。
- 去重：原始运行中出现过 1 条误嗅探重复项，即长征专题中的 `完成` 被识别到“党的伟大成就”的同一 m3u8；最终版剔除了它。
- 校对：只修高置信错字和专名术语，例如“明智维新→明治维新”“处级阶段→初级阶段”“中国是现代化→中国式现代化”“张文天→张闻天”“伯古→博古”“王家祥/王驾祥→王稼祥”等。
- 交付：整理出 131 个 SRT，按 11 个章节归档，字幕序号和时间轴保持原样。

## 仓库内容

```text
.
  README.md
  setup.ps1                    # 基础一键部署：创建 .venv 并安装 Python 依赖
  config.example.ps1           # 本机工具路径配置模板
  scripts/
    launch_chrome_debug.ps1    # 启动独立调试 Chrome
    run_dxpx_md_transcribe.ps1 # 推荐入口：嗅探并逐个转写
    dxpx_md_transcriber.py     # 页面遍历、断点续跑、调用转写
    dxpx_transcribe.ps1        # 单个 m3u8 调用 video2md 转写整理
    whisper_cpp_cublas_adapter.ps1
    run_jjfz.ps1 / jjfz.py     # 旧入口：自动播放积极分子课程
    run_fzdx.ps1 / fzdx.py     # 旧入口：自动播放发展对象课程
  srt/                         # 已校对的入党积极分子最终 SRT
  docs/
```

## 合规和风险说明

这个项目只做技术学习和个人学习资料整理。课程平台账号、课程内容、学校规则、版权和使用责任由使用者自行确认。

脚本会在运行时读取当前调试 Chrome 的登录态 Cookie，并把它作为命令参数传给本地转写/下载工具；Cookie 不会被写入仓库，但在脚本运行期间可能出现在本机进程命令行里。因此不要共享运行中的机器、不要提交 `chrome-profile`、`.tmp`、`output`、日志或 `config.local.ps1`。

## 已整理字幕

最终字幕在：

```text
srt/
```

数量：

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

合计 131 个 `.srt`。

## 部署方案一：推荐的 Codex/Windows 部署法

适合已经有本地转写工具链的人。`setup.ps1` 会安装 Selenium 依赖，但不会替你安装需要手动准备的 Whisper 模型、ffmpeg 或 video2md。

1. 克隆仓库并进入目录。

   ```powershell
   git clone <你的仓库地址>
   cd .\UESTC入党积极分子快速且深度学习指南——基于Selenium与Whisper的自动观看和自动转写脚本
   ```

2. 基础一键部署。

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup.ps1
   ```

3. 编辑本机配置。

   `setup.ps1` 会自动生成 `config.local.ps1`。把里面的路径改成你本机实际路径：

   ```powershell
   $env:VIDEO2MD_SCRIPT = "D:\path\to\video2md\video2md.ps1"
   $env:YTDLP_PATH = "D:\path\to\yt-dlp.exe"
   $env:FFMPEG_PATH = "D:\path\to\ffmpeg.exe"
   $env:WHISPER_CPP_ROOT = "D:\path\to\Whisper\Cpp"
   $env:WHISPER_CPP_CUBLAS_ROOT = "D:\path\to\Whisper\CppCuBlas"
   ```

4. 启动独立调试 Chrome。

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\launch_chrome_debug.ps1
   ```

5. 在弹出的 Chrome 中登录：

   ```text
   https://dxpx.uestc.edu.cn/
   ```

6. 先只跑 1 个视频验证链路。

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\run_dxpx_md_transcribe.ps1 -MaxVideos 1
   ```

7. 跑积极分子全量。

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\run_dxpx_md_transcribe.ps1
   ```

默认输出在：

```text
output\dxpx_notes
```

默认临时目录在：

```text
.tmp\dxpx_md_auto_transcribe
```

不加 `-KeepWork` 时，临时视频、音频和中间文件会自动清理。

## 部署方案二：手动部署法

1. 安装 Python 3.10+、Google Chrome、ffmpeg、yt-dlp、Whisper 或 whisper.cpp。
2. 准备可用的 `video2md.ps1`，确认它能把一个普通 m3u8 转成 SRT。
3. 创建虚拟环境并安装依赖：

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --upgrade pip
   .\.venv\Scripts\python.exe -m pip install -r .\scripts\requirements.txt
   ```

4. 复制配置模板：

   ```powershell
   Copy-Item .\config.example.ps1 .\config.local.ps1
   ```

5. 编辑 `config.local.ps1` 后，按“部署方案一”的第 4 步继续。

## 推荐入口参数

`scripts\run_dxpx_md_transcribe.ps1` 的常用参数：

```powershell
-Course jjfz          # jjfz 积极分子，fzdx 发展对象，both 两个都跑
-MaxVideos 1          # 只跑几个视频；0 表示全量
-RunName "补转"       # 指定本轮输出目录名
-Force                # 已完成条目也重新转写
-NoResume             # 关闭断点续跑
-KeepWork             # 保留临时下载/音频，只建议排查时使用
-SniffTimeout 20      # 网络慢时调大
-TriggerWait 4        # 播放器加载慢时调大
-NoRefreshOnMiss      # 嗅探不到媒体时不自动刷新/重进页面
```

示例：

```powershell
# 只验证 1 个视频
powershell -ExecutionPolicy Bypass -File .\scripts\run_dxpx_md_transcribe.ps1 -MaxVideos 1

# 网络慢时增加等待
powershell -ExecutionPolicy Bypass -File .\scripts\run_dxpx_md_transcribe.ps1 -MaxVideos 1 -SniffTimeout 20 -TriggerWait 4

# 发展对象课程
powershell -ExecutionPolicy Bypass -File .\scripts\run_dxpx_md_transcribe.ps1 -Course fzdx
```

## 旧入口：自动播放并后台转写

如果你更想模拟“逐个视频播放”的流程，可以先启动调试 Chrome 并登录，然后运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_jjfz.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_fzdx.ps1
```

只播放、不转写：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_jjfz.ps1 -NoTranscribe
powershell -ExecutionPolicy Bypass -File .\scripts\run_fzdx.ps1 -NoTranscribe
```

推荐优先使用 `run_dxpx_md_transcribe.ps1`，因为它的断点续跑、失败补转和输出整理更完整。

## 断点续跑逻辑

推荐入口会读取本轮输出目录下的 `logs\manifest.jsonl`，并核对每个视频目录里的 `meta.json` 与成品文件。已经完成且文件仍存在的条目会在点击视频和嗅探前跳过；失败项、缺成品项或加了 `-Force` 的条目会重新转写。

## 隐私清理清单

公开发布前请确认：

```powershell
git status --ignored --short
```

不要提交这些内容：

- `chrome-profile/`、`chrome-transcribe-profile*/`、任何浏览器用户数据目录。
- `config.local.ps1`。
- `.tmp/`、`output/`、`logs/`。
- `manifest.jsonl`、`meta.json`、`transcribe.log`、`failed_tasks.log`。
- 下载视频、音频、Whisper 中间 JSON/TXT、截图。

本仓库的 `.gitignore` 已默认排除这些文件，只保留 `srt/**/*.srt` 作为最终字幕。

## 诚实限制

- 这个项目不是平台官方工具。
- 完整“一键部署”无法覆盖人工登录、学校账号权限、Whisper 模型下载和 video2md 安装。
- ASR 校对是保守校对，不是人工逐字精校。我们只修了高置信错字、专名、标题和明显术语错误，没有润色或改写课程内容。
- DXPX 页面结构如果更新，Selenium 选择器可能需要维护。
