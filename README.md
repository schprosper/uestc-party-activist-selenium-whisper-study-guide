# DXPX Helper · Windows 浏览器任务助手

面向 UESTC 党校培训页面的 Python 桌面工具，整合浏览器会话、任务执行、故障恢复与平台状态复核，支持积极分子和发展对象两类流程。

**Python 3.11 · Tkinter · Chrome DevTools Protocol · requests · unittest · PyInstaller**

[Architecture / 架构](docs/ARCHITECTURE.md) · [Demo & Development / 演示与开发](docs/DEVELOPMENT.md) · [Engineering case study](docs/CASE_STUDY.md) · [来源与贡献](ATTRIBUTION.md)

> 当前应用及 Windows Release 仍为 **V1.2**；本次为仓库展示、离线演示与 CI 整理，不是新程序发布。仓库沿用历史名称，当前主线不依赖 Selenium，也不包含 Whisper 转写。

## 工程设计

页面变化、播放器暂停和网络故障会导致任务中断；播放器结束或请求受理，也不等于平台已记录完成。本项目分别处理页面操作、有限恢复与结果确认，并在失败时保留浏览器供用户接管。

| 设计 | 实现与价值 | 代码入口 |
| --- | --- | --- |
| 会话接入 | 专用 Chrome/Edge、动态端口、两类资料隔离，免维护 WebDriver | [`ensure_browser` / `CDP`](src/core.py) |
| 任务生命周期 | 工作线程与 UI 队列、协作取消、类别级 Windows 互斥锁 | [`App`](src/app.py) |
| 有限恢复 | 停滞 10 秒尝试恢复，每资源最多刷新两次，超限停止 | [`StallGuard`](src/playback.py) |
| 结果复核 | 区分动作完成和平台正式状态，跳过已有完成记录 | [`Client`](src/core.py)、[`run_playback`](src/playback.py) |
| 确定性匹配 | 根据完整内容映射当前选项 ID，冲突或歧义不猜测 | [`resolve`](src/core.py) |
| 可分发与排查 | Windows 目录式程序、本机 JSONL 日志和反馈 | [`build.py`](build.py)、[`App.feedback`](src/app.py) |

## 无账号离线演示

在仓库根目录运行，不打开浏览器、不连接学校平台：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe examples\offline_demo.py
```

预期输出四个 `PASS`：有限恢复、选项重排、完成任务跳过、拒绝将请求受理当作正式完成。演示直接调用业务函数，使用合成数据并拦截外部 I/O。

现有 **17 项 unittest** 覆盖请求边界、资源身份、匹配歧义、取消、状态一致性、GUI 分派和恢复预算。测试数不等于代码覆盖率或线上兼容率；运行方式见[开发说明](docs/DEVELOPMENT.md)。

## English overview

A Windows desktop automation tool for a specific training website. The engineering focus is bounded recovery, explicit outcome verification, cancellable background work and reproducible offline checks. It uses CDP and Python; it is **not embedded firmware or an RTOS implementation**. See the [English case study](docs/CASE_STUDY.md) for implementation evidence and limitations.

## 开始使用

1. 下载上面的程序，完整解压。
2. 双击 `积极分子一键启动.cmd` 或 `发展对象一键启动.cmd`；也可打开 `DXPX_Helper.exe` 自行选择类别。
3. 在打开的学校官网登录自己的账号并完成验证码。有多个培训期时，进入本次培训期，程序会继续。
4. 查看助手窗口的最后提示。退出助手不会关闭课程浏览器。

无需安装 Python，无需复制 Cookie；电脑需安装 Chrome 或 Edge。GitHub 的 Code → Download ZIP 下载的是源码，请普通使用者使用上面的程序下载链接。

## 这版有什么

- **积极分子兼容播放**：默认正常播放视频，点击“继续／继续播放”。播放时间 10 秒未前进，先尝试恢复，再按需刷新，同一视频最多刷新两次；不无限刷新。
- **发展对象**：保留原任务方式，也可点击“兼容播放”使用正常播放。已能读取的正式完成课程会跳过。
- **测试辅助**：进入官网的综合测试或章节测试后，匹配已知题目并保存；保留已有答案，无可靠答案的题号会提示，使用者检查后在官网交卷。
- **双题库**：积极分子 4050 题、发展对象 1230 题，可直接打开程序内题库目录，也可从 [assets/题库](assets/题库) 单独下载。
- **停止与反馈**：可以随时停止后续操作；日志和反馈只保存到本机。

兼容播放按正常视频时长运行，不快进。播放器结束与平台任务完成分开处理；无法读取正式状态时会提示“待官网确认”。发展对象默认任务采用直接记录提交方式，不能保证平台不识别自动化。公开题库不保证覆盖所有当期试题。

## 登录资料与故障提示

每个类别独立保存浏览器资料，位置为 `%LOCALAPPDATA%\UESTC_DXPX_Helper\`。程序不保存账号密码文本，也不要求向第三方提交 Cookie。

报错时打开“日志 / 反馈”，保留最后几行提示。反馈不要附密码、Cookie、验证码或 `browser` 文件夹。页面变化、网络中断或账号培训类型不匹配，均可能需要进一步排查；本版不保证适配所有培训期。

完整操作见 [使用教程.txt](使用教程.txt)。本版不包含转写功能。旧版转写脚本与字幕仍可在 Git 历史及旧版发行记录查看。

## 源码运行与构建

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src\app.py
```

构建 Windows 程序：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe build.py
```

产物位于 `dist/DXPX_Helper/`。运行环境、浏览器资料、日志、临时文件和安装包不进入 Git。

题库与项目参考：[MonarchMan/UESTC_dxpx](https://github.com/MonarchMan/UESTC_dxpx)。


## 来源与项目边界

本项目不是学校官方客户端。发展对象默认仍包含直接记录提交，不能把整个应用描述为只读工具或仅正常播放；直接记录也不等于正常观看。实际使用需符合平台要求。

题库 5,280 条是上游源记录数，不是原创题目数、唯一题数或准确率。代码及文档使用 AI 编程工具辅助实现，来源与贡献边界见 [ATTRIBUTION.md](ATTRIBUTION.md)。

`src/app.py` 管理界面与任务，`src/core.py` 管理连接、页面和业务判断，`src/playback.py` 管理播放恢复；`examples/`、`tests/` 和 `docs/` 分别提供演示、验证及设计说明。已知局限见[架构文档](docs/ARCHITECTURE.md)。
