from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from app import config
from app.web import static_file_for_request


class RuntimePathTests(unittest.TestCase):
    def test_installed_default_data_dir_uses_windows_user_data_dir(self) -> None:
        with patch("app.config._is_source_tree", return_value=False), patch.dict(
            "os.environ",
            {"LOCALAPPDATA": r"C:\Users\Alice\AppData\Local"},
            clear=True,
        ):
            self.assertEqual(
                Path(r"C:\Users\Alice\AppData\Local\Winflow"),
                config._default_data_dir(),
            )

    def test_source_tree_default_exe_icon_dir_stays_in_static_cache(self) -> None:
        with patch("app.config._is_source_tree", return_value=True):
            self.assertEqual(
                config.SOURCE_STATIC_DIR / "exe-icons",
                config._default_exe_icon_dir(),
            )

    def test_static_file_router_rejects_directory_traversal(self) -> None:
        self.assertIsNone(static_file_for_request("/static/../README.md"))
        self.assertIsNone(static_file_for_request("/static/exe-icons/../secret.png"))


if __name__ == "__main__":
    unittest.main()
