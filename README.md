# Winflow

Windows 本地活动轨迹 MVP：记录前台窗口、同步浏览器历史，并在本地网页查看当天时间线。

## 快速开始

```powershell
cd C:\Users\28377\Desktop\winflow
python -m app.main init
python -m app.main collect
# 另开一个终端
python -m app.main serve
```

打开：http://127.0.0.1:8765

## 命令

- `python -m app.main init`：初始化 SQLite 数据库
- `python -m app.main once`：采集一次当前前台窗口并同步浏览器历史
- `python -m app.main collect --interval 5`：持续采集，默认每 5 秒一次
- `python -m app.main sync-browsers`：仅同步浏览器历史
- `python -m app.main serve --port 8765`：启动本地 Web UI

## 数据位置

默认数据库：`data/winflow.sqlite`
