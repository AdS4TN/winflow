# GitHub 发布指南

本文用于首次把 Winflow 发布到 GitHub。它和 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) 的关系是：

- `RELEASE_CHECKLIST.md` 是逐项勾选清单；
- 本文是一次完整发布流程说明；
- `scripts/release_audit.py` 和 `scripts/package_audit.py` 只验证代码与仓库内容，不能替你完成 GitHub 页面设置、截图、release notes 等人工发布动作。

## 1. 发布定位

Winflow 的公开定位应保持一致：

```text
Windows-first local automatic work journal
```

推荐 GitHub description：

```text
Windows-first local automatic work journal
```

推荐 topics：

```text
windows
local-first
time-tracking
activity-tracker
sqlite
privacy
```

不要把 Winflow 描述成 macOS Dayflow 的移植版。Dayflow 只作为产品体验和开源成熟度参考，Winflow 的实现路线是 Windows 原生前台窗口采集、进程统计、exe 图标和本地 SQLite。

## 2. 发布前本地检查

在仓库根目录运行：

```powershell
python -m compileall -q app tests scripts
python -m unittest discover -s tests
python scripts/release_audit.py
python scripts/package_audit.py
git diff --check
```

这些检查应覆盖：

- Python 文件可编译；
- 单元测试通过；
- 不提交本机数据库、日志、`.env`、exe 图标缓存；
- 不重新引入浏览器历史读取模块；
- 不引入 macOS/Swift/ScreenCaptureKit 等实现依赖；
- 内置 SVG 图标随 wheel 分发；
- 安装态运行时数据目录不会写进源码树或 `site-packages`。

## 3. 发布前必须人工替换的占位

发布前必须把以下占位替换成真实仓库地址：

```text
https://github.com/OWNER/winflow
```

至少检查：

```text
README.md
pyproject.toml
docs/RELEASE_CHECKLIST.md
```

替换后再运行：

```powershell
python scripts/release_audit.py
```

如果你暂时还没创建 GitHub 仓库，可以保留 `OWNER/winflow` 占位，但不要打正式 release。

## 4. 不要提交的本地文件

发布前确认这些内容仍然是 ignored，而不是 staged：

```text
data/
logs/
docs/internal/
static/exe-icons/*.png
static/exe-icons/*.ico
.env
winflow-uploader*.log
build/
dist/
*.egg-info/
```

其中 `static/exe-icons/.gitkeep` 可以提交，用于保留源码树运行时的图标缓存目录。

## 5. 建议的首次提交结构

如果准备拆分提交，建议按以下顺序：

1. Windows-first 采集、统计、隐私边界和浏览器历史移除；
2. 本地 Web UI、应用使用统计、exe 图标、上传模块；
3. 开源文档、GitHub 模板、CI、release audit；
4. package data、安装态路径、package audit；
5. 文档一致性和发布指南。

如果只做一次首发提交，commit message 建议：

```text
Prepare Winflow for Windows-first open source release
```

## 6. GitHub 仓库设置

创建仓库后建议：

- 默认分支：`main`；
- 开启 GitHub Actions；
- 添加 MIT license；
- 添加 description 和 topics；
- 开启 Issues；
- 使用仓库内 issue templates；
- 首次 release 前至少等待一次 CI 通过。

## 7. README 截图或 GIF

当前代码不强制要求截图，但公开发布时建议补一张：

- 本地控制台首页；
- `/usage` 应用统计页；
- 时间轴或活动带区域。

截图前注意：

- 使用测试数据或脱敏数据；
- 不展示真实窗口标题；
- 不展示本机绝对路径；
- 不展示服务器 token、URL、个人网站后台。

建议放置位置：

```text
docs/assets/
```

如果暂时没有截图，可以先发布 alpha，但 release notes 要说明 UI 仍在快速迭代。

## 8. 首次 release notes 建议

tag：

```text
v0.1.0-alpha
```

release notes 可以包含：

- Windows-first、本地优先的自动工作日志；
- 默认只采集前台应用，不截图、不录屏、不 OCR、不调用 AI、不读取浏览器历史；
- 本地 SQLite；
- 活动带聚合和应用使用统计；
- 本地 Web 预览；
- 可选自托管上传；
- 当前仍是 alpha，不承诺计费级精确时长。

## 9. 发布后验证

发布后建议在一个新的目录重新 clone：

```powershell
git clone https://github.com/<OWNER>/winflow.git
cd winflow
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main init
python -m app.main serve --with-collector
```

然后打开：

```text
http://127.0.0.1:8765
http://127.0.0.1:8765/usage
```

如果你要验证安装态 wheel：

```powershell
python scripts/package_audit.py
```
