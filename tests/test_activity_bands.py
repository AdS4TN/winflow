"""活动带核心算法测试。

这些测试只面向 Agent A 提供的纯函数接口：
`app.activity_bands.NormalizedEvent` 与 `build_bands_from_events`。
生产代码尚未合入时，测试会被跳过；一旦接口存在，应覆盖开发文档第 9 节的 6 个必测用例。
"""

from __future__ import annotations

from datetime import datetime, timezone
import inspect
import unittest

try:
    from app.activity_bands import NormalizedEvent, build_bands_from_events
except ImportError as exc:  # pragma: no cover - 仅用于并行开发期间等待 Agent A 合入
    NormalizedEvent = None
    build_bands_from_events = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


BASE_DAY = "2026-05-18"


def ts(hh_mm: str) -> int:
    """把当天 HH:MM 转成稳定的 UTC 秒级时间戳，避免依赖本机时区。"""
    hour, minute = map(int, hh_mm.split(":"))
    return int(datetime(2026, 5, 18, hour, minute, tzinfo=timezone.utc).timestamp())


def band_value(band, name: str):
    """兼容 dataclass/对象 与 dict 两种返回结构，便于约束算法而非约束序列化形态。"""
    if isinstance(band, dict):
        return band[name]
    return getattr(band, name)


@unittest.skipIf(
    IMPORT_ERROR is not None,
    f"app.activity_bands 尚不可导入，等待 Agent A 合入核心算法：{IMPORT_ERROR}",
)
class ActivityBandsAlgorithmTest(unittest.TestCase):
    """开发文档第 9.2 节活动带聚合规则测试。"""

    def app_event(self, start: str, end: str, process_name: str = "Code.exe"):
        return NormalizedEvent(
            event_key=f"app:{process_name}",
            event_type="app",
            start_ts=ts(start),
            end_ts=ts(end),
            title=process_name,
            subtitle=process_name,
            detail=f"{process_name} window",
            source=process_name,
        )

    def web_event(self, at: str, domain: str = "github.com", index: int = 0):
        return NormalizedEvent(
            event_key=f"web:{domain}",
            event_type="web",
            start_ts=ts(at),
            end_ts=ts(at),
            title=f"{domain} page {index}",
            subtitle=domain,
            detail=f"https://{domain}/page-{index}",
            source=domain,
        )

    def build(self, events):
        """调用纯函数；若 Agent A 支持 day 参数则传入固定日期。"""
        signature = inspect.signature(build_bands_from_events)
        parameters = signature.parameters
        if "day_start_ts" in parameters and "day_end_ts" in parameters:
            result = build_bands_from_events(events, ts("00:00"), ts("23:59") + 59)
        elif "day" in parameters:
            result = build_bands_from_events(events, day=BASE_DAY)
        else:
            result = build_bands_from_events(events)

        if isinstance(result, dict):
            return result.get("bands", result.get("items", []))
        return list(result)

    def bands_for(self, bands, event_key: str):
        return [band for band in bands if band_value(band, "event_key") == event_key]

    def assert_single_band(self, bands, event_key: str):
        matched = self.bands_for(bands, event_key)
        self.assertEqual(1, len(matched), f"应只生成一条 {event_key} 活动带")
        return matched[0]

    def test_app_stay_over_three_minutes_creates_band(self):
        """用例 1：09:00-09:04 停留超过 3 分钟，应生成 app:Code.exe。"""
        bands = self.build([self.app_event("09:00", "09:04")])

        band = self.assert_single_band(bands, "app:Code.exe")
        self.assertEqual("app", band_value(band, "event_type"))
        self.assertEqual(ts("09:00"), band_value(band, "start_ts"))
        self.assertEqual(ts("09:04"), band_value(band, "end_ts"))
        self.assertGreaterEqual(band_value(band, "total_active_seconds"), 180)

    def test_app_stay_under_three_minutes_does_not_create_band(self):
        """用例 2：09:00-09:02 不足 3 分钟，应被阈值过滤。"""
        bands = self.build([self.app_event("09:00", "09:02")])

        self.assertEqual([], self.bands_for(bands, "app:Code.exe"))

    def test_five_web_hits_within_three_minutes_create_band(self):
        """用例 3：3 分钟内同域名访问 5 次，应生成 web:github.com。"""
        events = [
            self.web_event("09:00", index=1),
            self.web_event("09:01", index=2),
            self.web_event("09:01", index=3),
            self.web_event("09:02", index=4),
            self.web_event("09:02", index=5),
        ]

        bands = self.build(events)

        band = self.assert_single_band(bands, "web:github.com")
        self.assertEqual("web", band_value(band, "event_type"))
        self.assertGreaterEqual(band_value(band, "hit_count"), 5)

    def test_a_b_a_frequent_switching_merges_same_app_band(self):
        """用例 4：A-B-A 频繁切屏，Code.exe 间隔 1 分钟，应合并为 09:00-09:12。"""
        bands = self.build(
            [
                self.app_event("09:00", "09:05", "Code.exe"),
                self.app_event("09:05", "09:06", "WeChat.exe"),
                self.app_event("09:06", "09:12", "Code.exe"),
            ]
        )

        code_band = self.assert_single_band(bands, "app:Code.exe")
        self.assertEqual(ts("09:00"), band_value(code_band, "start_ts"))
        self.assertEqual(ts("09:12"), band_value(code_band, "end_ts"))
        self.assertEqual([], self.bands_for(bands, "app:WeChat.exe"))

    def test_same_event_gap_over_three_minutes_does_not_merge(self):
        """用例 5：同事件间隔超过 3 分钟，应生成两条 Code.exe 活动带。"""
        bands = self.build(
            [
                self.app_event("09:00", "09:05", "Code.exe"),
                self.app_event("09:10", "09:15", "Code.exe"),
            ]
        )

        code_bands = sorted(
            self.bands_for(bands, "app:Code.exe"), key=lambda band: band_value(band, "start_ts")
        )
        self.assertEqual(2, len(code_bands))
        self.assertEqual((ts("09:00"), ts("09:05")), (band_value(code_bands[0], "start_ts"), band_value(code_bands[0], "end_ts")))
        self.assertEqual((ts("09:10"), ts("09:15")), (band_value(code_bands[1], "start_ts"), band_value(code_bands[1], "end_ts")))

    def test_band_across_fifteen_minute_bucket_merges_naturally(self):
        """用例 6：09:10-09:25 跨 15 分钟窗口，最终仍显示一条自然合并活动带。"""
        bands = self.build([self.app_event("09:10", "09:25", "Code.exe")])

        band = self.assert_single_band(bands, "app:Code.exe")
        self.assertEqual(ts("09:10"), band_value(band, "start_ts"))
        self.assertEqual(ts("09:25"), band_value(band, "end_ts"))

    def test_three_minute_app_stay_across_bucket_boundary_still_creates_band(self):
        """边界补偿：09:14-09:17 横跨 09:15 桶边界，但总停留达到 3 分钟。"""
        bands = self.build([self.app_event("09:14", "09:17", "Code.exe")])

        band = self.assert_single_band(bands, "app:Code.exe")
        self.assertEqual(ts("09:14"), band_value(band, "start_ts"))
        self.assertEqual(ts("09:17"), band_value(band, "end_ts"))

    def test_five_web_hits_across_bucket_boundary_still_creates_band(self):
        """边界补偿：5 次访问横跨 09:15 桶边界时也不应被拆散漏判。"""
        events = [
            self.web_event("09:14", index=1),
            self.web_event("09:14", index=2),
            self.web_event("09:14", index=3),
            self.web_event("09:15", index=4),
            self.web_event("09:15", index=5),
        ]

        bands = self.build(events)

        band = self.assert_single_band(bands, "web:github.com")
        self.assertGreaterEqual(band_value(band, "hit_count"), 5)

    def test_explorer_task_switching_shell_event_is_filtered(self):
        """explorer.exe 的任务切换/桌面外壳事件不应生成活动带。"""
        from app.activity_bands import normalize_foreground_rows

        rows = [
            {
                "start_ts": ts("09:00"),
                "end_ts": ts("09:10"),
                "process_name": "explorer.exe",
                "window_title": "任务切换",
                "exe_path": "C:\\WINDOWS\\explorer.exe",
            }
        ]

        events = normalize_foreground_rows(rows)

        self.assertEqual([], events)

    def test_explorer_file_window_is_kept(self):
        """真实文件资源管理器窗口仍应保留，避免误杀文件浏览活动。"""
        from app.activity_bands import normalize_foreground_rows

        rows = [
            {
                "start_ts": ts("09:00"),
                "end_ts": ts("09:10"),
                "process_name": "explorer.exe",
                "window_title": "winflow",
                "exe_path": "C:\\WINDOWS\\explorer.exe",
            }
        ]

        events = normalize_foreground_rows(rows)

        self.assertEqual(1, len(events))
        self.assertEqual("app:explorer.exe", events[0].event_key)


if __name__ == "__main__":
    unittest.main()
