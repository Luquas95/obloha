"""Moon phase disc (braille) and the night timeline as plain data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from obloha.core.almanac import altitude_series, sun_altitudes
from obloha.core.bodies import BODY_BY_ID, BodyInfo
from obloha.core.location import Location
from obloha.render.canvas import Canvas, Frame

SPARK = " ▁▂▃▄▅▆▇█"


def moon_disc(
    illumination: float,
    waxing: bool,
    cols: int = 8,
    rows: int = 4,
    lit: int = 0xF4F1E0,
    dark: int = 0x2F3A55,
    bg: int = 0x0D1222,
    half: bool = False,
) -> Frame:
    """Moon disc: lit part bright, the rest dim (northern hemisphere orientation)."""
    c = Canvas(cols, rows, half=half, bg=bg)
    w, h = c.width, c.height
    r = min(w / 2.0, h / 2.0) - 0.3
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    ys, xs = np.mgrid[0:h, 0:w]
    dx = (xs - cx) / r
    dy = (ys - cy) / r
    inside = dx * dx + dy * dy <= 1.0
    # terminator: x = k * sqrt(1 - y^2), k from +1 (new) to -1 (full)
    k = 1.0 - 2.0 * illumination
    edge = k * np.sqrt(np.clip(1 - dy * dy, 0, 1))
    lit_mask = dx > edge if waxing else dx < -edge
    lit_mask &= inside
    dark_mask = inside & ~lit_mask
    c.dots(xs[dark_mask].astype(float), ys[dark_mask].astype(float), dark, 0)
    c.dots(xs[lit_mask].astype(float), ys[lit_mask].astype(float), lit, 1)
    return c.frame()


@dataclass(frozen=True)
class TimelineRow:
    label: str
    cells: str  # one character per column
    color: int


@dataclass(frozen=True)
class Timeline:
    start: datetime
    step: timedelta
    columns: int
    hour_marks: list[tuple[int, str]]  # (column, "21")
    rows: list[TimelineRow]
    sky_levels: list[int]  # 0 day .. 4 astronomical night, per column


def _hour_marks(start: datetime, step: timedelta, cols: int, zone: object) -> list[tuple[int, str]]:
    marks = []
    for i in range(cols):
        t = (start + step * i).astimezone(zone)  # type: ignore[arg-type]
        prev = (start + step * (i - 1)).astimezone(zone) if i else None  # type: ignore[arg-type]
        if prev is None or t.hour != prev.hour:
            marks.append((i, f"{t.hour:02d}"))
    return marks


def night_timeline(
    start: datetime,
    end: datetime,
    location: Location,
    columns: int,
    bodies: list[BodyInfo] | None = None,
    scores: list[tuple[datetime, int]] | None = None,
) -> Timeline:
    """Columns from ``start`` to ``end``: sky darkness, bodies above horizon, score."""
    columns = max(10, columns)
    step = (end - start) / columns
    times = [start + step * (i + 0.5) for i in range(columns)]
    sun = sun_altitudes(times, location)
    levels = [
        4 if s < -18 else 3 if s < -12 else 2 if s < -6 else 1 if s < -0.833 else 0 for s in sun
    ]
    sky_chars = {0: " ", 1: "░", 2: "▒", 3: "▓", 4: "█"}
    rows = [TimelineRow("obloha", "".join(sky_chars[v] for v in levels), 0x3D5A8A)]
    for info in bodies or [BODY_BY_ID["moon"]]:
        alt = altitude_series(info, times, location)
        cells = "".join("━" if a > 0 else " " for a in alt)
        rows.append(TimelineRow(info.name, cells, info.color_int))
    if scores:
        smap = {t.replace(minute=0, second=0, microsecond=0): s for t, s in scores}
        cells = ""
        for t in times:
            s = smap.get(t.replace(minute=0, second=0, microsecond=0), 0)
            cells += SPARK[min(8, round(s / 100 * 8))]
        rows.append(TimelineRow("pozorov.", cells, 0x7BD88F))
    marks = _hour_marks(start, step, columns, location.zone)
    return Timeline(start, step, columns, marks, rows, levels)


def now_column(tl: Timeline, now: datetime) -> int | None:
    if now < tl.start or now >= tl.start + tl.step * tl.columns:
        return None
    return int((now - tl.start) / tl.step)
