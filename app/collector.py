from __future__ import annotations

import threading
import time

from .config import DB_PATH
from .storage import init_db, record_foreground_window, safe_window_title
from .windows_activity import get_foreground_window

COLLECTOR_STATUS: dict[str, object] = {
    "running": False,
    "last_tick_ts": None,
    "last_window": None,
    "last_status": None,
    "last_error": None,
}


COLLECTOR_STOP_EVENT = threading.Event()


def _record_collector_tick(interval: int) -> None:
    """执行一次轻量窗口采集，并更新 Web 状态。

    当前只采集前台应用窗口，不再默认同步浏览器历史或具体标签页。
    """
    now = int(time.time())
    try:
        window = get_foreground_window()
        if window:
            status = record_foreground_window(window, now)
            COLLECTOR_STATUS.update(
                {
                    "last_tick_ts": now,
                    "last_window": window.process_name,
                    "last_status": status,
                    "last_error": None,
                }
            )
        else:
            COLLECTOR_STATUS.update(
                {
                    "last_tick_ts": now,
                    "last_window": None,
                    "last_status": "no-window",
                    "last_error": None,
                }
            )
    except Exception as exc:  # 防止后台采集线程因为单次 Win32/SQLite 异常退出
        COLLECTOR_STATUS.update(
            {
                "last_tick_ts": now,
                "last_status": "error",
                "last_error": str(exc),
            }
        )


def embedded_collect_loop(interval: int) -> None:
    """Web 服务内置采集循环，适合本地预览时一个命令同时跑 Web 和采集。"""
    init_db()
    COLLECTOR_STATUS.update(
        {
            "running": True,
            "last_error": None,
        }
    )
    try:
        while not COLLECTOR_STOP_EVENT.is_set():
            _record_collector_tick(interval)
            COLLECTOR_STOP_EVENT.wait(interval)
    finally:
        COLLECTOR_STATUS["running"] = False


def collect_once() -> None:
    init_db()
    window = get_foreground_window()
    if window:
        status = record_foreground_window(window)
        print(f"[window] {status}: {window.process_name} | {safe_window_title(window.process_name, window.title)}")
    else:
        print("[window] 未获取到前台窗口")


def collect_loop(interval: int) -> None:
    init_db()
    print(f"Winflow 采集中：DB={DB_PATH}，窗口间隔={interval}s，不同步浏览器历史。Ctrl+C 停止。")
    try:
        while True:
            now = time.time()
            window = get_foreground_window()
            if window:
                record_foreground_window(window, int(now))
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n采集已停止")
