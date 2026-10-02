"""Colour themes (dark, light, night vision) and star colours."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any

import numpy as np
from numpy.typing import NDArray

from obloha.render.color import blend, hex_to_int, to_night


@dataclass(frozen=True)
class Theme:
    """Named colours (RGB ints). ``night`` themes contain only reds."""

    name: str
    background: int
    panel: int
    sky: int
    sky_day: int
    sky_glow: int  # light pollution near the horizon
    ground: int
    roofs: int
    selection: int
    text: int
    muted: int
    suppressed: int
    border: int
    accent: int
    accent2: int
    const_lines: int
    const_borders: int
    const_names: int
    horizon: int
    grid: int
    ecliptic: int
    milky_way: int
    moon: int
    sun: int
    satellite: int
    good: int
    bad: int
    highlight: int
    guide: int
    night: bool = False

    def css_vars(self) -> dict[str, str]:
        """Colour values for Textual CSS variables."""
        return {
            f.name.replace("_", "-"): f"#{getattr(self, f.name):06x}"
            for f in fields(self)
            if isinstance(getattr(self, f.name), int)
            and not isinstance(getattr(self, f.name), bool)
        }


def _t(**kw: str) -> dict[str, Any]:
    return {k: hex_to_int(v) for k, v in kw.items()}


DARK = Theme(
    name="tmavé",
    **_t(
        background="#0a0e1a",
        panel="#0d1222",
        sky="#070b16",
        sky_day="#2d5f94",
        sky_glow="#222b45",
        ground="#04060b",
        roofs="#04060b",
        selection="#1c2a48",
        text="#d6dcea",
        muted="#7a86a3",
        suppressed="#2f3a55",
        border="#2a3452",
        accent="#8fb8ff",
        accent2="#c9a8ff",
        const_lines="#3d5a8a",
        const_borders="#2a3a5c",
        const_names="#56688f",
        horizon="#5a6a8f",
        grid="#26314d",
        ecliptic="#7a6a3a",
        milky_way="#1a2340",
        moon="#f4f1e0",
        sun="#ffe27a",
        satellite="#9ef0c0",
        good="#7bd88f",
        bad="#ff7a85",
        highlight="#ffd36b",
        guide="#c9a8ff",
    ),
)

LIGHT = Theme(
    name="světlé",
    **_t(
        background="#f3f5fa",
        panel="#e8ecf5",
        sky="#0f1830",
        sky_day="#6fa3d8",
        sky_glow="#2a3556",
        ground="#c9cfdc",
        roofs="#5a6274",
        selection="#c8d6f0",
        text="#1b2233",
        muted="#5a6478",
        suppressed="#a6aec0",
        border="#9aa6c0",
        accent="#2456b3",
        accent2="#7a4fc0",
        const_lines="#4d6ea8",
        const_borders="#3a4f78",
        const_names="#7f90b8",
        horizon="#7f8db0",
        grid="#2c3a5e",
        ecliptic="#a08a40",
        milky_way="#1d2848",
        moon="#f4f1e0",
        sun="#ffe27a",
        satellite="#9ef0c0",
        good="#1f8a3a",
        bad="#c0303c",
        highlight="#ffcc33",
        guide="#c9a8ff",
    ),
)


def night_theme(base: Theme = DARK) -> Theme:
    """Night vision: every colour mapped to red (fixed key colours from the design)."""
    mapped = {
        f.name: to_night(getattr(base, f.name))
        for f in fields(base)
        if f.name not in ("name", "night")
    }
    mapped.update(
        background=hex_to_int("#0a0000"),
        panel=hex_to_int("#0d0101"),
        sky=hex_to_int("#070000"),
        text=hex_to_int("#e0403a"),
        accent=hex_to_int("#ff5a4a"),
        muted=hex_to_int("#8a2622"),
        suppressed=hex_to_int("#3a0f0d"),
        border=hex_to_int("#4a1512"),
        selection=hex_to_int("#2a0806"),
    )
    return replace(base, name="noční vidění", night=True, **mapped)


NIGHT = night_theme()
THEMES: dict[str, Theme] = {"dark": DARK, "light": LIGHT, "night": NIGHT}

# B−V colour ramp from the design: blue-white → white → yellowish → orange → red-orange
_BV_STOPS = np.array([-0.3, 0.0, 0.6, 1.2, 1.8])
_BV_COLORS = [hex_to_int(c) for c in ("#bcd2ff", "#ffffff", "#fff1c4", "#ffc58a", "#ff9e70")]


def star_color(bv: float) -> int:
    """Colour of a star from its B−V index (NaN → white)."""
    if bv != bv:  # NaN
        return _BV_COLORS[1]
    if bv <= _BV_STOPS[0]:
        return _BV_COLORS[0]
    if bv >= _BV_STOPS[-1]:
        return _BV_COLORS[-1]
    i = int(np.searchsorted(_BV_STOPS, bv)) - 1
    f = (bv - _BV_STOPS[i]) / (_BV_STOPS[i + 1] - _BV_STOPS[i])
    return blend(_BV_COLORS[i], _BV_COLORS[i + 1], float(f))


def star_colors(bv: NDArray[np.float32]) -> NDArray[np.uint32]:
    return np.array([star_color(float(b)) for b in bv], dtype=np.uint32)
