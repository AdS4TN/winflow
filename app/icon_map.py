from __future__ import annotations

import json
from pathlib import Path

from .config import DATA_DIR, PACKAGE_STATIC_DIR, PROJECT_ROOT

ICON_MAP_PATH = DATA_DIR / "icon_map.json"
STATIC_ICON_ROOT = PACKAGE_STATIC_DIR / "icons"

DEFAULT_ICON_COLOR = "#64748b"
DEFAULT_TEXT_COLOR = "#f8fafc"

DEFAULT_ICON_MAP: dict[str, dict[str, dict[str, str]]] = {
    "apps": {
        "Chrome": {"icon": "/static/icons/apps/chrome.svg", "color": "#22c55e", "text_color": "#052e16"},
        "Edge": {"icon": "/static/icons/apps/edge.svg", "color": "#0ea5e9", "text_color": "#031927"},
        "Brave": {"icon": "🦁", "color": "#fb923c", "text_color": "#431407"},
        "Firefox": {"icon": "🦊", "color": "#f97316", "text_color": "#431407"},
        "VS Code": {"icon": "/static/icons/apps/vscode.svg", "color": "#3b82f6", "text_color": "#eff6ff"},
        "VS Code Insiders": {"icon": "/static/icons/apps/vscode.svg", "color": "#22c55e", "text_color": "#052e16"},
        "Cursor": {"icon": "/static/icons/apps/cursor.svg", "color": "#111827", "text_color": "#f9fafb"},
        "Windows Terminal": {"icon": "/static/icons/apps/terminal.svg", "color": "#111827", "text_color": "#f9fafb"},
        "PowerShell": {"icon": "/static/icons/apps/powershell.svg", "color": "#2563eb", "text_color": "#eff6ff"},
        "Command Prompt": {"icon": "/static/icons/apps/terminal.svg", "color": "#111827", "text_color": "#f9fafb"},
        "File Explorer": {"icon": "/static/icons/apps/explorer.svg", "color": "#f59e0b", "text_color": "#422006"},
        "WeChat": {"icon": "💬", "color": "#22c55e", "text_color": "#052e16"},
        "QQ": {"icon": "Q", "color": "#38bdf8", "text_color": "#082f49"},
        "TIM": {"icon": "T", "color": "#38bdf8", "text_color": "#082f49"},
        "Notepad": {"icon": "📝", "color": "#94a3b8", "text_color": "#0f172a"},
        "Notepad++": {"icon": "N++", "color": "#84cc16", "text_color": "#1a2e05"},
        "Obsidian": {"icon": "◆", "color": "#7c3aed", "text_color": "#f5f3ff"},
        "Typora": {"icon": "T", "color": "#94a3b8", "text_color": "#0f172a"},
        "Codex": {"icon": "✦", "color": "#10b981", "text_color": "#022c22"},
    },
}


def ensure_icon_map_file(path: Path = ICON_MAP_PATH) -> None:
    """确保本地有一份可编辑的 icon 映射配置。"""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULT_ICON_MAP, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_icon_map(path: Path = ICON_MAP_PATH) -> dict[str, dict[str, dict[str, str]]]:
    """读取 icon 映射配置；配置缺失或损坏时回退到内置映射。"""
    ensure_icon_map_file(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_ICON_MAP

    result = {"apps": dict(DEFAULT_ICON_MAP["apps"])}
    if isinstance(raw, dict):
        for section in ("apps",):
            custom = raw.get(section)
            if isinstance(custom, dict):
                for key, value in custom.items():
                    if isinstance(key, str) and isinstance(value, dict):
                        result[section][key] = _normalize_icon_entry(value)
    return result


def icon_for_app(app_name: str, icon_map: dict[str, dict[str, dict[str, str]]] | None = None) -> dict[str, str]:
    return _icon_for("apps", app_name, icon_map)


def serialize_icon_map() -> dict[str, object]:
    """给调试/前端预览使用，不包含任何个人数据。"""
    return {
        "path": _safe_public_path(ICON_MAP_PATH, fallback="<winflow-data>/icon_map.json"),
        "static_icon_root": "static/icons",
        "map": load_icon_map(),
    }


def _safe_public_path(path: Path, *, fallback: str) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return fallback


def _icon_for(
    section: str,
    key: str,
    icon_map: dict[str, dict[str, dict[str, str]]] | None = None,
) -> dict[str, str]:
    mapping = icon_map or load_icon_map()
    entries = mapping.get(section, {})
    exact = entries.get(str(key or ""))
    if exact:
        return dict(exact)
    lowered = str(key or "").strip().lower()
    for candidate, entry in entries.items():
        if candidate.strip().lower() == lowered:
            return dict(entry)
    return _fallback_icon_entry(str(key or ""))


def _normalize_icon_entry(value: dict[str, object]) -> dict[str, str]:
    icon = str(value.get("icon") or value.get("icon_url") or value.get("icon_text") or "?")
    color = str(value.get("color") or DEFAULT_ICON_COLOR)
    text_color = str(value.get("text_color") or value.get("textColor") or DEFAULT_TEXT_COLOR)
    return {"icon": icon, "color": color, "text_color": text_color}


def _fallback_icon_entry(label: str) -> dict[str, str]:
    clean = label.strip()
    icon = "?"
    if clean:
        icon = clean[:2].upper() if clean.isascii() else clean[:1]
    return {"icon": icon, "color": _hash_color(clean), "text_color": DEFAULT_TEXT_COLOR}


def _hash_color(value: str) -> str:
    palette = [
        "#64748b",
        "#71717a",
        "#78716c",
        "#0f766e",
        "#7c3aed",
        "#b45309",
        "#be123c",
        "#0369a1",
    ]
    total = sum(ord(ch) for ch in value)
    return palette[total % len(palette)]
