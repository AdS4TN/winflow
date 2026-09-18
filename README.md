# Winflow

> Windows 本地优先的自动工作日志。记录前台应用活动，把一天整理成可回看的时间线与应用使用统计。

Winflow is a local-first automatic work journal for Windows.

它借鉴 [Dayflow](https://github.com/JerryZLiu/Dayflow) 的产品方向：自动记录、时间线回看、local-first、开源透明。但 Winflow **不是 macOS 移植版，也不采用 macOS/Swift/ScreenCaptureKit 技术路线**。Winflow 是 Windows-first 项目，从 Win32 前台窗口、Windows 进程名、exe/快捷方式图标和本地 SQLite 出发，先做好轻量、可控、隐私默认安全的应用使用日志。

换句话说：Dayflow 是产品参考，不是实现参考。Winflow 的核心路线是 Windows 原生采集与 Windows 桌面体验。

## 项目速览

| 维度 | 内容 |
| --- | --- |
| 场景 | Windows 个人工作回顾与应用使用统计 |
| 运行方式 | Python 3.11+，本地 CLI + Web 页面 |
| 核心技术 | Win32 前台窗口 API、SQLite、Python HTTP 服务、Pillow |
| 关键设计 | 本地优先、浏览器标题脱敏、活动带聚合、显式选择上传 |
| 当前阶段 | Alpha 原型，没有托盘安装器或生产 SLA 承诺 |

**阅读路径：** `app/main.py` → `app/collector.py` → `app/storage.py` → `app/activity_bands.py` / `app/app_usage.py` → `app/web.py`。仓库提供源码与测试，不包含个人活动数据库。功能描述来自实现，不代表所有 Windows 环境均已验收。

## 为什么做 Winflow

传统时间追踪工具通常要求你手动开始/停止计时，或者只告诉你“哪个应用打开了多久”。Winflow 更关注个人回顾场景：

- 我刚才这几个小时大概在做什么？
- 今天主要在哪些应用之间切换？
- 一段工作是不是被聊天、浏览器、终端来回打断？
- 我能不能把本地统计安全地接到自己的个人网站？

Winflow 不追求计费级别的精确秒表，而是把 Windows 前台应用事件聚合成可回看的时间线和应用使用统计。

## 当前状态

Winflow 还处于早期阶段，但已经具备可运行的本地闭环：

- Windows 前台窗口采集；
- 本地 SQLite 存储；
- 活动带聚合，用于处理频繁切屏；
- 应用使用时长统计；
- 本地 Web 预览页；
- Windows exe 图标提取与缓存；
- 可选上传到自托管服务端。

## 功能一览

| 功能 | 当前实现 | 为什么有用 |
| --- | --- | --- |
| 自动应用时间线 | 定期读取 Windows 前台窗口，记录时间段、进程名和脱敏标题 | 不需要手动打点，也能回看一天节奏 |
| 活动带聚合 | 以 15 分钟窗口、3 分钟停留、3 分钟合并间隔整理细碎切屏 | 适合频繁切浏览器、编辑器、终端、聊天工具的真实工作流 |
| 应用使用统计 | `/usage` 与 `/api/apps/usage` 输出应用级时长、次数、颜色和图标 | 可以直接接入个人网站或本地 dashboard |
| Windows exe 图标 | 从 exe 或快捷方式提取图标，缓存到本地 | 比默认字母图标更接近真实桌面体验 |
| 本地 Web 预览 | `python -m app.main serve --with-collector` 启动本地控制台 | 方便验证采集和聚合结果 |
| 可选自托管上传 | 只在显式配置服务器和 token 后上传聚合快照 | 个人网站可以展示统计结果，同时不暴露原始窗口数据 |
| 隐私默认安全 | 默认不截图、不录屏、不读浏览器历史、不上传、不调用 AI | 适合作为长期后台工具逐步完善 |

### 自动应用时间线

Winflow 定期读取当前 Windows 前台窗口，并记录：

- 时间段；
- 进程名；
- 本地 exe 路径，仅用于提取图标；
- 窗口标题，浏览器窗口会被脱敏为固定文案。

### 活动带 Activity Bands

Winflow 不追求秒级精确计时，而是回答两个问题：

- 某个时间点我大概在做什么？
- 某件事大概从什么时候持续到什么时候？

当前规则：

- 以 15 分钟作为分析窗口；
- 应用在窗口内累计停留超过 3 分钟，会形成活动带；
- 同一事件之间间隔不超过 3 分钟，会自动合并；
- 一段时间允许多个活动带并存，用来表达查资料、写代码、跑命令、聊天等频繁切屏场景。

### 应用使用统计

`/usage` 页面和 `/api/apps/usage` 接口会展示应用级统计：

- 应用名称；
- 使用时长；
- 打开/命中进程；
- 图标与展示颜色。

默认不会展示浏览器标签页、站点域名、完整 URL、真实 exe 路径或窗口标题。

### Windows exe 图标

Winflow 会尝试从本机 exe 或其桌面快捷方式中提取更清晰的应用图标。源码目录运行时默认缓存到 `static/exe-icons/`；安装后运行时默认缓存到当前 Windows 用户数据目录下的 `exe-icons/`。这些图标是本机派生产物，默认不会提交到 Git。

### 可选上传

Winflow 默认不上传任何数据。只有显式配置 `WINFLOW_SERVER_URL` 和 `WINFLOW_UPLOAD_TOKEN`，并运行 `upload-usage` 命令时，才会把本地聚合后的应用统计快照上传到你的服务端。

## 工作原理

```text
Windows 前台窗口
      │
      ▼
app/windows_activity.py
      │  Win32 API 读取 hwnd / pid / process_name / exe_path / window_title
      ▼
app/storage.py
      │  写入本地 SQLite，并对浏览器标题做默认脱敏
      ▼
app/activity_bands.py      app/app_usage.py
      │                    │
      │                    └─ 生成应用级使用统计和图标信息
      ▼
活动带时间线
      │
      ├─ 本地 Web UI：/、/usage
      ├─ 本地 API：/api/timeline、/api/bands、/api/apps/usage
      └─ 可选上传：POST 到用户自托管服务端
```

详细模块说明见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 隐私默认值

默认情况下，Winflow：

- 不截图；
- 不录屏；
- 不做 OCR；
- 不调用 AI/LLM；
- 不读取浏览器历史；
- 不上传服务器；
- 不展示浏览器具体标签页或站点；
- 不在应用统计接口输出 `window_title`、`exe_path` 或完整 URL。

更多说明见 [PRIVACY.md](PRIVACY.md)。

## 要求

- Windows 10/11；
- Python 3.11+；
- PowerShell；
- Pillow，用于本地 exe 图标后处理。

## 快速开始

要求：Windows 10/11，Python 3.11+。

当前 alpha 版本仍推荐从仓库源码目录运行，便于审计代码、查看本地数据和参与开发：

```powershell
git clone https://github.com/AdS4TN/winflow.git
cd winflow
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main init
python -m app.main serve --with-collector
```

`pyproject.toml` 已包含基础 package 配置和 `winflow` console script，并由 `scripts/package_audit.py` 验证内置静态图标、安装态数据目录和图标缓存目录。但首次 GitHub release 仍以源码运行作为主路径；PyPI 发布、Windows installer、托盘应用和自启动安装器会在后续版本单独完善。

打开：<http://127.0.0.1:8765>

查看应用使用统计预览页：<http://127.0.0.1:8765/usage>

如果你想把采集和 Web 服务拆开运行：

```powershell
python -m app.main collect
# 另开一个 PowerShell
python -m app.main serve
```

## 常用命令

```powershell
python -m app.main init
python -m app.main once
python -m app.main collect --interval 5
python -m app.main serve --port 8765
python -m app.main serve --with-collector
python -m app.main bands
python -m app.main usage
python -m app.main export
```

### 可选上传

复制 `.env.example` 为 `.env`，填入你自己的服务器地址和 token：

```powershell
Copy-Item .env.example .env
```

然后运行：

```powershell
python -m app.main upload-usage --day 2026-06-08
python -m app.main upload-usage --watch --interval 300
```

上传是 opt-in：没有 `WINFLOW_SERVER_URL` 或 `--server-url` 时，命令会直接失败，不会默认指向任何个人服务器或本地端口。

## 本地数据位置

源码目录运行时的默认数据库：

```text
data/winflow.sqlite
```

源码目录运行时的本地派生数据：

```text
data/icon_map.json
static/exe-icons/
logs/
```

这些路径已在 `.gitignore` 中忽略，因为它们可能包含你的本机活动痕迹或本机派生图标。

如果通过安装后的 `winflow` 命令运行，默认数据目录会切到当前 Windows 用户数据目录，例如：

```text
%LOCALAPPDATA%\Winflow\
```

你可以用环境变量覆盖：

```powershell
$env:WINFLOW_DATA_DIR="D:\WinflowData"
$env:WINFLOW_DB="D:\WinflowData\winflow.sqlite"
$env:WINFLOW_EXE_ICON_DIR="D:\WinflowData\exe-icons"
```

## HTTP API

本地 Web 服务默认监听 `127.0.0.1:8765`。

| Endpoint | 说明 |
| --- | --- |
| `/` | 本地控制台与活动带视图 |
| `/usage` | 应用使用统计预览页 |
| `/api/timeline` | 安全化前台事件时间线 |
| `/api/bands` | 活动带聚合数据 |
| `/api/apps/usage` | 应用级使用统计 |
| `/api/collector/status` | 内置采集器状态 |
| `/api/icon-map` | 图标映射 |
| `/api/export` | Markdown 导出 |

## 项目结构

```text
app/
  main.py              # CLI 入口与命令编排
  collector.py         # Windows 前台窗口采集循环与状态
  web.py               # 本地 Web UI、HTTP handler 与 API
  windows_activity.py  # Windows 前台窗口读取
  storage.py           # SQLite schema 与读写
  activity_bands.py    # 活动带聚合算法
  app_usage.py         # 应用级使用统计
  exe_icon.py          # Windows exe 图标提取
  icon_map.py          # 图标映射与 fallback
  uploader.py          # 可选上传模块
  static/              # 打包随附的内置 SVG 图标
tests/                 # 单元测试
static/                # 源码树运行时的本机 exe 图标缓存占位
docs/                  # 设计与接入文档
```

## 开发与测试

本地核验（2026-09-18，Python 3.12）：语法检查与 49 项 unittest 测试通过。本轮未执行打包审计、真实桌面采集和外部上传验证。

```powershell
python -m compileall -q app tests scripts
python -m unittest discover -s tests
python scripts/release_audit.py
python scripts/package_audit.py
```

如果采集、图标或本地 Web 页面没有按预期工作，先看 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。

贡献指南见 [CONTRIBUTING.md](CONTRIBUTING.md)。

如果你准备把仓库公开发布到 GitHub，请看 [docs/GITHUB_RELEASE_GUIDE.md](docs/GITHUB_RELEASE_GUIDE.md)。

## Roadmap

见 [ROADMAP.md](ROADMAP.md)。短期重点：

- 继续将 `app/web.py` 中的 HTML/CSS/JS 拆到 `static/` 或模板文件；
- 增加 Windows 托盘与自启动；
- 增加保留期与数据清理；
- 完善应用图标和应用名称归一化；
- 将可选上传协议文档化；
- 在保持隐私默认安全的前提下探索本地总结能力。

## License

MIT License. See [LICENSE](LICENSE).
