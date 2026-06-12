from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable

from . import config
from .storage import fetch_foreground_events, safe_window_title
from .timeline import day_bounds

IGNORED_PROCESS_NAMES = {
    "lockapp.exe",
    "logonui.exe",
    "credentialuibroker.exe",
    "shellexperiencehost.exe",
    "searchhost.exe",
    "startmenuexperiencehost.exe",
}


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

    @property
    def id(self) -> str:
        return self.event_key

    @property
    def kind(self) -> str:
        return self.event_type

    def to_dict(self) -> dict[str, Any]:
        item = asdict(self)
        item["id"] = self.id
        item["kind"] = self.kind
        return item


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
        window_title = _clean_text(safe_window_title(process_name, _row_get(row, "window_title")), "无窗口标题")
        # exe_path 只用于本地图标提取，不应进入公开活动带 API。
        if _is_ignorable_system_shell(process_name, window_title):
            continue
        events.append(
            NormalizedEvent(
                event_key=f"app:{process_name}",
                event_type="app",
                start_ts=start_ts,
                end_ts=end_ts,
                title=process_name,
                subtitle=window_title,
                detail="",
                source="foreground",
            )
        )
    return events


def _is_ignorable_system_shell(process_name: str, window_title: str) -> bool:
    """过滤不代表真实用户任务的 Windows 外壳窗口。

    explorer.exe 同时负责文件资源管理器、桌面、任务栏和 Alt+Tab。
    文件资源管理器窗口应保留；任务切换、桌面等系统外壳事件应忽略，
    否则频繁切屏会把 explorer.exe 错误聚合成活动带。
    """
    process_key = process_name.strip().lower()
    if process_key in IGNORED_PROCESS_NAMES:
        return True
    if process_key != "explorer.exe":
        return False
    normalized_title = window_title.strip().lower()
    return normalized_title in {
        "",
        "无窗口标题",
        "program manager",
        "任务切换",
        "task switching",
        "start",
    }


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
        is_point = end_ts <= start_ts
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
    candidates.extend(
        _build_boundary_fallback_candidates(
            events,
            day_start_ts,
            day_end_ts,
            bucket_seconds,
            min_active_seconds,
            min_hit_count,
            merge_gap_seconds,
            point_event_seconds,
            max_sample_count,
            candidates,
        )
    )
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


def _build_boundary_fallback_candidates(
    events: Iterable[NormalizedEvent],
    day_start_ts: int,
    day_end_ts: int,
    bucket_seconds: int,
    min_active_seconds: int,
    min_hit_count: int,
    merge_gap_seconds: int,
    point_event_seconds: int,
    max_sample_count: int,
    existing_candidates: Iterable[ActivityBand],
) -> list[ActivityBand]:
    """补偿固定 15 分钟桶边界造成的漏判。

    例如 09:14-09:17 的连续应用停留实际达到 3 分钟，但被固定桶切成
    09:14-09:15 和 09:15-09:17 后，两个桶内都不足阈值。这里按同一
    event_key 的连续片段再做一次轻量聚合，只在没有候选带覆盖时补充。
    """
    existing = list(existing_candidates)
    by_key: dict[str, list[NormalizedEvent]] = {}
    for event in events:
        start_ts = max(day_start_ts, int(event.start_ts))
        end_ts = min(day_end_ts, int(event.end_ts))
        if start_ts > day_end_ts or end_ts < day_start_ts:
            continue
        by_key.setdefault(event.event_key, []).append(event)

    fallback: list[ActivityBand] = []
    for key_events in by_key.values():
        key_events.sort(key=lambda item: (item.start_ts, item.end_ts))
        current: ActivityBand | None = None
        cluster_anchor: int | None = None

        for event in key_events:
            start_ts = max(day_start_ts, int(event.start_ts))
            raw_end_ts = min(day_end_ts, int(event.end_ts))
            is_point = raw_end_ts <= start_ts
            end_ts = max(start_ts, min(start_ts + point_event_seconds, day_end_ts)) if is_point else raw_end_ts
            active_seconds = point_event_seconds if is_point else max(0, end_ts - start_ts)

            should_start_new = (
                current is None
                or start_ts - current.end_ts > merge_gap_seconds
                or (
                    cluster_anchor is not None
                    and start_ts - cluster_anchor >= bucket_seconds
                )
            )
            if should_start_new:
                if _is_qualifying_fallback(current, min_active_seconds, min_hit_count) and not _overlaps_existing(
                    current, existing
                ):
                    fallback.append(current)
                cluster_anchor = start_ts
                current = ActivityBand(
                    event_key=event.event_key,
                    event_type=event.event_type,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    title=event.title,
                    subtitle=event.subtitle,
                    detail=event.detail,
                    total_active_seconds=int(active_seconds),
                    hit_count=1,
                    sample_titles=[],
                    sample_details=[],
                )
            else:
                current.end_ts = max(current.end_ts, end_ts)
                current.total_active_seconds += int(active_seconds)
                current.hit_count += 1

            _append_sample(current.sample_titles, event.subtitle or event.title, max_sample_count)
            _append_sample(current.sample_details, event.detail, max_sample_count)

        if _is_qualifying_fallback(current, min_active_seconds, min_hit_count) and not _overlaps_existing(
            current, existing
        ):
            fallback.append(current)

    return fallback


def _is_qualifying_fallback(
    band: ActivityBand | None,
    min_active_seconds: int,
    min_hit_count: int,
) -> bool:
    return bool(
        band
        and (band.total_active_seconds >= min_active_seconds or band.hit_count >= min_hit_count)
    )


def _overlaps_existing(band: ActivityBand, existing: Iterable[ActivityBand]) -> bool:
    return any(
        other.event_key == band.event_key
        and band.start_ts <= other.end_ts
        and other.start_ts <= band.end_ts
        for other in existing
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
    bands = build_bands_from_events(events, start_ts, end_ts)
    return {
        "schema_version": 1,
        "day": datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d"),
        "start_ts": start_ts,
        "end_ts": end_ts,
        "range": {
            "start_ts": start_ts,
            "end_ts": end_ts,
        },
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
