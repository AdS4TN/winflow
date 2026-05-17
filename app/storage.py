from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from .browser_history import BrowserVisit
from .config import DATA_DIR, DB_PATH
from .windows_activity import ForegroundWindow

SCHEMA_VERSION = 1


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

            CREATE TABLE IF NOT EXISTS browser_visits (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              browser TEXT NOT NULL,
              profile TEXT NOT NULL,
              visit_ts INTEGER NOT NULL,
              url TEXT NOT NULL,
              title TEXT,
              visit_count INTEGER NOT NULL DEFAULT 0,
              typed_count INTEGER NOT NULL DEFAULT 0,
              created_at INTEGER NOT NULL,
              UNIQUE(browser, profile, visit_ts, url)
            );

            CREATE INDEX IF NOT EXISTS idx_browser_visits_time
              ON browser_visits(visit_ts);
            CREATE INDEX IF NOT EXISTS idx_browser_visits_browser
              ON browser_visits(browser, profile);
            """
        )
        con.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )


def _same_window(row: sqlite3.Row, window: ForegroundWindow) -> bool:
    return (
        int(row["pid"] or 0) == window.pid
        and str(row["process_name"] or "") == window.process_name
        and str(row["window_title"] or "") == window.title
    )


def record_foreground_window(window: ForegroundWindow, now_ts: Optional[int] = None) -> str:
    """写入前台窗口事件。连续相同窗口会延长上一条记录。"""
    init_db()
    now = int(now_ts or time.time())
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
                window.title,
                now,
            ),
        )
        return "inserted"


def insert_browser_visits(visits: Iterable[BrowserVisit]) -> int:
    init_db()
    now = int(time.time())
    inserted = 0
    with connect() as con:
        for visit in visits:
            cur = con.execute(
                """
                INSERT OR IGNORE INTO browser_visits(
                  browser, profile, visit_ts, url, title, visit_count, typed_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    visit.browser,
                    visit.profile,
                    visit.visit_time,
                    visit.url,
                    visit.title,
                    visit.visit_count,
                    visit.typed_count,
                    now,
                ),
            )
            inserted += cur.rowcount
    return inserted


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


def fetch_browser_visits(start_ts: int, end_ts: int) -> list[sqlite3.Row]:
    init_db()
    with connect() as con:
        return list(
            con.execute(
                """
                SELECT * FROM browser_visits
                WHERE visit_ts BETWEEN ? AND ?
                ORDER BY visit_ts ASC, id ASC
                """,
                (start_ts, end_ts),
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
        browser_rows = con.execute(
            """
            SELECT browser, COUNT(*) AS count
            FROM browser_visits
            WHERE visit_ts BETWEEN ? AND ?
            GROUP BY browser
            ORDER BY count DESC
            """,
            (start_ts, end_ts),
        ).fetchall()
    return {
        "apps": [dict(row) for row in app_rows],
        "browsers": [dict(row) for row in browser_rows],
    }
