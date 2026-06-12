from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import uploader
from app.uploader import UploadError


class UploaderSafetyTest(unittest.TestCase):
    def test_missing_server_url_is_an_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(UploadError):
                uploader._configured_server_url(None)

    def test_explicit_server_url_is_required_for_upload_usage(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("app.uploader.build_usage_snapshot") as build_snapshot:
                with self.assertRaises(UploadError):
                    uploader.upload_usage("2026-06-01")
        build_snapshot.assert_not_called()

    def test_load_env_files_only_reads_project_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("WINFLOW_SERVER_URL=https://example.com\n", encoding="utf-8")
            with patch("app.uploader.PROJECT_ROOT", root), patch.dict(os.environ, {}, clear=True):
                uploader.load_env_files()
                self.assertEqual("https://example.com", os.environ.get("WINFLOW_SERVER_URL"))
                self.assertNotIn("WINFLOW_UPLOAD_TOKEN", os.environ)

    def test_sync_snapshot_icons_processes_only_app_level_icons(self):
        snapshot = {
            "apps": [
                {
                    "app_name": "Chrome",
                    "icon": "/static/exe-icons/chrome.png",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            icon_path = Path(tmp) / "static" / "exe-icons" / "chrome.png"
            icon_path.parent.mkdir(parents=True, exist_ok=True)
            icon_path.write_bytes(b"fake")
            with patch("app.uploader.PROJECT_ROOT", Path(tmp)), patch(
                "app.uploader.EXE_ICON_DIR",
                icon_path.parent,
            ), patch(
                "app.uploader.upload_icon",
                return_value="https://cdn.example.com/chrome.png",
            ) as upload_icon:
                result = uploader.sync_snapshot_icons(snapshot, "https://example.com", "token")

        upload_icon.assert_called_once()
        self.assertEqual("https://cdn.example.com/chrome.png", result["apps"][0]["icon"])

    def test_sync_snapshot_icons_ignores_nested_non_app_fields(self):
        snapshot = {
            "apps": [
                {
                    "app_name": "Chrome",
                    "icon": "/static/icons/apps/chrome.svg",
                    "children": [
                        {"icon": "/static/exe-icons/nested.png"},
                    ],
                }
            ]
        }
        with patch("app.uploader.upload_icon") as upload_icon:
            result = uploader.sync_snapshot_icons(snapshot, "https://example.com", "token")

        upload_icon.assert_not_called()
        self.assertEqual("/static/exe-icons/nested.png", result["apps"][0]["children"][0]["icon"])

    def test_upload_pending_syncs_local_exe_icons_before_snapshot(self):
        snapshot = {
            "device_id": "pc",
            "day": "2026-06-01",
            "apps": [{"app_name": "Chrome", "icon": "/static/exe-icons/chrome.png"}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            pending_dir = Path(tmp) / "pending"
            pending_dir.mkdir()
            (pending_dir / "pc-2026-06-01.json").write_text(
                json.dumps(snapshot),
                encoding="utf-8",
            )
            icon_path = Path(tmp) / "static" / "exe-icons" / "chrome.png"
            icon_path.parent.mkdir(parents=True)
            icon_path.write_bytes(b"fake")

            with patch("app.uploader.PENDING_DIR", pending_dir), patch(
                "app.uploader.PROJECT_ROOT",
                Path(tmp),
            ), patch(
                "app.uploader.EXE_ICON_DIR",
                icon_path.parent,
            ), patch(
                "app.uploader.upload_icon",
                return_value="https://cdn.example.com/chrome.png",
            ) as upload_icon, patch(
                "app.uploader.upload_snapshot",
                return_value={"ok": True},
            ) as upload_snapshot:
                uploaded = uploader.upload_pending(
                    server_url="https://example.com",
                    upload_token="token",
                )

        self.assertEqual(1, uploaded)
        upload_icon.assert_called_once()
        sent_snapshot = upload_snapshot.call_args.args[0]
        self.assertEqual("https://cdn.example.com/chrome.png", sent_snapshot["apps"][0]["icon"])


if __name__ == "__main__":
    unittest.main()
