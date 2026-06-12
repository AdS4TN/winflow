from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest


class CliWebSplitTests(unittest.TestCase):
    REPLACEMENT_RUN = "?" * 4

    def test_split_modules_are_importable(self) -> None:
        from app.collector import collect_loop, collect_once, embedded_collect_loop
        from app.main import main
        from app.web import Handler, serve

        self.assertTrue(callable(main))
        self.assertTrue(callable(collect_once))
        self.assertTrue(callable(collect_loop))
        self.assertTrue(callable(embedded_collect_loop))
        self.assertTrue(callable(serve))
        self.assertIsNotNone(Handler)

    def test_cli_help_smoke(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "app.main", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Winflow Windows", result.stdout)
        self.assertIn("upload-usage", result.stdout)
        self.assertNotIn(self.REPLACEMENT_RUN, result.stdout)

    def test_documented_read_only_cli_commands_smoke_with_empty_db(self) -> None:
        with tempfile.TemporaryDirectory(prefix="winflow_cli_") as temp_dir:
            db_path = os.path.join(temp_dir, "winflow.sqlite")
            env = {**os.environ, "WINFLOW_DB": db_path}

            init_result = subprocess.run(
                [sys.executable, "-m", "app.main", "init"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                env=env,
            )
            self.assertEqual(init_result.returncode, 0, init_result.stderr)
            self.assertIn("已初始化数据库", init_result.stdout)

            for command in ("usage", "bands"):
                with self.subTest(command=command):
                    result = subprocess.run(
                        [sys.executable, "-m", "app.main", command, "--day", "2026-06-08"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=15,
                        env=env,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    payload = json.loads(result.stdout)
                    self.assertEqual("2026-06-08", payload["day"])
                    self.assertNotIn(self.REPLACEMENT_RUN, result.stdout)

            export_result = subprocess.run(
                [sys.executable, "-m", "app.main", "export", "--day", "2026-06-08"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                env=env,
            )
            self.assertEqual(export_result.returncode, 0, export_result.stderr)
            self.assertIn("# 2026-06-08 访问轨迹", export_result.stdout)
            self.assertNotIn(self.REPLACEMENT_RUN, export_result.stdout)


if __name__ == "__main__":
    unittest.main()
