# 发布前检查

这个仓库设计为可公开发布，但发布前仍建议逐项检查。

## 本地检查

```powershell
git status --ignored --short
rg -n "Cookie|Set-Cookie|Authorization|Bearer|password|C:\\Users|chrome-profile|config.local" .
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
