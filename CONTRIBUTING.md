# 贡献指南

感谢你考虑贡献 Winflow。这个项目的方向是 Windows-first、local-first、隐私默认安全的自动工作日志。

## 开发原则

- 优先支持 Windows 10/11；
- 默认不上传、不截图、不读取浏览器历史；
- 任何可能扩大隐私范围的功能都必须是 opt-in；
- 不提交本地数据库、日志、提取出的 exe 图标或 `.env`；
- 代码尽量保持小步、可测试、可回滚。

## 本地开发

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main init
python -m app.main serve --with-collector
```

## 测试

提交前请至少运行：

```powershell
python -m compileall -q app tests scripts
python -m unittest discover -s tests
python scripts/release_audit.py
python scripts/package_audit.py
```

## Pull Request 建议

PR 请说明：

- 改了什么；
- 为什么需要改；
- 是否影响隐私边界；
- 是否新增或更新测试；
- 是否需要迁移已有本地数据。

如果是大功能，例如托盘、自启动、上传协议、AI 总结，请先开 issue 讨论范围。
