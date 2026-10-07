""" "Co je to za světlo?": guess which object the user points at."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from obloha.beginner.describe import color_word, direction_word, fist_text, height_word
from obloha.core.coords import separation_deg
from obloha.core.objects import PLANET_BV
from obloha.core.sky import ObjectRef, SkyScene, limiting_magnitude_for_sun
from obloha.core.textnorm import fold

POINTING_SIGMA = 6.0  # degrees: how precisely people point at the sky
ALTERNATIVE_MIN = 0.08  # probability needed to mention an alternative


@dataclass(frozen=True)
class Candidate:
    ref: ObjectRef
    name: str
    kind: str  # "planeta", "hvězda", "Měsíc", "družice", "objekt"
    probability: float
    distance: float  # degrees from the pointed direction
    mag: float
    twinkles: bool
    explanation: str


@dataclass(frozen=True)
class Identification:
    candidates: tuple[Candidate, ...]
    alternatives: tuple[str, ...]  # Czech sentences ("pokud to bliká, …")

    @property
    def best(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None


def _prior(mag: float) -> float:
    """Brighter objects are more likely to be noticed."""
    return float(10 ** (-0.25 * mag))


def identify(
    scene: SkyScene,
    alt: float,
    az: float,
    moving: bool = False,
    user_limit: float = 3.5,
    limit: int = 4,
) -> Identification:
    """Rank visible objects by brightness × closeness to (alt, az)."""
    lim = limiting_magnitude_for_sun(scene.sun_alt, user_limit)
    raw: list[tuple[float, ObjectRef, str, str, float, float, bool]] = []
    cat = scene.cat
    if moving:
        for s in scene.satellites:
            if s.alt > 0:
                d = float(separation_deg(s.alt, s.az, alt, az))
                w = math.exp(-0.5 * (d / (POINTING_SIGMA * 2)) ** 2) * 5
                raw.append(
                    (
                        w,
                        ObjectRef("sat", s.name),
                        s.name,
                        "družice",
                        d,
                        s.mag if s.mag is not None else 2.0,
                        False,
                    )
                )
    else:
        up = (scene.star_alt > 0) & (cat.mag <= lim)
        for i in up.nonzero()[0]:
            d = float(separation_deg(scene.star_alt[i], scene.star_az[i], alt, az))
            if d > 4 * POINTING_SIGMA:
                continue
            mag = float(cat.mag[i])
            w = _prior(mag) * math.exp(-0.5 * (d / POINTING_SIGMA) ** 2)
            label = cat.cs_star_names.get(int(i))
            if label is None:
                con = cat.star_constellation(int(i))
                label = f"hvězda v souhvězdí {cat.constellation_cs(con)}" if con else "slabá hvězda"
            raw.append((w, ObjectRef.star(int(i)), label, "hvězda", d, mag, True))
        for b in scene.bodies.values():
            if b.alt <= 0 or b.id == "sun" or b.mag > lim + 1:
                continue
            d = float(separation_deg(b.alt, b.az, alt, az))
            if d > 4 * POINTING_SIGMA:
                continue
            w = _prior(b.mag) * math.exp(-0.5 * (d / POINTING_SIGMA) ** 2)
            kind = "Měsíc" if b.id == "moon" else "planeta"
            raw.append((w, ObjectRef.body(b.id), b.name, kind, d, b.mag, False))
    total = sum(r[0] for r in raw)
    raw.sort(key=lambda r: -r[0])
    cands = []
    for w, ref, name, kind, d, mag, tw in raw[:limit]:
        cands.append(
            Candidate(
                ref,
                name,
                kind,
                w / total if total else 0.0,
                d,
                mag,
                tw,
                _explain(scene, ref, name, kind, d, mag, alt),
            )
        )
    alternatives = _alternatives(cands, moving)
    return Identification(tuple(cands), alternatives)


def _explain(
    scene: SkyScene,
    ref: ObjectRef,
    name: str,
    kind: str,
    dist: float,
    mag: float,
    pointed_alt: float,
) -> str:
    pos = scene.altaz_of(ref)
    assert pos is not None
    alt, az = pos
    where = f"{height_word(alt)} {direction_word(az)}, {fist_text(alt)} nad obzorem"
    if kind == "družice":
        return (
            f"{name} právě přelétá {direction_word(az)}. Družice se pohybuje stálou "
            "rychlostí a nebliká; letadlo má blikající barevná světla."
        )
    if kind == "Měsíc":
        return f"To je Měsíc, {where}."
    bv = (
        PLANET_BV.get(ref.key)
        if ref.kind == "body"
        else (float(scene.cat.bv[int(ref.key)]) if ref.kind == "star" else None)
    )
    close = "přesně tam" if dist < 3 else f"{dist:.0f}° vedle místa"
    if kind == "planeta":
        col_n = color_word(bv, gender="n")
        return (
            f"Je to to {col_n} světlo {where}. Je {close}, kam ukazuješ, a je to nejjasnější "
            "bod v okolí. Nebliká (hvězdy blikají), protože je to planeta."
        )
    bright = "jasná" if mag < 1.5 else "slabší"
    col_f = color_word(bv, gender="f")
    return f"{bright.capitalize()} {col_f} hvězda {where} ({close}). Bliká jako všechny hvězdy."


def _alternatives(cands: list[Candidate], moving: bool) -> tuple[str, ...]:
    if moving:
        return (
            "Pokud světlo bliká červeně a zeleně, je to letadlo.",
            "Stálé světlo, které za pár minut přeletí celou oblohu, je družice (třeba ISS).",
        )
    if len(cands) < 2:
        return ()
    best = cands[0]
    out = []
    # only offer alternatives that are not hopelessly unlikely
    likely = [c for c in cands[1:] if c.probability >= ALTERNATIVE_MIN]
    other_star = next((c for c in likely if c.twinkles), None)
    other_planet = next((c for c in likely if not c.twinkles and c.kind == "planeta"), None)
    if not best.twinkles and other_star:
        out.append(f"Pokud to bliká, je to spíš {other_star.name}.")
    if best.twinkles and other_planet:
        out.append(f"Pokud to nebliká, je to spíš planeta {other_planet.name}.")
    if best.twinkles and not other_planet and likely:
        out.append(f"Pokud je to slabší světlo, může to být {likely[0].name}.")
    return tuple(out)


_DIR_WORDS = {
    "severovychod": 45,
    "jihovychod": 135,
    "jihozapad": 225,
    "severozapad": 315,
    "sever": 0,
    "vychod": 90,
    "jih": 180,
    "zapad": 270,
    "sv": 45,
    "jv": 135,
    "jz": 225,
    "sz": 315,
    "s": 0,
    "v": 90,
    "j": 180,
    "z": 270,
}
_HEIGHT_WORDS = {
    "tesne": 4,
    "u obzoru": 4,
    "nizko": 12,
    "napul": 40,
    "vysoko": 65,
    "nad hlavou": 85,
    "zenit": 90,
}


def parse_direction(text: str) -> tuple[float, float]:
    """Parse ``jihovýchod, 2 pěsti`` / ``JZ 30°`` / ``západ nízko`` into (alt, az)."""
    t = fold(text).replace(",", " ")
    az: float | None = None
    for word in sorted(_DIR_WORDS, key=len, reverse=True):
        if re.search(rf"\b{word}\w*", t) if len(word) > 2 else re.search(rf"\b{word}\b", t):
            az = float(_DIR_WORDS[word])
            break
    if az is None:
        raise ValueError("Nerozumím směru. Napiš třeba „jihovýchod, 2 pěsti“.")
    alt: float | None = None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:°|stup)", t)
    if m:
        alt = float(m[1].replace(",", "."))
    m = m or re.search(r"(\d+(?:[.,]\d+)?)\s*pest", t)
    if alt is None and m:
        alt = float(m[1].replace(",", ".")) * 10.0
    if alt is None:
        for word, value in _HEIGHT_WORDS.items():
            if word in t:
                alt = float(value)
                break
    if alt is None:
        alt = 20.0
    return min(90.0, max(0.0, alt)), az
