# 隐私说明

Winflow 的默认设计是 local-first：先把数据留在你的 Windows 电脑上，只有你显式开启上传时才离开本机。

## 默认会记录什么

默认采集器记录 Windows 前台窗口事件：

- 开始时间与结束时间；
- 进程名；
- 窗口句柄和进程 ID；
- exe 路径，仅用于本地图标提取；
- 窗口标题，但浏览器窗口会被脱敏为固定文案。

这些原始数据保存在本地 SQLite 数据库：

```text
data/winflow.sqlite
```

源码目录运行时默认使用仓库内 `data/`。如果通过安装后的 `winflow` 命令运行，默认会使用当前 Windows 用户数据目录，例如 `%LOCALAPPDATA%\Winflow\`。也可以通过 `WINFLOW_DATA_DIR` 或 `WINFLOW_DB` 显式覆盖。

## 默认不会做什么

默认情况下，Winflow 不会：

- 截图；
- 录屏；
- 录音；
- OCR；
- 调用 AI/LLM；
- 读取浏览器历史；
- 上传服务器；
- 展示浏览器具体标签页、站点域名或完整 URL；
- 在本地 HTTP API 中输出真实 `window_title`、`exe_path` 或完整 URL。

## 浏览器处理

浏览器进程会按应用统计，例如 Chrome、Edge、Firefox，而不是按标签页或站点统计。浏览器窗口标题默认会被替换为固定文案，避免把标签页标题泄露到活动带或统计接口中。

当前公开应用不包含浏览器历史读取模块，也不会创建、读取或上传浏览器历史明细。

## 本地图标缓存

Winflow 会尝试从 exe 或桌面快捷方式提取应用图标，并缓存到：

```text
static/exe-icons/
```

源码目录运行时默认使用上面的目录；安装后运行时默认使用用户数据目录下的 `exe-icons/`。也可以通过 `WINFLOW_EXE_ICON_DIR` 显式覆盖。图标缓存是本机派生产物，默认已被 `.gitignore` 忽略。

## 可选上传

上传是 opt-in。只有当你显式配置：

```text
WINFLOW_SERVER_URL
WINFLOW_UPLOAD_TOKEN
```

并运行 `python -m app.main upload-usage` 时，Winflow 才会上传聚合后的应用统计快照。

上传快照默认只包含应用级统计，不包含窗口标题、真实 exe 路径、完整 URL 或浏览器标签页明细。

## 删除数据

停止 Winflow 后，你可以直接删除本地数据库和派生产物：

```powershell
Remove-Item data\winflow.sqlite*
Remove-Item data\icon_map.json
Remove-Item static\exe-icons\* -Exclude .gitkeep
```

如果你使用的是安装后默认目录，也可以删除：

```powershell
Remove-Item "$env:LOCALAPPDATA\Winflow" -Recurse
```

删除前请确认你不再需要这些本地记录。
