# Changelog

本项目采用轻量变更日志。发布版本后请在这里记录用户可见变化。

## Unreleased

- 明确 Winflow 是 Windows-first、local-first 的自动工作日志；
- 加固上传模块：没有 `WINFLOW_SERVER_URL` 或 `--server-url` 时不会默认上传；
- 移除上传模块中的个人路径搜索；
- 移除默认浏览器历史读取模块，浏览器只按应用统计；
- 增加 `WINFLOW_DATA_DIR`、`WINFLOW_DB`、`WINFLOW_EXE_ICON_DIR` 运行时路径配置；
- 将内置 SVG 图标移入 `app/static/` 并通过 package data 分发；
- 增加 `scripts/release_audit.py` 与 `scripts/package_audit.py`，用于发布前隐私、路径、打包和安装态 smoke 检查；
- `.gitignore` 忽略本地数据库、日志、待上传快照、exe 图标缓存和 `.env`；
- 补齐 README、架构说明、排障指南、隐私说明、安全策略、贡献指南、路线图、CI 和 GitHub 模板。
