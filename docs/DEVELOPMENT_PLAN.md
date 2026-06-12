# Winflow 开发计划

Winflow 是一个 Windows-first、local-first 的自动工作日志项目。它参考 Dayflow 的产品成熟度与开源表达方式，但不复刻 macOS 的屏幕录制/Swift 技术路线，也不把 Dayflow 的平台实现当作迁移目标。

项目边界要始终保持清楚：Dayflow 是产品灵感来源，Winflow 是 Windows 原生实现。所有采集、图标、启动、托盘、自启动和打包设计，都应优先围绕 Windows 10/11 的桌面运行环境展开。

## 1. 产品目标

Winflow 要解决的问题是：用户不想手动记时间，但希望在一天结束后知道自己大概做了什么、在哪些应用之间切换、某段工作大约持续了多久。

当前阶段的核心目标：

- 在 Windows 上稳定采集前台应用窗口；
- 将原始事件聚合为可理解的活动带；
- 展示本地 Web 时间线和应用使用统计；
- 默认本地保存，默认不上传；
- 默认不截图、不读取浏览器历史、不展示浏览器标签页明细。

## 2. 非目标

当前阶段不做：

- macOS 支持；
- 屏幕截图或录屏；
- OCR；
- 默认 AI/LLM 总结；
- 默认浏览器历史读取；
- 默认云端同步；
- 企业级多用户权限系统。

## 3. 当前技术栈

- Python 3.11+；
- Windows Win32 API via `ctypes`；
- SQLite；
- 标准库 `http.server` 提供本地 Web UI；
- Pillow 用于 exe 图标后处理；
- `unittest` 做核心算法测试。

## 4. 当前模块

```text
app/
  main.py              # CLI 入口与命令编排
  collector.py         # Windows 前台窗口采集循环与状态
  web.py               # 本地 Web UI、HTTP handler 与 API
  windows_activity.py  # 读取 Windows 前台窗口、进程名和 exe 路径
  storage.py           # SQLite schema、原始事件写入与查询
  activity_bands.py    # 活动带聚合算法
  app_usage.py         # 应用级使用统计快照
  exe_icon.py          # 本地 exe/快捷方式图标提取
  icon_map.py          # 图标映射与 fallback
  uploader.py          # 可选自托管上传
tests/
  test_activity_bands.py
  test_app_usage.py
```

## 5. 数据边界

默认本地数据库：

```text
data/winflow.sqlite
```

默认被 Git 忽略的本地派生产物：

```text
data/*.sqlite
data/*.sqlite-*
data/icon_map.json
data/upload-pending/
logs/
static/exe-icons/
.env
```

原因：这些内容可能包含用户本机活动痕迹、派生图标或上传凭据。

## 6. 隐私默认值

默认流程只记录前台应用活动。浏览器按应用统计，不按站点或标签页统计。本地 HTTP API 不能输出：

- `window_title`；
- `exe_path`；
- 完整 URL；
- 浏览器标签页标题；
- 浏览器历史明细。

任何扩大采集范围的功能都必须满足：

1. 默认关闭；
2. 文档明确；
3. UI/CLI 明确提示；
4. 测试覆盖不泄露敏感字段。

## 7. 活动带算法

活动带用于把细碎切屏事件转成更接近人类理解的时间段。

当前规则：

- 15 分钟分析窗口；
- 应用累计停留超过 3 分钟形成活动带；
- 点事件命中次数达到阈值也可形成活动带；
- 同一事件间隔不超过 3 分钟则合并；
- 同一时间段允许多个活动带并存。

后续优化：

- 更准确的 idle/锁屏识别；
- 更合理的跨窗口合并策略；
- 可配置阈值；
- 更易解释的调试输出。

## 8. 开源发布优先级

### P0：可信发布基线

- README、LICENSE、PRIVACY、SECURITY、CONTRIBUTING、ROADMAP；
- CI 跑 compile 与 unit tests；
- `.gitignore` 阻止本地数据泄露；
- 上传模块默认无目标即失败；
- 清理个人路径和个人化服务绑定表述。

### P1：工程拆分

- 已完成：`app/main.py` 保留 CLI 编排，采集循环拆到 `collector.py`，本地 Web UI/API 拆到 `web.py`；
- 下一步：HTML/CSS/JS 继续移到 `static/` 或模板文件；
- 明确 API schema；
- 增加更细的单元测试。

### P2：Windows 产品体验

- 托盘图标；
- 开机自启动；
- Windows installer 或源码目录运行以外的分发方式；
- 本地设置页面；
- 数据保留期；
- 更好的异常提示和采集状态。

### P3：可选同步和总结

- 自托管上传协议；
- 服务端示例；
- 本地-only 总结实验；
- 可插拔 provider，但不得改变默认隐私边界。

## 9. 测试策略

最低验证：

```powershell
python -m compileall -q app tests scripts
python -m unittest discover -s tests
python scripts/release_audit.py
python scripts/package_audit.py
```

重点测试：

- 活动带阈值与合并；
- 浏览器窗口标题脱敏；
- 应用统计不泄露私有字段；
- 锁屏/凭据/系统壳进程过滤；
- 上传模块无显式配置时失败；
- 图标缓存文件名不泄露绝对路径。
