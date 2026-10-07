"""Czech formatting of times, numbers and durations."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

WEEKDAYS = ("po", "út", "st", "čt", "pá", "so", "ne")
TZ_CS = {"CET": "SEČ", "CEST": "SELČ"}


def num(value: float, digits: int = 1) -> str:
    """Decimal comma and real minus sign: ``-0.1`` -> ``−0,1``."""
    text = f"{value:.{digits}f}".replace(".", ",")
    return text.replace("-", "−")


def local(when: datetime, zone: ZoneInfo) -> datetime:
    return when.astimezone(zone)


def tz_abbr(when: datetime, zone: ZoneInfo) -> str:
    loc = when.astimezone(zone)
    name = loc.tzname() or ""
    if name in TZ_CS:
        return TZ_CS[name]
    if name and name[0] not in "+-":
        return name
    off = loc.utcoffset() or timedelta()
    total = int(off.total_seconds() // 60)
    sign = "+" if total >= 0 else "−"
    h, m = divmod(abs(total), 60)
    return f"UTC{sign}{h}" + (f":{m:02d}" if m else "")


def hm(when: datetime | None, zone: ZoneInfo) -> str:
    if when is None:
        return "—"
    return when.astimezone(zone).strftime("%H:%M")


def hms(when: datetime, zone: ZoneInfo) -> str:
    return when.astimezone(zone).strftime("%H:%M:%S")


def date_short(when: datetime, zone: ZoneInfo) -> str:
    """``1. 10.``"""
    d = when.astimezone(zone)
    return f"{d.day}. {d.month}."


def date_long(when: datetime, zone: ZoneInfo) -> str:
    """``čt 1. 10. 2026``"""
    d = when.astimezone(zone)
    return f"{WEEKDAYS[d.weekday()]} {d.day}. {d.month}. {d.year}"


def duration(td: timedelta) -> str:
    """``10 h 05 m``"""
    minutes = round(td.total_seconds() / 60)
    h, m = divmod(max(0, minutes), 60)
    return f"{h} h {m:02d} m"


def bar(fraction: float, width: int = 10, full: str = "█", empty: str = "░") -> str:
    n = max(0, min(width, round(fraction * width)))
    return full * n + empty * (width - n)


def plural(n: int, one: str, few: str, many: str) -> str:
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def local_zone() -> Any:
    """The user's own IANA time zone (``TZ`` or ``/etc/localtime``), DST aware."""
    import os
    from pathlib import Path

    name = os.environ.get("TZ", "").lstrip(":")
    candidates = [name] if name else []
    try:
        target = str(Path("/etc/localtime").resolve())
        if "zoneinfo/" in target:
            candidates.append(target.split("zoneinfo/", 1)[1])
    except OSError:  # pragma: no cover
        pass
    for cand in candidates:
        try:
            return ZoneInfo(cand)
        except (ValueError, KeyError, OSError):
            continue
    return datetime.now().astimezone().tzinfo
