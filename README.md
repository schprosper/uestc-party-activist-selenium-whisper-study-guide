# UESTC 党校助手 · V1.2

积极分子、发展对象两个一键入口，Windows 10/11 64 位免安装版。

**[下载最新版 Windows 程序](https://github.com/schprosper/uestc-party-activist-selenium-whisper-study-guide/releases/latest/download/DXPX_Helper_Windows_x64.zip)**

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
