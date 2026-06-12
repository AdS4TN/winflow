# Winflow 排障指南

本文记录当前 Windows-first alpha 版本最常见的问题和排查方式。

## 1. 本地页面没有数据

先确认数据库已初始化，并且采集器正在运行：

```powershell
python -m app.main init
python -m app.main serve --with-collector
```

打开：

```text
http://127.0.0.1:8765
http://127.0.0.1:8765/usage
```

如果你把采集器和 Web 服务拆开运行，需要两个 PowerShell：

```powershell
python -m app.main collect --interval 5
```

```powershell
python -m app.main serve
```

可以用只读命令确认当天是否有统计：

```powershell
python -m app.main usage
python -m app.main bands
```

## 2. 采集器看起来没有更新

检查以下几点：

- Web 页面是否是旧缓存，尝试刷新页面；
- 是否有另一个进程占用了旧数据库；
- 是否设置了 `WINFLOW_DB`，导致 CLI 和 Web 服务读写不同数据库；
- 是否设置了 `WINFLOW_DATA_DIR`，导致数据目录不在仓库 `data/` 下；
- 是否正在锁屏、登录界面、凭据输入界面，这些系统窗口会被过滤；
- 是否有权限读取前台窗口所属进程路径，读取失败时仍应保留进程名。

快速验证当前前台窗口采集：

```powershell
python -m app.main once
python -m app.main usage
```

## 3. 浏览器没有显示具体标签页

这是当前默认设计，不是故障。

Winflow 公开版本默认按浏览器应用统计，例如 Chrome、Edge、Firefox，不展示标签页标题、站点域名或完整 URL。原因是浏览器窗口标题通常包含页面标题，容易泄露个人内容。

如果未来要支持更细粒度浏览器统计，必须是 opt-in，并且需要单独的文档、设置入口和隐私测试。

## 4. 锁屏、登录、凭据窗口不应计入统计

当前会过滤这些系统进程：

```text
lockapp.exe
logonui.exe
credentialuibroker.exe
shellexperiencehost.exe
searchhost.exe
startmenuexperiencehost.exe
```

如果看到类似系统进程进入统计，优先检查：

- 进程名大小写或别名是否不同；
- 是否来自已有旧数据库记录；
- 是否需要删除本地数据库重新采集验证。

## 5. 图标看起来不对或太小

Winflow 会优先从 Windows 桌面快捷方式或开始菜单快捷方式寻找更合适的图标源，然后导出 PNG 并做透明边界裁剪。

本地图标缓存位置：

```text
static/exe-icons/
```

这是源码目录运行时的默认位置；安装后运行时默认在 `%LOCALAPPDATA%\Winflow\exe-icons\`。也可以通过 `WINFLOW_EXE_ICON_DIR` 覆盖。

如果图标异常，可以停止服务后删除缓存，再重新打开应用采集：

```powershell
Remove-Item static\exe-icons\* -Exclude .gitkeep
python -m app.main serve --with-collector
```

注意：`static/exe-icons/` 是本机派生产物，不应提交到 Git。

## 6. 上传命令失败

上传默认关闭。缺少服务器地址时失败是预期行为。

正确方式：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```text
WINFLOW_SERVER_URL=https://example.com
WINFLOW_UPLOAD_TOKEN=replace-with-a-long-random-token
WINFLOW_DEVICE_ID=my-windows-pc
```

然后运行：

```powershell
python -m app.main upload-usage
```

如果上传失败，待上传快照会放在：

```text
data/upload-pending/
```

之后可以重试：

```powershell
python -m app.main upload-usage --retry-pending
```

## 7. 发布前发现本地文件很多

正常开发过程中会出现数据库、日志和本地图标缓存。它们默认不应提交。

发布前运行：

```powershell
python scripts\release_audit.py
git status --short
```

确认不要提交：

```text
data/
logs/
static/exe-icons/*.png
static/exe-icons/*.ico
.env
winflow-uploader*.log
docs/internal/
```
