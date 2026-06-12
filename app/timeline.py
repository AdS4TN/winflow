from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .storage import fetch_foreground_events, fetch_stats, safe_window_title


@dataclass(frozen=True)
class TimelineItem:
    start_ts: int
    end_ts: int
    kind: str
    title: str
    subtitle: str
    detail: str
    source: str


def day_bounds(day: str | None = None) -> tuple[int, int]:
    if day:
        d = datetime.strptime(day, "%Y-%m-%d").date()
    else:
        d = date.today()
    start = datetime.combine(d, datetime.min.time())
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return int(start.timestamp()), int(end.timestamp())


def fmt_time(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def _safe_timeline_item_title(process_name: str) -> str:
    return process_name or "Unknown"


def _safe_timeline_item_subtitle(process_name: str, window_title: str | None) -> str:
    title = safe_window_title(process_name, window_title)
    if title == "浏览器窗口":
        return title
    return "前台应用窗口"


def build_timeline(day: str | None = None) -> dict:
    start_ts, end_ts = day_bounds(day)
    foreground = fetch_foreground_events(start_ts, end_ts)
    items: list[TimelineItem] = []

    for row in foreground:
        s = max(start_ts, int(row["start_ts"]))
        e = min(end_ts, int(row["end_ts"] or row["start_ts"]))
        process = row["process_name"] or "Unknown"
        items.append(
            TimelineItem(
                start_ts=s,
                end_ts=e,
                kind="app",
                title=_safe_timeline_item_title(process),
                subtitle=_safe_timeline_item_subtitle(process, row["window_title"]),
                detail="",
                source="foreground",
            )
        )

    items.sort(key=lambda item: (item.start_ts, item.kind))
    stats = fetch_stats(start_ts, end_ts)
    return {
        "day": datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d"),
        "start_ts": start_ts,
        "end_ts": end_ts,
        "generated_at": int(time.time()),
        "items": [item.__dict__ for item in items],
        "stats": stats,
    }


def build_summary_text(day: str | None = None) -> str:
    data = build_timeline(day)
    lines = [f"# {data['day']} 访问轨迹", ""]
    lines.append("## 应用使用排行")
    for app in data["stats"]["apps"][:10]:
        minutes = int((app["seconds"] or 0) / 60)
        lines.append(f"- {app['process_name']}: {minutes} 分钟，{app['count']} 段")
    lines.append("")
    lines.append("## 时间线")
    for item in data["items"]:
        lines.append(f"- {fmt_time(item['start_ts'])}-{fmt_time(item['end_ts'])} [{item['subtitle']}] {item['title']}")
    return "\n".join(lines)
