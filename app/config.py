from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Winflow"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = Path(os.environ.get("WINFLOW_DB", DATA_DIR / "winflow.sqlite"))
DEFAULT_COLLECT_INTERVAL_SECONDS = 5
DEFAULT_BROWSER_SYNC_INTERVAL_SECONDS = 300

# 为了减少隐私风险，窗口标题默认最多存 300 字符。
MAX_WINDOW_TITLE_LENGTH = 300

# 浏览器历史只同步最近 N 天。
BROWSER_HISTORY_LOOKBACK_DAYS = int(os.environ.get("WINFLOW_HISTORY_DAYS", "14"))

# 活动带聚合参数。
ACTIVITY_BUCKET_SECONDS = 15 * 60
ACTIVITY_MIN_ACTIVE_SECONDS = 3 * 60
ACTIVITY_MIN_HIT_COUNT = 5
ACTIVITY_MERGE_GAP_SECONDS = 3 * 60
ACTIVITY_POINT_EVENT_SECONDS = 30
ACTIVITY_MAX_SAMPLE_COUNT = 5
