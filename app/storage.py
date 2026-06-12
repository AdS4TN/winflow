from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from .config import DATA_DIR, DB_PATH
from .windows_activity import ForegroundWindow

SCHEMA_VERSION = 2
BROWSER_PROCESS_NAMES = {
    "chrome.exe",
    "msedge.exe",
    "brave.exe",
    "firefox.exe",
    "roxychrome.exe",
    "roxybrowser.exe",
}


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def connect(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    ensure_data_dir()
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        yield con
        con.commit()
    finally:
        con.close()


def init_db(db_path: Path = DB_PATH) -> None:
    with connect(db_path) as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS foreground_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              start_ts INTEGER NOT NULL,
              end_ts INTEGER,
              hwnd INTEGER,
              pid INTEGER,
              process_name TEXT NOT NULL,
              exe_path TEXT,
              window_title TEXT,
              created_at INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_foreground_events_start
              ON foreground_events(start_ts);
            CREATE INDEX IF NOT EXISTS idx_foreground_events_process
              ON foreground_events(process_name);
            """
        )
        con.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )


def _same_window(row: sqlite3.Row, window: ForegroundWindow) -> bool:
    window_title = safe_window_title(window.process_name, window.title)
    return (
        int(row["pid"] or 0) == window.pid
        and str(row["process_name"] or "") == window.process_name
        and str(row["window_title"] or "") == window_title
    )


def is_browser_process(process_name: str) -> bool:
    return (process_name or "").strip().lower() in BROWSER_PROCESS_NAMES


def safe_window_title(process_name: str, window_title: str | None = None) -> str:
    """浏览器窗口标题通常就是具体标签页标题，默认不再入库或输出。"""
    if is_browser_process(process_name):
        return "浏览器窗口"
    return str(window_title or "")


def record_foreground_window(window: ForegroundWindow, now_ts: Optional[int] = None) -> str:
    """写入前台窗口事件。连续相同窗口会延长上一条记录。"""
    init_db()
    now = int(now_ts or time.time())
    window_title = safe_window_title(window.process_name, window.title)
    with connect() as con:
        last = con.execute(
            "SELECT * FROM foreground_events ORDER BY start_ts DESC, id DESC LIMIT 1"
        ).fetchone()
        if last and _same_window(last, window):
            con.execute(
                "UPDATE foreground_events SET end_ts = ? WHERE id = ?",
                (now, last["id"]),
            )
            return "extended"
        if last and last["end_ts"] is None:
            con.execute(
                "UPDATE foreground_events SET end_ts = ? WHERE id = ?",
                (now, last["id"]),
            )
        con.execute(
            """
            INSERT INTO foreground_events(
              start_ts, end_ts, hwnd, pid, process_name, exe_path, window_title, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                now,
                window.hwnd,
                window.pid,
                window.process_name,
                window.exe_path,
                window_title,
                now,
            ),
        )
        return "inserted"


def fetch_foreground_events(start_ts: int, end_ts: int) -> list[sqlite3.Row]:
    init_db()
    with connect() as con:
        return list(
            con.execute(
                """
                SELECT * FROM foreground_events
                WHERE start_ts <= ? AND COALESCE(end_ts, start_ts) >= ?
                ORDER BY start_ts ASC, id ASC
                """,
                (end_ts, start_ts),
            )
        )

def fetch_stats(start_ts: int, end_ts: int) -> dict[str, Any]:
    init_db()
    with connect() as con:
        app_rows = con.execute(
            """
            SELECT process_name,
                   SUM(MAX(0, COALESCE(end_ts, start_ts) - start_ts)) AS seconds,
                   COUNT(*) AS count
            FROM foreground_events
            WHERE start_ts <= ? AND COALESCE(end_ts, start_ts) >= ?
            GROUP BY process_name
            ORDER BY seconds DESC
            LIMIT 20
            """,
            (end_ts, start_ts),
        ).fetchall()
    return {
        "apps": [dict(row) for row in app_rows],
        "browsers": [],
    }
