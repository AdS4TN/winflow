## 变更摘要

-

## 验证

- [ ] `python -m compileall -q app tests scripts`
- [ ] `python -m unittest discover -s tests`
- [ ] `python scripts/release_audit.py`
- [ ] `python scripts/package_audit.py`

## 隐私检查

- [ ] 没有提交本地数据库、日志、图标缓存或 `.env`
- [ ] 没有新增默认上传行为
- [ ] 没有新增默认浏览器历史读取
- [ ] 没有在应用统计接口输出窗口标题、exe 路径或完整 URL

## 备注

-
