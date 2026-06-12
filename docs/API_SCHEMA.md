# 本地 HTTP API Schema

Winflow 的本地 Web 服务默认监听 `127.0.0.1:8765`。这些接口面向本机预览、个人网站本地代理，或用户自建工具接入。

> 隐私边界：默认接口不应输出浏览器标签页标题、站点域名、完整 URL、真实 `exe_path` 或原始 `window_title`。如果后续新增字段，必须先更新本文档和测试。

## 通用约定

- 日期参数：`day=YYYY-MM-DD`，省略时使用本机当天。
- 时间戳：Unix timestamp，单位秒。
- 返回编码：`application/json; charset=utf-8`，Markdown 导出除外。
- 缓存：服务端返回 `Cache-Control: no-store`。

## `GET /api/apps/usage`

应用级使用统计。适合个人网站展示“今天用了哪些软件、用了多久”。

### Query

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `day` | string | 今天 | 日期，格式 `YYYY-MM-DD` |
| `idle_threshold_seconds` | integer | `300` | 两段活动之间超过该间隔会被视为空闲切分 |

### Response

```json
{
  "schema_version": 1,
  "device_id": "local-windows-pc",
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

### 不应出现的字段

- `window_title`
- `exe_path`
- `url`
- `sites`
- 浏览器标签页标题
- 浏览器历史明细

## `GET /api/bands`

活动带聚合结果，用于回答“某段时间大概在做什么”。

### Query

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `day` | string | 今天 | 日期，格式 `YYYY-MM-DD` |

### Response 结构

```json
{
  "schema_version": 1,
  "day": "2026-06-08",
  "start_ts": 1780848000,
  "end_ts": 1780934399,
  "generated_at": 1780915200,
  "range": {
    "start_ts": 1780848000,
    "end_ts": 1780934399
  },
  "stats": {
    "top_bands": [],
    "by_type": []
  },
  "bands": [
    {
      "id": "app:vscode:1780900000",
      "event_key": "app:vscode:1780900000",
      "kind": "app",
      "event_type": "app",
      "title": "VS Code",
      "subtitle": "编辑器",
      "detail": "",
      "start_ts": 1780900000,
      "end_ts": 1780903600,
      "total_active_seconds": 2400,
      "hit_count": 12,
      "sample_titles": [],
      "sample_details": []
    }
  ]
}
```

浏览器窗口标题会被脱敏为固定文案。`detail` 与 samples 不能包含真实 `exe_path` 或完整 URL。

锁屏、凭据输入等 Windows 系统界面不代表真实用户任务，会被过滤，不应生成活动带。

## `GET /api/timeline`

安全化前台事件时间线。该接口用于本地控制台展示比活动带更细的前台切换节奏，但默认仍不输出真实窗口标题或 exe 绝对路径。

### Query

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `day` | string | 今天 | 日期，格式 `YYYY-MM-DD` |

### Response 结构

```json
{
  "day": "2026-06-08",
  "start_ts": 1780848000,
  "end_ts": 1780934399,
  "generated_at": 1780915200,
  "items": [
    {
      "start_ts": 1780900000,
      "end_ts": 1780900300,
      "kind": "app",
      "title": "Code.exe",
      "subtitle": "前台应用窗口",
      "detail": "",
      "source": "foreground"
    },
    {
      "start_ts": 1780900300,
      "end_ts": 1780900600,
      "kind": "app",
      "title": "chrome.exe",
      "subtitle": "浏览器窗口",
      "detail": "",
      "source": "foreground"
    }
  ],
  "stats": {
    "apps": [],
    "browsers": []
  }
}
```

### 隐私提示

该接口可以包含进程名，但不应包含真实窗口标题、真实 `exe_path`、完整 URL、浏览器站点或标签页标题。对外网站集成优先使用 `/api/apps/usage` 或可选上传快照。

## `GET /api/collector/status`

内置采集器状态。

```json
{
  "running": true,
  "last_tick_ts": 1780915200,
  "last_window": "Chrome.exe",
  "last_status": "extended",
  "last_error": null
}
```

## `GET /api/icon-map`

返回应用图标映射和 fallback 结果，主要供本地 UI 使用。该接口不应返回真实 exe 绝对路径。

## `GET /api/export`

返回 Markdown 摘要：`text/markdown; charset=utf-8`。

## 适合个人网站接入的推荐方式

1. 本机 Winflow 运行采集与统计。
2. 使用 `python -m app.main upload-usage` 将聚合后的 `/api/apps/usage` 快照上传到你的自托管服务端。
3. 个人网站只读取服务端保存的聚合快照。

这样网站不需要直连你的电脑，也不会接触原始窗口标题或 exe 路径。
