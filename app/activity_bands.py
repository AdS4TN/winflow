from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable
from urllib.parse import urlparse

from . import config
from .storage import fetch_browser_visits, fetch_foreground_events
from .timeline import day_bounds


@dataclass(frozen=True)
class NormalizedEvent:
    event_key: str
    event_type: str
    start_ts: int
    end_ts: int
    title: str
    subtitle: str
    detail: str
    source: str


@dataclass
class ActivityBand:
    event_key: str
    event_type: str
    start_ts: int
    end_ts: int
    title: str
    subtitle: str
    detail: str
    total_active_seconds: int
    hit_count: int
    sample_titles: list[str]
    sample_details: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _BucketStat:
    event: NormalizedEvent
    start_ts: int
    end_ts: int
    total_active_seconds: int = 0
    hit_count: int = 0
    sample_titles: list[str] | None = None
    sample_details: list[str] | None = None


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    """兼容 sqlite3.Row、dict 和测试用简单对象。"""
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


def _clean_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _domain_of(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or (url or "")[:60] or "unknown"


def _append_sample(samples: list[str], value: str, max_count: int) -> None:
    value = _clean_text(value)
    if value and value not in samples and len(samples) < max_count:
        samples.append(value)


def _merge_samples(left: list[str], right: Iterable[str], max_count: int) -> list[str]:
    merged = list(left)
    for item in right:
        _append_sample(merged, item, max_count)
    return merged


def normalize_foreground_rows(rows: Iterable[Any]) -> list[NormalizedEvent]:
    events: list[NormalizedEvent] = []
    for row in rows:
        start_ts = int(_row_get(row, "start_ts", 0) or 0)
        end_ts = int(_row_get(row, "end_ts", start_ts) or start_ts)
        if end_ts < start_ts:
            end_ts = start_ts
        process_name = _clean_text(_row_get(row, "process_name"), "Unknown")
        window_title = _clean_text(_row_get(row, "window_title"), "无窗口标题")
        exe_path = _clean_text(_row_get(row, "exe_path"))
        events.append(
            NormalizedEvent(
                event_key=f"app:{process_name}",
                event_type="app",
                start_ts=start_ts,
                end_ts=end_ts,
                title=process_name,
                subtitle=window_title,
                detail=exe_path,
                source="foreground",
            )
        )
    return events


def normalize_browser_rows(rows: Iterable[Any]) -> list[NormalizedEvent]:
    events: list[NormalizedEvent] = []
    for row in rows:
        visit_ts = int(_row_get(row, "visit_ts", 0) or 0)
        url = _clean_text(_row_get(row, "url"))
        domain = _domain_of(url)
        title = _clean_text(_row_get(row, "title"), domain)
        browser = _clean_text(_row_get(row, "browser"), "browser")
        profile = _clean_text(_row_get(row, "profile"), "profile")
        events.append(
            NormalizedEvent(
                event_key=f"web:{domain}",
                event_type="web",
                start_ts=visit_ts,
                end_ts=visit_ts,
                title=domain,
                subtitle=title,
                detail=url,
                source=f"{browser} / {profile}",
            )
        )
    return events


def build_bands_from_events(
    events: Iterable[NormalizedEvent],
    day_start_ts: int,
    day_end_ts: int,
    *,
    bucket_seconds: int = config.ACTIVITY_BUCKET_SECONDS,
    min_active_seconds: int = config.ACTIVITY_MIN_ACTIVE_SECONDS,
    min_hit_count: int = config.ACTIVITY_MIN_HIT_COUNT,
    merge_gap_seconds: int = config.ACTIVITY_MERGE_GAP_SECONDS,
    point_event_seconds: int = config.ACTIVITY_POINT_EVENT_SECONDS,
    max_sample_count: int = config.ACTIVITY_MAX_SAMPLE_COUNT,
) -> list[ActivityBand]:
    """从标准事件构建活动带；不读写外部状态，便于单元测试。"""
    buckets: dict[tuple[int, str], list[_BucketStat]] = {}

    for event in sorted(events, key=lambda item: (item.start_ts, item.end_ts, item.event_key)):
        start_ts = max(day_start_ts, int(event.start_ts))
        end_ts = min(day_end_ts, int(event.end_ts))
        if start_ts > day_end_ts or end_ts < day_start_ts:
            continue
        is_point = event.event_type == "web" or end_ts <= start_ts
        if is_point:
            bucket_start = day_start_ts + ((start_ts - day_start_ts) // bucket_seconds) * bucket_seconds
            bucket_end = min(bucket_start + bucket_seconds, day_end_ts + 1)
            _add_bucket_hit(
                buckets,
                bucket_start,
                bucket_end,
                event,
                start_ts,
                max(start_ts, min(start_ts + point_event_seconds, day_end_ts)),
                point_event_seconds,
                merge_gap_seconds,
                max_sample_count,
            )
            continue

        first_bucket = day_start_ts + ((start_ts - day_start_ts) // bucket_seconds) * bucket_seconds
        bucket_start = first_bucket
        while bucket_start <= end_ts and bucket_start <= day_end_ts:
            bucket_end = min(bucket_start + bucket_seconds, day_end_ts + 1)
            overlap_start = max(start_ts, bucket_start)
            overlap_end = min(end_ts, bucket_end)
            active_seconds = max(0, overlap_end - overlap_start)
            if active_seconds > 0:
                _add_bucket_hit(
                    buckets,
                    bucket_start,
                    bucket_end,
                    event,
                    overlap_start,
                    overlap_end,
                    active_seconds,
                    merge_gap_seconds,
                    max_sample_count,
                )
            bucket_start += bucket_seconds

    candidates = [
        _stat_to_band(stat)
        for stats in buckets.values()
        for stat in stats
        if stat.total_active_seconds >= min_active_seconds or stat.hit_count >= min_hit_count
    ]
    return _merge_candidate_bands(candidates, merge_gap_seconds, max_sample_count)


def _add_bucket_hit(
    buckets: dict[tuple[int, str], list[_BucketStat]],
    bucket_start: int,
    bucket_end: int,
    event: NormalizedEvent,
    hit_start_ts: int,
    hit_end_ts: int,
    active_seconds: int,
    merge_gap_seconds: int,
    max_sample_count: int,
) -> None:
    key = (bucket_start, event.event_key)
    stats = buckets.setdefault(key, [])
    stat = None
    for candidate in reversed(stats):
        if hit_start_ts - candidate.end_ts <= merge_gap_seconds:
            stat = candidate
            break
    if stat is None:
        stat = _BucketStat(
            event=event,
            start_ts=hit_start_ts,
            end_ts=hit_end_ts,
            sample_titles=[],
            sample_details=[],
        )
        stats.append(stat)
    stat.start_ts = max(bucket_start, min(stat.start_ts, hit_start_ts))
    stat.end_ts = min(bucket_end, max(stat.end_ts, hit_end_ts))
    stat.total_active_seconds += int(active_seconds)
    stat.hit_count += 1
    if stat.sample_titles is None:
        stat.sample_titles = []
    if stat.sample_details is None:
        stat.sample_details = []
    _append_sample(stat.sample_titles, event.subtitle or event.title, max_sample_count)
    _append_sample(stat.sample_details, event.detail, max_sample_count)


def _stat_to_band(stat: _BucketStat) -> ActivityBand:
    event = stat.event
    return ActivityBand(
        event_key=event.event_key,
        event_type=event.event_type,
        start_ts=stat.start_ts,
        end_ts=stat.end_ts,
        title=event.title,
        subtitle=event.subtitle,
        detail=event.detail,
        total_active_seconds=stat.total_active_seconds,
        hit_count=stat.hit_count,
        sample_titles=list(stat.sample_titles or []),
        sample_details=list(stat.sample_details or []),
    )


def _merge_candidate_bands(
    candidates: Iterable[ActivityBand],
    merge_gap_seconds: int,
    max_sample_count: int,
) -> list[ActivityBand]:
    by_key: dict[str, list[ActivityBand]] = {}
    for band in candidates:
        by_key.setdefault(band.event_key, []).append(band)

    merged: list[ActivityBand] = []
    for bands in by_key.values():
        bands.sort(key=lambda band: (band.start_ts, band.end_ts))
        current: ActivityBand | None = None
        for band in bands:
            if current is None:
                current = band
                continue
            if band.start_ts - current.end_ts <= merge_gap_seconds:
                current.end_ts = max(current.end_ts, band.end_ts)
                current.total_active_seconds += band.total_active_seconds
                current.hit_count += band.hit_count
                current.sample_titles = _merge_samples(
                    current.sample_titles, band.sample_titles, max_sample_count
                )
                current.sample_details = _merge_samples(
                    current.sample_details, band.sample_details, max_sample_count
                )
            else:
                merged.append(current)
                current = band
        if current is not None:
            merged.append(current)

    merged.sort(key=lambda band: (band.start_ts, band.end_ts, band.event_key))
    return merged


def build_activity_bands(day: str | None = None) -> dict[str, Any]:
    start_ts, end_ts = day_bounds(day)
    events = normalize_foreground_rows(fetch_foreground_events(start_ts, end_ts))
    events.extend(normalize_browser_rows(fetch_browser_visits(start_ts, end_ts)))
    bands = build_bands_from_events(events, start_ts, end_ts)
    return {
        "day": datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d"),
        "start_ts": start_ts,
        "end_ts": end_ts,
        "generated_at": int(time.time()),
        "bands": [band.to_dict() for band in bands],
        "stats": _build_stats(bands),
    }


def _build_stats(bands: list[ActivityBand]) -> dict[str, Any]:
    by_type: dict[str, dict[str, Any]] = {}
    for band in bands:
        item = by_type.setdefault(
            band.event_type,
            {"event_type": band.event_type, "total_active_seconds": 0, "hit_count": 0, "band_count": 0},
        )
        item["total_active_seconds"] += band.total_active_seconds
        item["hit_count"] += band.hit_count
        item["band_count"] += 1
    top_bands = sorted(
        (band.to_dict() for band in bands),
        key=lambda item: (item["total_active_seconds"], item["hit_count"]),
        reverse=True,
    )[:10]
    return {
        "by_type": sorted(by_type.values(), key=lambda item: item["event_type"]),
        "top_bands": top_bands,
    }
