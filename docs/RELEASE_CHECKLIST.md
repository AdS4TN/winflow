# GitHub 发布检查清单

发布 Winflow 前，请按此清单逐项确认。目标是把项目作为 Windows-first、local-first、隐私默认安全的开源项目发布。

## 1. 定位与文档

- [ ] README 明确说明 Winflow 是 Windows-first 项目。
- [ ] README 明确说明 Dayflow 只作为产品体验和开源成熟度参考，不作为 macOS 技术栈迁移目标。
- [ ] README 明确说明当前 alpha 仍推荐源码目录运行，并说明 package audit 覆盖安装态基础路径。
- [ ] README 包含快速开始、常用命令、本地数据位置、隐私默认值、API 入口。
- [ ] `PRIVACY.md` 明确默认不截图、不录屏、不 OCR、不调用 AI、不读取浏览器历史、不上传。
- [ ] `SECURITY.md` 包含安全问题报告方式。
- [ ] `CONTRIBUTING.md` 包含本地开发、测试和隐私边界要求。
- [ ] `ROADMAP.md` 区分 P0/P1/P2/P3。
- [ ] `docs/ARCHITECTURE.md` 能解释 Windows 采集、存储、聚合、图标和上传模块。
- [ ] `docs/TROUBLESHOOTING.md` 覆盖无数据、采集不更新、图标异常和上传失败等常见问题。
- [ ] `docs/GITHUB_RELEASE_GUIDE.md` 区分自动检查和 GitHub 页面上的人工发布动作。
- [ ] `docs/API_SCHEMA.md` 与当前本地 HTTP API 一致。
- [ ] `docs/UPLOAD_API.md` 与 uploader 的实际上传 payload 一致。

## 2. 隐私与本地数据

- [ ] `.gitignore` 忽略 `data/*.sqlite`、`data/icon_map.json`、`logs/`、`.env`、`static/exe-icons/*`。
- [ ] 根目录临时日志如 `winflow-uploader*.log` 已忽略。
- [ ] 仓库中没有真实本机数据库、日志、提取出的 exe 图标或个人草稿。
- [ ] `WINFLOW_DATA_DIR`、`WINFLOW_DB`、`WINFLOW_EXE_ICON_DIR` 的行为已在 README、隐私文档和架构文档说明。
- [ ] `/api/apps/usage` 和 `/api/timeline` 不输出 `window_title`、`exe_path`、完整 URL、浏览器标签页标题或站点明细。
- [ ] 公开应用中不存在浏览器历史读取模块、CLI 命令或上传字段。
- [ ] 上传模块缺少 `WINFLOW_SERVER_URL` 或显式 `--server-url` 时会失败，不会默认上传。

## 3. Windows-first 边界

- [ ] 核心实现使用 Windows 前台窗口、进程名、exe 图标和 SQLite。
- [ ] 没有引入 macOS/Swift/ScreenCaptureKit/AVFoundation 作为实现依赖。
- [ ] CI 至少在 `windows-latest` 上运行。
- [ ] README 的安装命令使用 PowerShell 示例。
- [ ] 如果要发布 PyPI 包、Windows installer 或全局 `winflow` 命令，需要先通过 `scripts/package_audit.py` 验证静态资源路径、本地数据目录和图标缓存目录。
- [ ] `app/static/icons/apps/*.svg` 已作为 package data 声明；`static/exe-icons/` 不作为 package data 发布。

## 4. 测试与检查

发布前至少运行：

```powershell
python -m compileall -q app tests scripts
python -m unittest discover -s tests
python scripts/release_audit.py
python scripts/package_audit.py
git diff --check
```

建议额外运行：

```powershell
python -m app.main --help
python -m app.main usage
python -m app.main bands
```

## 5. GitHub 仓库设置

- [ ] 将 README 和 `pyproject.toml` 中的 `https://github.com/OWNER/winflow` 替换为真实 GitHub 仓库地址。
- [ ] 按 `docs/GITHUB_RELEASE_GUIDE.md` 完成首次发布流程。
- [ ] 默认分支建议为 `main`。
- [ ] 开启 GitHub Actions。
- [ ] 添加项目描述：`Windows-first local automatic work journal`。
- [ ] 添加 topics：`windows`、`local-first`、`time-tracking`、`activity-tracker`、`sqlite`、`privacy`。
- [ ] 发布前新建截图或 GIF，放在 `docs/assets/` 或 README 使用外链。

## 6. 首次 release 建议

- [ ] tag：`v0.1.0-alpha`。
- [ ] release notes 明确这是早期 Windows 本地预览版。
- [ ] 明确不承诺精确计费，只用于个人回顾。
- [ ] 标注默认不会上传，上传需用户自托管并显式配置。
