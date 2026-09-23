"""Stable fictional schedule with an optional public-listings adapter.

The default experience is deterministic and works offline. A third-party
XMLTV feed can be enabled deliberately for local exploration, but it is not
described as open data and its contents are never committed.
"""
from __future__ import annotations

import gzip
import io
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent
CACHE_PATH = ROOT / "data" / "schedule_cache.csv"
GUIDE_URL = "https://iptv-epg.org/files/epg-ch.xml.gz"
SOURCE_LABEL = "IPTV-EPG.org publicly accessible XMLTV guide for Switzerland"
ZURICH = ZoneInfo("Europe/Zurich")

CHANNELS = {"3+.ch": "3+", "4+.ch": "4+", "5+.ch": "5+", "6+.ch": "6+"}
COLUMNS = [
    "programme_id",
    "channel",
    "title",
    "genre",
    "start",
    "stop",
    "duration_min",
    "source",
]


def _parse_time(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y%m%d%H%M%S %z").astimezone(ZURICH)


def parse_xmltv(stream: io.IOBase) -> pd.DataFrame:
    """Stream-parse XMLTV and keep only the four channels."""
    rows = []
    for _, element in ET.iterparse(stream, events=("end",)):
        if element.tag != "programme":
            continue
        channel = CHANNELS.get(element.get("channel", ""))
        if channel:
            start = _parse_time(element.get("start"))
            stop = _parse_time(element.get("stop"))
            title = element.findtext("title") or "(untitled)"
            genre = element.findtext("category") or "Unbekannt"
            rows.append(
                {
                    "programme_id": f"PUB-{channel}-{start:%Y%m%d%H%M}",
                    "channel": channel,
                    "title": title.strip(),
                    "genre": genre.strip(),
                    "start": start,
                    "stop": stop,
                    "duration_min": int((stop - start).total_seconds() // 60),
                    "source": "real",
                }
            )
        element.clear()
    frame = pd.DataFrame(rows, columns=COLUMNS)
    return frame.sort_values(["channel", "start"]).reset_index(drop=True)


def _resolve_redirect(url: str) -> str:
    """iptv-epg.org answers with an HTML meta refresh to a hashed file path."""
    with urllib.request.urlopen(url, timeout=30) as response:
        head = response.read(2048)
    if head[:2] == b"\x1f\x8b":
        return url
    marker = b"url='"
    start = head.find(marker)
    if start < 0:
        raise ValueError("Guide URL returned neither gzip nor a redirect page")
    end = head.find(b"'", start + len(marker))
    return head[start + len(marker):end].decode()


def fetch_schedule(url: str = GUIDE_URL) -> pd.DataFrame:
    target = _resolve_redirect(url)
    with urllib.request.urlopen(target, timeout=120) as response:
        with gzip.GzipFile(fileobj=response) as unzipped:
            return parse_xmltv(unzipped)


def synthetic_schedule(days: int = 7, anchor: datetime | None = None) -> pd.DataFrame:
    """Offline fallback with the same columns. Invented titles, labelled synthetic."""
    anchor = (anchor or datetime.now(ZURICH)).replace(hour=6, minute=0, second=0, microsecond=0)
    blocks = [
        (6, 360, "Einkauf", "Teleshopping"),
        (12, 60, "Sitcom", "Sitcom block"),
        (13, 60, "Reality", "Reality show"),
        (14, 120, "Dokumentation", "Documentary"),
        (16, 60, "Sitcom", "Sitcom block"),
        (17, 60, "Reality", "Reality show"),
        (18, 60, "Krimi Drama", "Crime series"),
        (19, 75, "Sitcom", "Sitcom block"),
        (20, 105, "Film", "Prime-time film"),
        (22, 60, "Drama Serie", "Late drama"),
        (23, 60, "Film", "Late film"),
    ]
    rows = []
    for channel in CHANNELS.values():
        for day in range(days):
            base = anchor + timedelta(days=day)
            for hour, minutes, genre, title in blocks:
                start = base.replace(hour=hour, minute=15 if hour == 20 else 0)
                stop = start + timedelta(minutes=minutes)
                rows.append(
                    {
                        "programme_id": f"DEMO-{channel}-{start:%Y%m%d%H%M}",
                        "channel": channel,
                        "title": title,
                        "genre": genre,
                        "start": start,
                        "stop": stop,
                        "duration_min": minutes,
                        "source": "synthetic",
                    }
                )
    return pd.DataFrame(rows, columns=COLUMNS)


def stable_demo_schedule() -> pd.DataFrame:
    """Fixed schedule used by tests and the default public experience."""
    anchor = datetime(2026, 9, 21, 6, 0, tzinfo=ZURICH)
    return synthetic_schedule(anchor=anchor)


def public_refresh_enabled() -> bool:
    """Fail closed until source reuse has been reviewed deliberately."""
    return os.getenv("SELLABLE_ENABLE_PUBLIC_SCHEDULE_REFRESH", "0") == "1"


def load_schedule(refresh: bool = False, allow_remote: bool | None = None) -> tuple[pd.DataFrame, str]:
    """Return a stable grid unless an explicitly enabled refresh is requested."""
    allow_remote = public_refresh_enabled() if allow_remote is None else allow_remote
    if not refresh or not allow_remote:
        return stable_demo_schedule(), "Stable fictional programme grid"
    if CACHE_PATH.exists() and not refresh:
        frame = pd.read_csv(CACHE_PATH)
        for column in ("start", "stop"):
            frame[column] = pd.to_datetime(frame[column], utc=True).dt.tz_convert(ZURICH)
        return frame, f"{SOURCE_LABEL} (local cache)"
    try:
        frame = fetch_schedule()
        if frame.empty:
            raise ValueError("No 3+/4+/5+/6+ programmes in the guide")
        from contracts import programme_errors
        errors = programme_errors(frame)
        if errors:
            raise ValueError("; ".join(errors))
    except Exception as error:  # network, format, or empty guide
        return stable_demo_schedule(), f"Stable fictional grid; refresh failed ({type(error).__name__})"
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(CACHE_PATH, index=False)
    return frame, f"{SOURCE_LABEL} (fetched now)"


if __name__ == "__main__":
    grid, source = load_schedule(refresh=True, allow_remote=True)
    print(source)
    print(grid.groupby("channel").size().to_string())
