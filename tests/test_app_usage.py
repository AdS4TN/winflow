from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

from app.app_usage import build_usage_snapshot_from_rows, normalize_app_name
from app.icon_map import icon_for_app, load_icon_map
from app.exe_icon import _cache_path_for_exe


def ts(hh_mm: str) -> int:
    hour, minute = map(int, hh_mm.split(":"))
    return int(datetime(2026, 6, 1, hour, minute, tzinfo=timezone.utc).timestamp())


class AppUsageSnapshotTest(unittest.TestCase):
    def test_normalize_common_process_names(self):
        self.assertEqual("Chrome", normalize_app_name("chrome.exe"))
        self.assertEqual("VS Code", normalize_app_name("Code.exe"))
        self.assertEqual("Windows Terminal", normalize_app_name("WindowsTerminal.exe"))
        self.assertEqual("CustomApp", normalize_app_name("CustomApp.exe"))

    def test_builds_app_usage_without_private_fields(self):
        snapshot = build_usage_snapshot_from_rows(
            [
                {
                    "start_ts": ts("09:00"),
                    "end_ts": ts("09:20"),
                    "process_name": "Code.exe",
                    "window_title": "secret project",
                    "exe_path": "C:\\secret\\Code.exe",
                }
            ],
            ts("00:00"),
            ts("23:59") + 59,
            day="2026-06-01",
            idle_threshold_seconds=300,
            now_ts=ts("12:00"),
        )

        app = snapshot["apps"][0]
        self.assertEqual("2026-06-01", snapshot["day"])
        self.assertEqual(300, snapshot["summary"]["active_seconds"])
        self.assertEqual("VS Code", app["app_name"])
        self.assertEqual(300, app["seconds"])
        self.assertEqual(["Code.exe"], app["process_names"])
        self.assertEqual("/static/icons/apps/vscode.svg", app["icon"])
        self.assertIn("color", app)
        serialized = str(snapshot)
        self.assertNotIn("secret project", serialized)
        self.assertNotIn("C:\\secret", serialized)

    def test_browser_usage_does_not_include_site_or_tab_details(self):
        snapshot = build_usage_snapshot_from_rows(
            [
                {
                    "start_ts": ts("10:00"),
                    "end_ts": ts("10:04"),
                    "process_name": "chrome.exe",
                    "window_title": "openai/codex - GitHub - Google Chrome",
                },
                {
                    "start_ts": ts("10:10"),
                    "end_ts": ts("10:16"),
                    "process_name": "chrome.exe",
                    "window_title": "ChatGPT - Google Chrome",
                },
            ],
            ts("00:00"),
            ts("23:59") + 59,
            day="2026-06-01",
            idle_threshold_seconds=300,
            now_ts=ts("12:00"),
        )

        chrome = snapshot["apps"][0]
        self.assertEqual("Chrome", chrome["app_name"])
        self.assertEqual(540, chrome["seconds"])
        self.assertNotIn("sites", chrome)
        serialized = str(snapshot)
        self.assertNotIn("openai/codex", serialized)
        self.assertNotIn("ChatGPT", serialized)
        self.assertNotIn("github.com", serialized)
        self.assertNotIn("chatgpt.com", serialized)

    def test_browser_windows_are_only_counted_as_browser_app_usage(self):
        foreground = [
            {
                "start_ts": ts("10:00"),
                "end_ts": ts("10:01"),
                "process_name": "chrome.exe",
                "window_title": "GitHub - Google Chrome",
            },
            {
                "start_ts": ts("10:02"),
                "end_ts": ts("10:04"),
                "process_name": "chrome.exe",
                "window_title": "ChatGPT - Google Chrome",
            },
            {
                "start_ts": ts("10:05"),
                "end_ts": ts("10:08"),
                "process_name": "chrome.exe",
                "window_title": "YouTube - Google Chrome",
            },
        ]

        snapshot = build_usage_snapshot_from_rows(
            foreground,
            ts("00:00"),
            ts("23:59") + 59,
            day="2026-06-01",
            idle_threshold_seconds=300,
            now_ts=ts("12:00"),
        )

        chrome = snapshot["apps"][0]
        self.assertEqual("Chrome", chrome["app_name"])
        self.assertEqual(360, chrome["seconds"])
        self.assertNotIn("sites", chrome)
        serialized = str(snapshot)
        self.assertNotIn("GitHub - Google Chrome", serialized)
        self.assertNotIn("ChatGPT - Google Chrome", serialized)
        self.assertNotIn("YouTube - Google Chrome", serialized)

    def test_lock_screen_process_is_ignored(self):
        snapshot = build_usage_snapshot_from_rows(
            [
                {
                    "start_ts": ts("09:00"),
                    "end_ts": ts("09:10"),
                    "process_name": "LockApp.exe",
                    "window_title": "Windows 默认锁屏界面",
                },
                {
                    "start_ts": ts("09:10"),
                    "end_ts": ts("09:12"),
                    "process_name": "CredentialUIBroker.exe",
                    "window_title": "Windows 凭据输入界面",
                },
                {
                    "start_ts": ts("09:12"),
                    "end_ts": ts("09:17"),
                    "process_name": "Code.exe",
                },
            ],
            ts("00:00"),
            ts("23:59") + 59,
            day="2026-06-01",
            idle_threshold_seconds=300,
            now_ts=ts("12:00"),
        )

        app = snapshot["apps"][0]
        self.assertEqual("VS Code", app["app_name"])
        self.assertEqual(300, app["seconds"])
        self.assertEqual(["Code.exe"], app["process_names"])
        self.assertNotIn("LockApp", str(snapshot))
        self.assertNotIn("CredentialUIBroker", str(snapshot))

    def test_unknown_browser_window_title_does_not_leak_full_title(self):
        rows = [
            {
                "start_ts": ts("10:00"),
                "end_ts": ts("10:05"),
                "process_name": "chrome.exe",
                "window_title": "AI Radar V1 - Google Chrome",
            }
        ]

        snapshot = build_usage_snapshot_from_rows(
            rows,
            ts("00:00"),
            ts("23:59") + 59,
            day="2026-06-01",
            idle_threshold_seconds=300,
            now_ts=ts("12:00"),
        )

        self.assertNotIn("sites", snapshot["apps"][0])
        self.assertNotIn("AI Radar V1", str(snapshot))


    def test_exe_path_is_used_for_icon_without_leaking_path(self):
        private_exe = r"C:\Secret Folder\PrivateApp.exe"
        with patch("app.app_usage.icon_url_for_exe", return_value="/static/exe-icons/private-app.ico"):
            snapshot = build_usage_snapshot_from_rows(
                [
                    {
                        "start_ts": ts("11:00"),
                        "end_ts": ts("11:05"),
                        "process_name": "notepad.exe",
                        "exe_path": private_exe,
                        "window_title": "private note",
                    }
                ],
                ts("00:00"),
                ts("23:59") + 59,
                day="2026-06-01",
                idle_threshold_seconds=300,
                now_ts=ts("12:00"),
            )

        app = snapshot["apps"][0]
        self.assertEqual("Notepad", app["app_name"])
        self.assertEqual("exe", app["icon_source"])
        self.assertEqual("/static/exe-icons/private-app.ico", app["icon"])
        serialized = str(snapshot)
        self.assertNotIn(private_exe, serialized)
        self.assertNotIn("private note", serialized)

    def test_exe_icon_cache_name_does_not_include_absolute_path(self):
        target = _cache_path_for_exe(Path(r"C:\Secret Folder\PrivateApp.exe"), "Private App")

        self.assertTrue(target.name.startswith("private-app-"))
        self.assertNotIn("\\", target.name)

    def test_icon_map_can_be_customized_from_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "icon_map.json"
            path.write_text(
                """{
                  "apps": {"VS Code": {"icon": "/static/icons/custom/code.svg", "color": "#123456", "text_color": "#ffffff"}}
                }""",
                encoding="utf-8",
            )
            mapping = load_icon_map(path)

        self.assertEqual(
            {"icon": "/static/icons/custom/code.svg", "color": "#123456", "text_color": "#ffffff"},
            icon_for_app("VS Code", mapping),
        )

    def test_unknown_icon_fallback_is_stable_without_empty_default(self):
        icon = icon_for_app("CustomApp", {"apps": {}})

        self.assertEqual("CU", icon["icon"])
        self.assertTrue(icon["color"].startswith("#"))
        self.assertEqual("#f8fafc", icon["text_color"])


if __name__ == "__main__":
    unittest.main()
