# Development / 开发、演示与验证

本地环境：Windows、Python 3.11.15。GUI 使用 Tkinter。运行依赖见 `requirements.txt`，打包依赖见 `requirements-build.txt`。正常运行需要 Chrome 或 Edge，以下离线命令无需真实登录。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe examples\offline_demo.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

GUI 测试创建隐藏 Tk 窗口，用 mock 替代浏览器和平台客户端。生成的 `audit/` 不进入 Git。离线演示使用合成数据，拦截 HTTP、WebSocket 连接和进程启动，不加载个人浏览器或公开题库。

| 演示场景 | 预期 | 业务函数 |
| --- | --- | --- |
| 卡顿恢复 | 先恢复、有限刷新、最终停止 | `StallGuard.observe` |
| 选项重排 | A/B 对调仍输出当前正确 ID | `resolve` |
| 已完成跳过 | 模拟平台已完成，不发写操作 | `Client.run_videos` |
| 拒绝误报完成 | 请求受理但正式未完成，报错停止 | `Client.run_videos` |

任何一项不满足预期，演示抛出异常并返回非零状态，不是只打印固定结果。加 `--json` 可输出机器可读结果。

## 测试范围

17 个测试方法：`test_core.py` 14 个、`test_gui.py` 1 个、`test_playback.py` 2 个。覆盖域名/类别拒绝、资源/培训期匹配、答案冲突、取消、完成跳过、状态不一致、POST 不重试、GUI 分派与失败恢复、卡顿预算。

mock 与合成数据不证明真实网站兼容、题库准确率或所有电脑可用；没有覆盖率指标。可选 Chromium DOM 验证会启动独立无头浏览器，仅解析合成 HTML，替换平台请求：

```powershell
New-Item -ItemType Directory -Force audit | Out-Null
.\.venv\Scripts\python.exe tests\browser_fixtures.py
```

它不属于默认 unittest 发现，也不模拟学校服务器，一般评审无需执行。

## CI 与构建

[Windows checks](../.github/workflows/checks.yml) 在 push、pull request 或手动触发时安装依赖，运行演示和 unittest。只有仓库读取权限，不使用学校账号或发布凭据，不执行平台任务。参考 [GitHub 官方 Python 测试说明](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)；有配置不等于远端已通过，以对应提交 Actions 结果为准。

```powershell
.\.venv\Scripts\python.exe src\app.py
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe build.py
```

完整分发 `dist/DXPX_Helper/`，不能只复制 EXE。打包入口附带启动器、教程和公开题库，不复制个人资料或核查记录。

## 本次整理

2026-11-09 在独立 V1.3 副本整理文档、演示与 CI；应用仍为 V1.2，没有重发安装包。检查离线演示、17 项测试和文档链接，对照旧版核对运行时代码、资产及打包入口。不重新登录或操作真实课程/考试，不以离线结果替代平台验收。
