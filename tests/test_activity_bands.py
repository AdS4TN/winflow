"""活动带核心算法测试。

这些测试面向 `app.activity_bands.NormalizedEvent` 与
`build_bands_from_events` 两个纯函数接口，覆盖频繁切屏、阈值过滤、
跨 15 分钟窗口和隐私脱敏等核心规则。
"""

from __future__ import annotations

from datetime import datetime, timezone
import inspect
import unittest

from app.activity_bands import NormalizedEvent, build_bands_from_events


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


class ActivityBandsAlgorithmTest(unittest.TestCase):
    """活动带聚合规则测试。"""

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

    def point_app_event(self, at: str, process_name: str = "WindowsTerminal.exe", index: int = 0):
        return NormalizedEvent(
            event_key=f"app:{process_name}",
            event_type="app",
            start_ts=ts(at),
            end_ts=ts(at),
            title=process_name,
            subtitle=f"{process_name} quick hit {index}",
            detail="",
            source=process_name,
        )

    def build(self, events):
        """调用纯函数；兼容历史版本中的 day 参数签名。"""
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
        self.assertEqual("app:Code.exe", band_value(band, "id"))
        self.assertEqual("app", band_value(band, "kind"))
        self.assertEqual(ts("09:00"), band_value(band, "start_ts"))
        self.assertEqual(ts("09:04"), band_value(band, "end_ts"))
        self.assertGreaterEqual(band_value(band, "total_active_seconds"), 180)

    def test_app_stay_under_three_minutes_does_not_create_band(self):
        """用例 2：09:00-09:02 不足 3 分钟，应被阈值过滤。"""
        bands = self.build([self.app_event("09:00", "09:02")])

        self.assertEqual([], self.bands_for(bands, "app:Code.exe"))

    def test_five_short_app_hits_within_three_minutes_create_band(self):
        """用例 3：3 分钟内同一应用命中 5 次，应生成该应用活动带。"""
        events = [
            self.point_app_event("09:00", index=1),
            self.point_app_event("09:01", index=2),
            self.point_app_event("09:01", index=3),
            self.point_app_event("09:02", index=4),
            self.point_app_event("09:02", index=5),
        ]

        bands = self.build(events)

        band = self.assert_single_band(bands, "app:WindowsTerminal.exe")
        self.assertEqual("app", band_value(band, "event_type"))
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

    def test_five_short_app_hits_across_bucket_boundary_still_creates_band(self):
        """边界补偿：5 次应用命中横跨 09:15 桶边界时也不应被拆散漏判。"""
        events = [
            self.point_app_event("09:14", index=1),
            self.point_app_event("09:14", index=2),
            self.point_app_event("09:14", index=3),
            self.point_app_event("09:15", index=4),
            self.point_app_event("09:15", index=5),
        ]

        bands = self.build(events)

        band = self.assert_single_band(bands, "app:WindowsTerminal.exe")
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

    def test_browser_window_title_is_redacted(self):
        """浏览器窗口标题通常是具体标签页标题，应脱敏成固定文案。"""
        from app.activity_bands import normalize_foreground_rows

        rows = [
            {
                "start_ts": ts("09:00"),
                "end_ts": ts("09:10"),
                "process_name": "chrome.exe",
                "window_title": "Secret Page - Google Chrome",
                "exe_path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            }
        ]

        events = normalize_foreground_rows(rows)

        self.assertEqual(1, len(events))
        self.assertEqual("app:chrome.exe", events[0].event_key)
        self.assertEqual("浏览器窗口", events[0].subtitle)
        self.assertNotIn("Secret Page", str(events[0]))

    def test_foreground_exe_path_is_not_exposed_in_band_event_detail(self):
        """活动带公开 API 不应输出真实 exe_path。"""
        from app.activity_bands import normalize_foreground_rows

        rows = [
            {
                "start_ts": ts("09:00"),
                "end_ts": ts("09:10"),
                "process_name": "Code.exe",
                "window_title": "workspace",
                "exe_path": "C:\\Users\\Alice\\Private\\Code.exe",
            }
        ]

        events = normalize_foreground_rows(rows)

        self.assertEqual(1, len(events))
        self.assertEqual("", events[0].detail)
        self.assertNotIn("Private", str(events[0]))

    def test_lock_and_credential_windows_are_filtered(self):
        """锁屏和凭据窗口不是用户任务，不应进入活动带。"""
        from app.activity_bands import normalize_foreground_rows

        rows = [
            {
                "start_ts": ts("09:00"),
                "end_ts": ts("09:10"),
                "process_name": "LockApp.exe",
                "window_title": "Windows 默认锁屏界面",
                "exe_path": "C:\\WINDOWS\\SystemApps\\Microsoft.LockApp\\LockApp.exe",
            },
            {
                "start_ts": ts("09:10"),
                "end_ts": ts("09:20"),
                "process_name": "CredentialUIBroker.exe",
                "window_title": "Windows 凭据输入界面",
                "exe_path": "C:\\WINDOWS\\System32\\CredentialUIBroker.exe",
            },
        ]

        self.assertEqual([], normalize_foreground_rows(rows))

    def test_build_activity_bands_response_schema_is_stable(self):
        """公开 /api/bands 响应应包含版本和时间范围字段。"""
        from unittest.mock import patch

        from app.activity_bands import build_activity_bands

        rows = [
            {
                "start_ts": ts("09:00"),
                "end_ts": ts("09:10"),
                "process_name": "Code.exe",
                "window_title": "workspace",
                "exe_path": "C:\\Users\\Alice\\Private\\Code.exe",
            }
        ]

        with patch("app.activity_bands.day_bounds", return_value=(ts("00:00"), ts("23:59") + 59)), patch(
            "app.activity_bands.fetch_foreground_events",
            return_value=rows,
        ):
            payload = build_activity_bands(BASE_DAY)

        self.assertEqual(1, payload["schema_version"])
        self.assertEqual({"start_ts": ts("00:00"), "end_ts": ts("23:59") + 59}, payload["range"])
        self.assertEqual(ts("00:00"), payload["start_ts"])
        self.assertEqual(ts("23:59") + 59, payload["end_ts"])
        band = payload["bands"][0]
        self.assertEqual("app:Code.exe", band["id"])
        self.assertEqual("app", band["kind"])
        self.assertEqual("", band["detail"])
        self.assertEqual([], band["sample_details"])
        self.assertNotIn("Private", str(payload))


if __name__ == "__main__":
    unittest.main()
