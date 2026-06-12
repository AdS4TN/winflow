from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WindowsFirstBoundaryTests(unittest.TestCase):
    def test_implementation_does_not_import_macos_stack(self) -> None:
        """Winflow 只借鉴 Dayflow 的产品方向，不迁移 macOS 技术栈。"""

        banned_terms = (
            "ScreenCaptureKit",
            "AVFoundation",
            "NSWorkspace",
            "CGWindow",
            "CoreGraphics",
            "Quartz",
            "AppKit",
            "AppleScript",
            "Objective-C",
        )
        implementation_files = [
            *ROOT.joinpath("app").rglob("*.py"),
            ROOT / "requirements.txt",
        ]

        for path in implementation_files:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                text = path.read_text(encoding="utf-8")
                for term in banned_terms:
                    self.assertNotIn(term, text)

    def test_core_windows_modules_are_present(self) -> None:
        """核心采集链路必须保持 Windows-first：前台窗口、进程、exe 图标、本地 SQLite。"""

        required_files = (
            ROOT / "app" / "windows_activity.py",
            ROOT / "app" / "collector.py",
            ROOT / "app" / "storage.py",
            ROOT / "app" / "exe_icon.py",
            ROOT / "app" / "app_usage.py",
        )

        for path in required_files:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertTrue(path.exists(), f"{path} should exist")

    def test_browser_history_reader_is_not_part_of_public_app(self) -> None:
        """默认隐私边界：开源版不应内置浏览器历史读取模块或存储入口。"""

        forbidden_paths = (
            ROOT / "app" / "browser_history.py",
        )
        forbidden_terms = (
            "insert_browser_visits",
            "fetch_browser_visits",
            "BrowserVisit",
            "WINFLOW_HISTORY_DAYS",
        )
        implementation_files = [
            *ROOT.joinpath("app").rglob("*.py"),
            ROOT / "requirements.txt",
        ]

        for path in forbidden_paths:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertFalse(path.exists(), f"{path} should not be part of the public app")

        for path in implementation_files:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                text = path.read_text(encoding="utf-8")
                for term in forbidden_terms:
                    self.assertNotIn(term, text)


if __name__ == "__main__":
    unittest.main()
