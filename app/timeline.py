from __future__ import annotations

import calendar
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

from .storage import fetch_browser_visits, fetch_foreground_events, fetch_stats


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


def domain_of(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or url[:60]


def build_timeline(day: str | None = None) -> dict:
    start_ts, end_ts = day_bounds(day)
    foreground = fetch_foreground_events(start_ts, end_ts)
    visits = fetch_browser_visits(start_ts, end_ts)
    items: list[TimelineItem] = []

    for row in foreground:
        s = max(start_ts, int(row["start_ts"]))
        e = min(end_ts, int(row["end_ts"] or row["start_ts"]))
        title = row["window_title"] or "无窗口标题"
        process = row["process_name"] or "Unknown"
        items.append(
            TimelineItem(
                start_ts=s,
                end_ts=e,
                kind="app",
                title=title,
                subtitle=process,
                detail=row["exe_path"] or "",
                source="foreground",
            )
        )

    for row in visits:
        title = row["title"] or domain_of(row["url"])
        browser = f"{row['browser']} / {row['profile']}"
        items.append(
            TimelineItem(
                start_ts=int(row["visit_ts"]),
                end_ts=int(row["visit_ts"]),
                kind="web",
                title=title,
                subtitle=domain_of(row["url"]),
                detail=row["url"],
                source=browser,
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
        if item["kind"] == "app":
            lines.append(f"- {fmt_time(item['start_ts'])}-{fmt_time(item['end_ts'])} [{item['subtitle']}] {item['title']}")
        else:
            lines.append(f"- {fmt_time(item['start_ts'])} [Web:{item['source']}] {item['subtitle']} - {item['title']}")
    return "\n".join(lines)
