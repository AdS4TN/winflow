# 可选上传 API

Winflow 默认本地运行，不上传任何数据。上传功能只面向用户自己的自托管服务端，并且必须显式配置。

## 1. 客户端配置

复制 `.env.example` 为 `.env`：

```powershell
Copy-Item .env.example .env
```

配置：

```text
WINFLOW_SERVER_URL=https://example.com
WINFLOW_UPLOAD_TOKEN=replace-with-a-long-random-token
WINFLOW_DEVICE_ID=my-windows-pc
```

运行：

```powershell
python -m app.main upload-usage
python -m app.main upload-usage --watch --interval 300
```

没有 `WINFLOW_SERVER_URL` 或 `--server-url` 时，命令会失败，不会默认上传到任何地址。

## 2. 快照接口

客户端会 POST：

```text
POST /api/winflow/snapshots
Authorization: Bearer <WINFLOW_UPLOAD_TOKEN>
Content-Type: application/json
```

请求体示例：

```json
{
  "schema_version": 1,
  "device_id": "my-windows-pc",
  "day": "2026-06-08",
  "timezone": "China Standard Time",
  "generated_at": 1780915200,
  "window_start_ts": 1780848000,
  "window_end_ts": 1780934399,
  "idle_threshold_seconds": 300,
  "summary": {
    "active_seconds": 7200,
    "app_count": 4
  },
  "apps": [
    {
      "app_name": "VS Code",
      "seconds": 3600,
      "process_names": ["Code.exe"],
      "icon": "/static/icons/apps/vscode.svg",
      "icon_source": "map",
      "color": "#3b82f6",
      "text_color": "#eff6ff"
    }
  ]
}
```

服务端建议返回：

```json
{"ok": true}
```

## 3. 图标接口

如果快照中包含本地 exe 图标 URL，客户端会先上传图标：

```text
POST /api/winflow/icons
Authorization: Bearer <WINFLOW_UPLOAD_TOKEN>
Content-Type: application/json
```

请求体：

```json
{
  "hash": "sha256",
  "filename": "code-xxxx.png",
  "data": "base64-encoded-image"
}
```

服务端返回：

```json
{"url": "https://example.com/winflow/icons/code-xxxx.png"}
```

客户端会把快照中的本地图标路径替换成返回的远端 URL。

## 4. 隐私边界

上传快照不应包含：

- 窗口标题；
- 真实 exe 路径；
- 完整 URL；
- 浏览器标签页标题；
- 浏览器历史明细。

服务端也不应要求客户端上传这些字段。
