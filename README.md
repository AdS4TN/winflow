# Winflow

Windows 本地活动轨迹 MVP：记录前台窗口、同步浏览器历史，并在本地网页查看当天“活动带”时间线。

这个项目当前不追求秒级精确用量，而是回答：

> 某个时间点我大概在做什么？某个事件从什么时候持续到什么时候？

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
- `python -m app.main bands`：输出今天的活动带 JSON
- `python -m app.main bands --day 2026-05-18`：输出指定日期活动带
- `python -m app.main export`：导出原始时间线 Markdown

## 活动带规则

Web UI 默认显示“活动带”，并保留“原始事件”切换。

当前规则：

- 以 15 分钟作为分析窗口。
- 应用事件在窗口内累计停留超过 3 分钟，会形成活动带。
- 网页事件在窗口内同域名访问次数达到 5 次，也会形成活动带。
- 同一事件之间间隔不超过 3 分钟，会自动合并。
- 一段时间可以同时存在多个活动带，用来表达频繁切屏、查资料、跑命令等并行上下文。

## 数据位置

默认数据库：`data/winflow.sqlite`

## 隐私说明

- 数据保存在本机 SQLite。
- 当前版本不截屏、不做 OCR。
- 浏览器历史读取采用“复制数据库副本后只读分析”的方式，不直接写浏览器数据库。
