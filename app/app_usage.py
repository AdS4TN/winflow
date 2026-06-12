from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from .exe_icon import icon_url_for_exe
from .icon_map import icon_for_app, load_icon_map
from .storage import connect, fetch_foreground_events
from .timeline import day_bounds

IDLE_THRESHOLD_SECONDS = 5 * 60
IGNORED_PROCESS_NAMES = {
    "lockapp.exe",
    "logonui.exe",
    "shellexperiencehost.exe",
    "searchhost.exe",
    "startmenuexperiencehost.exe",
    "credentialuibroker.exe",
}


@dataclass(frozen=True)
class ForegroundSegment:
    start_ts: int
    end_ts: int
    process_name: str
    app_name: str
    window_title: str = ""
    exe_path: str = ""


@dataclass
class AppUsage:
    app_name: str
    seconds: int = 0
    process_names: set[str] = field(default_factory=set)
    _exe_paths: set[str] = field(default_factory=set)

    def to_dict(
        self,
        *,
        icon_map: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {
            "app_name": self.app_name,
            "seconds": int(self.seconds),
            "process_names": sorted(self.process_names, key=str.lower),
        }
        item.update(icon_for_app(self.app_name, icon_map))
        if exe_icon := self._best_exe_icon():
            item["icon"] = exe_icon
            item["icon_source"] = "exe"
        else:
            item["icon_source"] = "map"
        return item

    def _best_exe_icon(self) -> str | None:
        for exe_path in sorted(self._exe_paths):
            if icon_url := icon_url_for_exe(exe_path, self.app_name):
                return icon_url
        return None


def normalize_app_name(process_name: str) -> str:
    """把 Windows 进程名归一成网站端更适合展示的软件名。"""
    raw = (process_name or "").strip()
    key = raw.lower()
    mapping = {
        "chrome.exe": "Chrome",
        "msedge.exe": "Edge",
        "brave.exe": "Brave",
        "firefox.exe": "Firefox",
        "code.exe": "VS Code",
        "code - insiders.exe": "VS Code Insiders",
        "cursor.exe": "Cursor",
        "windowsterminal.exe": "Windows Terminal",
        "wt.exe": "Windows Terminal",
        "powershell.exe": "PowerShell",
        "pwsh.exe": "PowerShell",
        "cmd.exe": "Command Prompt",
        "explorer.exe": "File Explorer",
        "wechat.exe": "WeChat",
        "weixin.exe": "WeChat",
        "qq.exe": "QQ",
        "tim.exe": "TIM",
        "notepad.exe": "Notepad",
        "notepad++.exe": "Notepad++",
        "obsidian.exe": "Obsidian",
        "typora.exe": "Typora",
    }
    if key in mapping:
        return mapping[key]
    if raw.lower().endswith(".exe"):
        return raw[:-4] or raw
    return raw or "Unknown"


def device_id() -> str:
    return os.environ.get("WINFLOW_DEVICE_ID") or os.environ.get("COMPUTERNAME") or "unknown-device"


def local_timezone_name() -> str:
    return time.tzname[0] if time.tzname else "local"


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


def _clamp_segment(row: Any, day_start_ts: int, day_end_ts: int) -> ForegroundSegment | None:
    start_ts = max(day_start_ts, int(_row_get(row, "start_ts", 0) or 0))
    end_ts = min(day_end_ts, int(_row_get(row, "end_ts", start_ts) or start_ts))
    if end_ts <= start_ts:
        return None
    process_name = str(_row_get(row, "process_name", "") or "Unknown")
    if process_name.strip().lower() in IGNORED_PROCESS_NAMES:
        return None
    return ForegroundSegment(
        start_ts=start_ts,
        end_ts=end_ts,
        process_name=process_name,
        app_name=normalize_app_name(process_name),
        window_title=str(_row_get(row, "window_title", "") or ""),
        exe_path=str(_row_get(row, "exe_path", "") or ""),
    )


def normalize_foreground_segments(
    rows: Iterable[Any],
    day_start_ts: int,
    day_end_ts: int,
) -> list[ForegroundSegment]:
    segments = [
        segment
        for row in rows
        if (segment := _clamp_segment(row, day_start_ts, day_end_ts)) is not None
    ]
    segments.sort(key=lambda item: (item.start_ts, item.end_ts, item.process_name))
    return segments


def _active_seconds_for_segment(segment: ForegroundSegment, idle_threshold_seconds: int) -> int:
    duration = max(0, int(segment.end_ts - segment.start_ts))
    if idle_threshold_seconds <= 0:
        return duration
    return min(duration, int(idle_threshold_seconds))


def build_usage_snapshot_from_rows(
    foreground_rows: Iterable[Any],
    day_start_ts: int,
    day_end_ts: int,
    *,
    day: str | None = None,
    idle_threshold_seconds: int = IDLE_THRESHOLD_SECONDS,
    now_ts: int | None = None,
) -> dict[str, Any]:
    """从本地原始记录生成准备上传的“当天完整统计快照”。

    隐私约束：不输出窗口标题、不输出 exe_path、不输出完整 URL；
    浏览器只按应用本身统计，不再下钻到具体标签页/站点。
    """
    segments = normalize_foreground_segments(foreground_rows, day_start_ts, day_end_ts)
    usage_by_app: dict[str, AppUsage] = {}

    for segment in segments:
        seconds = _active_seconds_for_segment(segment, idle_threshold_seconds)
        if seconds <= 0:
            continue
        usage = usage_by_app.setdefault(segment.app_name, AppUsage(app_name=segment.app_name))
        usage.seconds += seconds
        usage.process_names.add(segment.process_name)
        if segment.exe_path:
            usage._exe_paths.add(segment.exe_path)

    icon_map = load_icon_map()
    apps = [
        usage.to_dict(icon_map=icon_map)
        for usage in sorted(usage_by_app.values(), key=lambda item: item.seconds, reverse=True)
        if usage.seconds > 0
    ]
    active_seconds = sum(item["seconds"] for item in apps)
    generated_at = int(now_ts or time.time())
    return {
        "schema_version": 1,
        "device_id": device_id(),
        "day": day or datetime.fromtimestamp(day_start_ts).strftime("%Y-%m-%d"),
        "timezone": local_timezone_name(),
        "generated_at": generated_at,
        "window_start_ts": int(day_start_ts),
        "window_end_ts": int(day_end_ts),
        "idle_threshold_seconds": int(idle_threshold_seconds),
        "summary": {
            "active_seconds": int(active_seconds),
            "app_count": len(apps),
        },
        "apps": apps,
    }


def build_usage_snapshot(
    day: str | None = None,
    *,
    idle_threshold_seconds: int = IDLE_THRESHOLD_SECONDS,
) -> dict[str, Any]:
    if day is None:
        day = latest_recorded_day() or datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d")
    start_ts, end_ts = day_bounds(day)
    return build_usage_snapshot_from_rows(
        fetch_foreground_events(start_ts, end_ts),
        start_ts,
        end_ts,
        day=datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d"),
        idle_threshold_seconds=idle_threshold_seconds,
    )


def latest_recorded_day() -> str | None:
    with connect() as con:
        fg_max = con.execute("SELECT MAX(start_ts) AS ts FROM foreground_events").fetchone()["ts"]
    latest_ts = int(fg_max) if fg_max is not None else None
    if latest_ts is None:
        return None
    return datetime.fromtimestamp(latest_ts).strftime("%Y-%m-%d")
