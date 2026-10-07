"""Human descriptions instead of numbers: fists, directions, colours."""

from __future__ import annotations

import math

DIRECTIONS_LOC = (
    "na severu",
    "na severovýchodě",
    "na východě",
    "na jihovýchodě",
    "na jihu",
    "na jihozápadě",
    "na západě",
    "na severozápadě",
)
DIRECTIONS_ACC = (
    "sever",
    "severovýchod",
    "východ",
    "jihovýchod",
    "jih",
    "jihozápad",
    "západ",
    "severozápad",
)
ARROWS = ("↑", "↗", "→", "↘", "↓", "↙", "←", "↖")

#: altitude limits (degrees) between the height words
HEIGHT_WORDS = (
    (0.0, "těsně nad obzorem"),
    (10.0, "nízko"),
    (25.0, "napůl k nebi"),
    (55.0, "vysoko"),
    (75.0, "skoro nad hlavou"),
)


def direction_index(az: float) -> int:
    return int(((az % 360.0) + 22.5) // 45.0) % 8


def direction_word(az: float) -> str:
    """``na jihovýchodě`` etc."""
    return DIRECTIONS_LOC[direction_index(az)]


def direction_name(az: float) -> str:
    """``jihovýchod`` etc. (for "díváš se na …")."""
    return DIRECTIONS_ACC[direction_index(az)]


def direction_arrow(az: float) -> str:
    return ARROWS[direction_index(az)]


def height_word(alt: float) -> str:
    if alt < 0:
        return "pod obzorem"
    word = HEIGHT_WORDS[0][1]
    for limit, w in HEIGHT_WORDS:
        if alt >= limit:
            word = w
    return word


def fists(alt: float) -> float:
    """Altitude in fists at arm's length (1 fist ≈ 10°), rounded to halves."""
    return round(max(0.0, alt) / 10.0 * 2) / 2


def fist_text(alt: float) -> str:
    """``asi 2 pěsti``, ``asi 1 pěst``, ``asi 5 pěstí``, ``asi půl pěsti``."""
    n = fists(alt)
    if n < 0.5:
        return "kousek nad obzorem"
    if n == 0.5:
        return "asi půl pěsti"
    if n == int(n):
        k = int(n)
        word = "pěst" if k == 1 else "pěsti" if k < 5 else "pěstí"
        return f"asi {k} {word}"
    return f"asi {str(n).replace('.', ',')} pěsti"


def fist_range_text(alt: float) -> str:
    """``6–7 pěstí`` style range for high objects."""
    lo = math.floor(alt / 10.0)
    hi = lo + 1
    if lo < 1:
        return fist_text(alt)
    word = "pěsti" if hi < 5 else "pěstí"
    return f"{lo}–{hi} {word}"


def position_sentence(alt: float, az: float) -> str:
    """``Nízko na jihovýchodě, asi 2 pěsti nad obzorem.``"""
    if alt < 0:
        return f"Teď je pod obzorem ({direction_word(az)})."
    hw = height_word(alt)
    if alt >= 75:
        return "Skoro přímo nad hlavou."
    if alt < 10:
        return f"Těsně nad obzorem {direction_word(az)}, {fist_text(alt)}."
    if hw == "napůl k nebi" and 35 <= alt < 50:
        return f"{direction_word(az).capitalize()}, napůl k nebi ({fist_text(alt)})."
    amount = fist_range_text(alt) if alt >= 55 else fist_text(alt)
    return f"{hw.capitalize()} {direction_word(az)}, {amount} nad obzorem."


def _inflect(adj: str, gender: str) -> str:
    if gender == "f":
        return adj[:-1] + "á"
    if gender == "n":
        return adj[:-1] + "é"
    return adj


def color_word(bv: float | None, feminine: bool = False, gender: str | None = None) -> str:
    """Colour from B−V in words: masc. ("bod"), fem. ("hvězda") or neuter ("světlo")."""
    if bv is None or bv != bv:
        base = "bílý"
    elif bv < -0.05:
        base = "bílomodrý"
    elif bv < 0.3:
        base = "bílý"
    elif bv < 0.6:
        base = "nažloutle bílý"
    elif bv < 1.0:
        base = "nažloutlý"
    elif bv < 1.45:
        base = "oranžový"
    else:
        base = "červenooranžový"
    return _inflect(base, gender or ("f" if feminine else "m"))


def brightness_word(mag: float, feminine: bool = False, gender: str | None = None) -> str:
    if mag < -3:
        w = "oslnivě jasný"
    elif mag < -1:
        w = "velmi jasný"
    elif mag < 0.5:
        w = "jasný"
    elif mag < 1.5:
        w = "dobře viditelný"
    elif mag < 2.5:
        w = "středně jasný"
    else:
        w = "slabý"
    return _inflect(w, gender or ("f" if feminine else "m"))


def twinkle_text(is_planet: bool) -> str:
    return "nebliká (planety neblikají)" if is_planet else "bliká"


def degrees_text(value: float) -> str:
    return f"{value:.0f}°"
