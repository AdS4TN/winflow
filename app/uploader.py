from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .app_usage import build_usage_snapshot
from .config import DATA_DIR, EXE_ICON_DIR, PROJECT_ROOT

PENDING_DIR = DATA_DIR / "upload-pending"
SNAPSHOT_ENDPOINT = "api/winflow/snapshots"
ICON_ENDPOINT = "api/winflow/icons"


class UploadError(RuntimeError):
    pass


def _read_env_file(path: Path) -> None:
    """只从项目目录读取可选上传配置。"""
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def load_env_files() -> None:
    """只加载仓库根目录下的 .env 文件，不扫描项目外目录。"""
    _read_env_file(PROJECT_ROOT / ".env.local")
    _read_env_file(PROJECT_ROOT / ".env")


def _configured_server_url(server_url: str | None = None) -> str:
    target = (server_url or os.environ.get("WINFLOW_SERVER_URL") or "").strip()
    if not target:
        raise UploadError("Missing WINFLOW_SERVER_URL or --server-url. Upload is opt-in and requires an explicit server.")
    return target.rstrip("/")


def _server_url(server_url: str | None) -> str:
    return urljoin(_configured_server_url(server_url) + "/", SNAPSHOT_ENDPOINT)


def _icon_server_url(server_url: str | None) -> str:
    return urljoin(_configured_server_url(server_url) + "/", ICON_ENDPOINT)


def _token(upload_token: str | None = None) -> str:
    token = upload_token or os.environ.get("WINFLOW_UPLOAD_TOKEN") or os.environ.get("WINFLOW_TOKEN") or ""
    if not token:
        raise UploadError("Missing WINFLOW_UPLOAD_TOKEN or --token. Upload endpoints require explicit authentication.")
    return token


def upload_snapshot(
    snapshot: dict[str, Any],
    server_url: str | None,
    upload_token: str | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    body = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
    request = Request(
        _server_url(server_url),
        data=body,
        headers={
            "Authorization": f"Bearer {_token(upload_token)}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {"ok": True}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise UploadError(f"Upload failed with HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise UploadError(f"Upload failed: {exc.reason}") from exc


def upload_icon(icon_path: Path, server_url: str | None, upload_token: str | None = None, timeout: int = 15) -> str:
    data = icon_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    payload = {
        "hash": digest,
        "filename": icon_path.name,
        "data": base64.b64encode(data).decode("ascii"),
    }
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        _icon_server_url(server_url),
        data=body,
        headers={
            "Authorization": f"Bearer {_token(upload_token)}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            result = json.loads(raw) if raw else {}
            url = result.get("url")
            if not isinstance(url, str) or not url:
                raise UploadError("Icon upload response is missing url")
            return url
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise UploadError(f"Icon upload failed with HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise UploadError(f"Icon upload failed: {exc.reason}") from exc


def sync_snapshot_icons(snapshot: dict[str, Any], server_url: str | None, upload_token: str | None = None) -> dict[str, Any]:
    """只替换应用级条目中的本地 exe 图标 URL。"""
    icon_cache: dict[str, str] = {}

    def replace_icon(item: dict[str, Any]) -> None:
        icon = item.get("icon")
        if not isinstance(icon, str) or not icon.startswith("/static/exe-icons/"):
            return
        local_path = _local_exe_icon_path(icon)
        if local_path is None:
            return
        if not local_path.is_file():
            return
        cache_key = str(local_path)
        if cache_key not in icon_cache:
            icon_cache[cache_key] = upload_icon(local_path, server_url, upload_token)
        item["icon"] = icon_cache[cache_key]

    for app in snapshot.get("apps", []):
        if isinstance(app, dict):
            replace_icon(app)

    return snapshot


def _local_exe_icon_path(icon_url: str) -> Path | None:
    relative = icon_url.removeprefix("/static/exe-icons/")
    parts = PurePosixPath(relative).parts
    if not parts or any(part in {"", ".", ".."} or "\\" in part for part in parts):
        return None
    target = (EXE_ICON_DIR.joinpath(*parts)).resolve()
    root = EXE_ICON_DIR.resolve()
    if root not in [target, *target.parents]:
        return None
    return target


def _pending_path(snapshot: dict[str, Any]) -> Path:
    device_id = str(snapshot.get("device_id") or "unknown").replace("/", "_").replace("\\", "_")
    day = str(snapshot.get("day") or time.strftime("%Y-%m-%d"))
    return PENDING_DIR / f"{device_id}-{day}.json"


def save_pending_snapshot(snapshot: dict[str, Any]) -> Path:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    path = _pending_path(snapshot)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def upload_usage(day: str | None = None, *, server_url: str | None = None, upload_token: str | None = None) -> dict[str, Any]:
    load_env_files()
    target = _configured_server_url(server_url)
    snapshot = build_usage_snapshot(day)

    try:
        sync_snapshot_icons(snapshot, target, upload_token)
        result = upload_snapshot(snapshot, target, upload_token)
        pending = _pending_path(snapshot)
        if pending.exists():
            pending.unlink()
        return result
    except Exception:
        save_pending_snapshot(snapshot)
        raise


def upload_pending(*, server_url: str | None = None, upload_token: str | None = None) -> int:
    load_env_files()
    target = _configured_server_url(server_url)
    if not PENDING_DIR.is_dir():
        return 0

    uploaded = 0
    for path in sorted(PENDING_DIR.glob("*.json")):
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        sync_snapshot_icons(snapshot, target, upload_token)
        upload_snapshot(snapshot, target, upload_token)
        path.unlink()
        uploaded += 1
    return uploaded


def upload_loop(
    day: str | None = None,
    *,
    server_url: str | None = None,
    upload_token: str | None = None,
    interval_seconds: int = 300,
) -> None:
    load_env_files()
    target = _configured_server_url(server_url)
    interval = max(30, int(interval_seconds or 300))
    print(f"Winflow uploader started: interval={interval}s, target={target}")
    while True:
        try:
            pending_count = upload_pending(server_url=target, upload_token=upload_token)
            if pending_count:
                print(f"[{time.strftime('%H:%M:%S')}] Uploaded {pending_count} pending snapshots")
            result = upload_usage(day, server_url=target, upload_token=upload_token)
            print(f"[{time.strftime('%H:%M:%S')}] Upload succeeded: {json.dumps(result, ensure_ascii=False)}")
        except Exception as exc:
            print(f"[{time.strftime('%H:%M:%S')}] Upload failed; snapshot saved for retry: {exc}")
        time.sleep(interval)
