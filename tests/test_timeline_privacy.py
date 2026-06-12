from __future__ import annotations

import json
import unittest
from unittest.mock import patch


class TimelinePrivacyTests(unittest.TestCase):
    def test_timeline_does_not_expose_window_title_or_exe_path(self) -> None:
        from app.timeline import build_timeline

        rows = [
            {
                "start_ts": 100,
                "end_ts": 200,
                "process_name": "Code.exe",
                "window_title": "Secret Customer Project",
                "exe_path": r"C:\Users\Alice\Private\Code.exe",
            },
            {
                "start_ts": 210,
                "end_ts": 260,
                "process_name": "chrome.exe",
                "window_title": "Private Tab - Google Chrome",
                "exe_path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            },
        ]

        with patch("app.timeline.day_bounds", return_value=(0, 999)), patch(
            "app.timeline.fetch_foreground_events",
            return_value=rows,
        ), patch("app.timeline.fetch_stats", return_value={"apps": [], "browsers": []}):
            payload = build_timeline("2026-06-08")

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("Secret Customer Project", serialized)
        self.assertNotIn("Private Tab", serialized)
        self.assertNotIn("C:\\Users\\Alice", serialized)
        self.assertNotIn("Program Files", serialized)

        self.assertEqual("Code.exe", payload["items"][0]["title"])
        self.assertEqual("前台应用窗口", payload["items"][0]["subtitle"])
        self.assertEqual("", payload["items"][0]["detail"])
        self.assertEqual("chrome.exe", payload["items"][1]["title"])
        self.assertEqual("浏览器窗口", payload["items"][1]["subtitle"])
        self.assertEqual("", payload["items"][1]["detail"])


if __name__ == "__main__":
    unittest.main()
