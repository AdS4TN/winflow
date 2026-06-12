# Winflow 架构说明

本文面向想要理解或贡献 Winflow 的开发者，说明当前 Windows-first 版本的模块边界、数据流和隐私约束。

## 1. 设计目标

Winflow 的目标是做一个 Windows 本地优先的自动工作日志：

- 默认在本机运行和存储；
- 默认只统计应用级活动；
- 默认不截图、不录屏、不 OCR、不调用 AI/LLM、不读取浏览器历史；
- 可把聚合后的使用统计上传到用户自己的服务端；
- 代码结构足够简单，便于个人开发者审计和二次开发。

Dayflow 只作为产品体验与开源成熟度参考。Winflow 不迁移 Dayflow 的平台实现，也不引入 macOS 技术栈。

## 2. 运行时数据流

```text
Windows 前台窗口
  └─ app/windows_activity.py
       读取 hwnd、pid、窗口标题、进程名、exe 路径
          │
          ▼
     app/collector.py
       周期性采样，调用存储层写入事件
          │
          ▼
     app/storage.py
       SQLite schema、事件合并、浏览器窗口标题脱敏
          │
          ├─ app/timeline.py
          │    构建安全化原始时间线
          │
          ├─ app/activity_bands.py
          │    把细碎切屏聚合成活动带
          │
          └─ app/app_usage.py
               构建应用级使用统计快照
                    │
                    ├─ app/icon_map.py
                    │    内置和用户自定义图标映射
                    │
                    └─ app/exe_icon.py
                         从 exe 或快捷方式提取本地图标
```

本地 Web 服务由 `app/web.py` 提供，CLI 入口由 `app/main.py` 编排。

## 3. 核心模块职责

| 模块 | 职责 | 重要边界 |
| --- | --- | --- |
| `app/windows_activity.py` | 通过 Windows Win32 API 获取当前前台窗口 | 只做采样，不做聚合和上传 |
| `app/collector.py` | 按固定间隔调用采样并写入存储 | 采集失败应记录状态，不中断 Web 服务 |
| `app/storage.py` | SQLite schema、事件延长、浏览器标题脱敏 | 原始窗口标题只保存在本地库中，浏览器标题默认替换为固定文案 |
| `app/activity_bands.py` | 生成活动带 | 不读取浏览器历史，不输出 exe 路径 |
| `app/app_usage.py` | 生成应用级统计快照 | 不输出 `window_title`、`exe_path`、完整 URL 或站点明细 |
| `app/exe_icon.py` | 提取 Windows exe/快捷方式图标 | 图标缓存是本机派生产物，不能提交 |
| `app/icon_map.py` | 内置图标和颜色映射 | 用户自定义映射保存在 `data/icon_map.json`，默认忽略 |
| `app/uploader.py` | 可选自托管上传 | 必须显式配置服务器；只上传聚合快照 |
| `app/web.py` | 本地 Web UI 和 HTTP API | 默认监听本机地址；API 需保持隐私边界 |

## 4. 本地存储

默认数据库：

```text
data/winflow.sqlite
```

运行时目录规则：

- 源码树运行：默认使用仓库内 `data/` 和 `static/exe-icons/`，方便开发调试；
- 安装后运行：默认使用当前 Windows 用户数据目录，例如 `%LOCALAPPDATA%\Winflow\`，避免把用户数据库和本地图标写入 `site-packages`；
- 可用 `WINFLOW_DATA_DIR`、`WINFLOW_DB`、`WINFLOW_EXE_ICON_DIR` 覆盖。

主要表：

```text
meta
foreground_events
```

`foreground_events` 保存前台窗口采样结果。连续相同窗口会延长上一条记录，避免每个采样点都产生独立行。

默认被 Git 忽略的派生产物：

```text
data/*.sqlite
data/*.sqlite-*
data/icon_map.json
data/upload-pending/
logs/
static/exe-icons/
.env
```

内置 SVG 图标放在 `app/static/icons/apps/`，并通过 `pyproject.toml` 的 package data 随包分发；本机提取的 exe 图标缓存不属于 package data。

## 5. 隐私边界

公开 API 和上传快照不应包含：

- 真实 `window_title`；
- 真实 `exe_path`；
- 完整 URL；
- 浏览器标签页标题；
- 浏览器历史明细；
- 本机用户名、绝对路径、token。

新增功能如果扩大采集范围，必须满足：

1. 默认关闭；
2. 文档明确；
3. CLI 或 UI 明确提示；
4. 测试覆盖不泄露敏感字段；
5. `scripts/release_audit.py` 能拦截明显发布风险。

## 6. 活动带聚合思路

活动带不是精确计费器，而是个人回顾用的“时间段解释”。

当前规则：

- 以 15 分钟作为分析窗口；
- 应用累计停留超过 3 分钟形成活动带；
- 点事件命中次数达到阈值也可形成活动带；
- 同一事件之间间隔不超过 3 分钟则合并；
- 同一时间段允许多个活动带并存。

这种设计是为了适配真实 Windows 工作流：写代码、查资料、跑命令、聊天经常交替出现，不应被强行压成唯一事件。

## 7. 上传边界

上传是 opt-in：

```powershell
python -m app.main upload-usage --server-url https://example.com --token <token>
```

没有 `WINFLOW_SERVER_URL` 或 `--server-url` 时，上传命令会失败，不会默认上传到任何地址。

上传前，`app/uploader.py` 会尝试把本地 exe 图标上传到服务端图标接口，并把快照中的本地图标 URL 替换成服务端返回 URL。详见 [UPLOAD_API.md](UPLOAD_API.md)。

## 8. 发布前检查

发布或提交 PR 前至少运行：

```powershell
python -m compileall -q app tests scripts
python -m unittest discover -s tests
python scripts\release_audit.py
git diff --check
```

`release_audit.py` 会阻止常见发布风险，例如本地数据库、日志、exe 图标、浏览器历史读取残留、个人路径和 macOS 实现依赖进入公开候选文件。
