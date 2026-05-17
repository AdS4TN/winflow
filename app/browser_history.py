from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

from .config import BROWSER_HISTORY_LOOKBACK_DAYS

WINDOWS_EPOCH_OFFSET_MICROSECONDS = 11644473600000000


@dataclass(frozen=True)
class BrowserProfile:
    browser: str
    profile: str
    history_path: Path


@dataclass(frozen=True)
class BrowserVisit:
    browser: str
    profile: str
    visit_time: int
    url: str
    title: str
    visit_count: int
    typed_count: int


def _local_app_data() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", ""))


def _app_data() -> Path:
    return Path(os.environ.get("APPDATA", ""))


def discover_chromium_profiles() -> list[BrowserProfile]:
    candidates = [
        ("Chrome", _local_app_data() / "Google" / "Chrome" / "User Data"),
        ("Edge", _local_app_data() / "Microsoft" / "Edge" / "User Data"),
        ("Brave", _local_app_data() / "BraveSoftware" / "Brave-Browser" / "User Data"),
    ]
    profiles: list[BrowserProfile] = []
    for browser, root in candidates:
        if not root.exists():
            continue
        for profile_dir in root.iterdir():
            if not profile_dir.is_dir():
                continue
            if profile_dir.name != "Default" and not profile_dir.name.startswith("Profile"):
                continue
            history = profile_dir / "History"
            if history.exists():
                profiles.append(BrowserProfile(browser, profile_dir.name, history))
    return profiles


def discover_firefox_profiles() -> list[BrowserProfile]:
    root = _app_data() / "Mozilla" / "Firefox" / "Profiles"
    profiles: list[BrowserProfile] = []
    if not root.exists():
        return profiles
    for profile_dir in root.iterdir():
        places = profile_dir / "places.sqlite"
        if places.exists():
            profiles.append(BrowserProfile("Firefox", profile_dir.name, places))
    return profiles


def discover_browser_profiles() -> list[BrowserProfile]:
    return discover_chromium_profiles() + discover_firefox_profiles()


def _copy_locked_db(path: Path) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="winflow_browser_"))
    target = temp_dir / path.name
    shutil.copy2(path, target)
    return target


def chrome_time_to_unix_seconds(value: int) -> int:
    return int((value - WINDOWS_EPOCH_OFFSET_MICROSECONDS) / 1_000_000)


def firefox_time_to_unix_seconds(value: int) -> int:
    return int(value / 1_000_000)


def read_chromium_history(profile: BrowserProfile, since_ts: int) -> Iterator[BrowserVisit]:
    copied = _copy_locked_db(profile.history_path)
    try:
        con = sqlite3.connect(f"file:{copied}?mode=ro", uri=True)
        try:
            has_visits = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='visits'"
            ).fetchone()
            has_urls = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='urls'"
            ).fetchone()
            if not has_visits or not has_urls:
                return
            min_chrome_time = since_ts * 1_000_000 + WINDOWS_EPOCH_OFFSET_MICROSECONDS
            rows = con.execute(
                """
                SELECT urls.url, urls.title, urls.visit_count, urls.typed_count, visits.visit_time
                FROM visits
                JOIN urls ON urls.id = visits.url
                WHERE visits.visit_time >= ?
                ORDER BY visits.visit_time ASC
                """,
                (min_chrome_time,),
            )
            for url, title, visit_count, typed_count, visit_time in rows:
                if not url:
                    continue
                yield BrowserVisit(
                    browser=profile.browser,
                    profile=profile.profile,
                    visit_time=chrome_time_to_unix_seconds(int(visit_time)),
                    url=str(url),
                    title=str(title or ""),
                    visit_count=int(visit_count or 0),
                    typed_count=int(typed_count or 0),
                )
        finally:
            con.close()
    finally:
        shutil.rmtree(copied.parent, ignore_errors=True)


def read_firefox_history(profile: BrowserProfile, since_ts: int) -> Iterator[BrowserVisit]:
    copied = _copy_locked_db(profile.history_path)
    try:
        con = sqlite3.connect(f"file:{copied}?mode=ro", uri=True)
        try:
            min_firefox_time = since_ts * 1_000_000
            rows = con.execute(
                """
                SELECT moz_places.url, moz_places.title, moz_places.visit_count,
                       moz_historyvisits.visit_date
                FROM moz_historyvisits
                JOIN moz_places ON moz_places.id = moz_historyvisits.place_id
                WHERE moz_historyvisits.visit_date >= ?
                ORDER BY moz_historyvisits.visit_date ASC
                """,
                (min_firefox_time,),
            )
            for url, title, visit_count, visit_time in rows:
                if not url:
                    continue
                yield BrowserVisit(
                    browser=profile.browser,
                    profile=profile.profile,
                    visit_time=firefox_time_to_unix_seconds(int(visit_time)),
                    url=str(url),
                    title=str(title or ""),
                    visit_count=int(visit_count or 0),
                    typed_count=0,
                )
        finally:
            con.close()
    finally:
        shutil.rmtree(copied.parent, ignore_errors=True)


def read_profile_history(profile: BrowserProfile, since_ts: int) -> Iterator[BrowserVisit]:
    try:
        if profile.browser in {"Chrome", "Edge", "Brave"}:
            yield from read_chromium_history(profile, since_ts)
        elif profile.browser == "Firefox":
            yield from read_firefox_history(profile, since_ts)
    except Exception as exc:
        # 浏览器历史采集是辅助能力，不应影响主采集循环。
        print(f"[browser] 跳过 {profile.browser}/{profile.profile}: {exc}")


def read_recent_browser_history(lookback_days: int = BROWSER_HISTORY_LOOKBACK_DAYS) -> list[BrowserVisit]:
    since_ts = int(time.time()) - lookback_days * 86400
    visits: list[BrowserVisit] = []
    for profile in discover_browser_profiles():
        visits.extend(read_profile_history(profile, since_ts))
    visits.sort(key=lambda item: item.visit_time)
    return visits
