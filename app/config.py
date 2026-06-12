from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Winflow"
PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
PACKAGE_STATIC_DIR = PACKAGE_ROOT / "static"
SOURCE_STATIC_DIR = PROJECT_ROOT / "static"


def _is_source_tree() -> bool:
    """判断当前是否在仓库源码目录中运行。

    源码树运行时保留旧的 `data/` 与 `static/exe-icons/` 位置，方便开发和
    本地预览；安装到 site-packages 后则不能把用户数据写进包目录。
    """
    return (PROJECT_ROOT / ".git").exists() or (PROJECT_ROOT / "pyproject.toml").exists()


def _windows_user_data_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if root:
        return Path(root) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def _default_data_dir() -> Path:
    if _is_source_tree():
        return PROJECT_ROOT / "data"
    return _windows_user_data_dir()


DATA_DIR = Path(os.environ.get("WINFLOW_DATA_DIR", _default_data_dir()))
DB_PATH = Path(os.environ.get("WINFLOW_DB", DATA_DIR / "winflow.sqlite"))


def _default_exe_icon_dir() -> Path:
    if _is_source_tree():
        return SOURCE_STATIC_DIR / "exe-icons"
    return DATA_DIR / "exe-icons"


EXE_ICON_DIR = Path(os.environ.get("WINFLOW_EXE_ICON_DIR", _default_exe_icon_dir()))
DEFAULT_COLLECT_INTERVAL_SECONDS = 5

# 限制存储的前台窗口标题长度，降低隐私风险。
MAX_WINDOW_TITLE_LENGTH = 300

# 活动带聚合参数。
ACTIVITY_BUCKET_SECONDS = 15 * 60
ACTIVITY_MIN_ACTIVE_SECONDS = 3 * 60
ACTIVITY_MIN_HIT_COUNT = 5
ACTIVITY_MERGE_GAP_SECONDS = 3 * 60
ACTIVITY_POINT_EVENT_SECONDS = 30
ACTIVITY_MAX_SAMPLE_COUNT = 5
