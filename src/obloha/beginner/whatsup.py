""" "Co teď uvidíš": the 3–5 easiest interesting things in the sky right now."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from obloha.beginner.describe import (
    brightness_word,
    color_word,
    position_sentence,
)
from obloha.beginner.facts import BODY_FACTS, STAR_FACTS
from obloha.core.coords import separation_deg
from obloha.core.objects import PLANET_BV, is_feminine, object_info
from obloha.core.sky import ObjectRef, SkyScene, limiting_magnitude_for_sun


@dataclass(frozen=True)
class Suggestion:
    """One entry of the "what you can see" panel."""

    ref: ObjectRef
    title: str
    kind: str  # Czech word: planeta, hvězda, obrazec, Měsíc, …
    symbol: str
    sentences: tuple[str, ...]
    ease: float
    alt: float
    az: float

    @property
    def text(self) -> str:
        return " ".join(self.sentences)


def _altitude_bonus(alt: float) -> float:
    if alt < 8:
        return -30.0
    if alt < 15:
        return -12.0
    if alt > 78:
        return -8.0  # neck-breaking
    return 0.0


def _brightest_nearby(scene: SkyScene, alt: float, az: float, mag: float) -> bool:
    """True if no brighter star or planet is within 35°."""
    cat = scene.cat
    up = (scene.star_alt > 0) & (cat.mag < mag)
    if up.any():
        d = separation_deg(scene.star_alt[up], scene.star_az[up], alt, az)
        if np.any(d < 35):
            return False
    for b in scene.bodies.values():
        near = float(separation_deg(b.alt, b.az, alt, az)) < 35 and (b.alt, b.az) != (alt, az)
        if b.alt > 0 and b.mag < mag and b.id != "sun" and near:
            return False
    return True


def suggestions(scene: SkyScene, limit: int = 5, user_limit: float = 3.5) -> list[Suggestion]:
    """Deterministic list of easy targets, best first."""
    lim = limiting_magnitude_for_sun(scene.sun_alt, user_limit)
    out: list[Suggestion] = []
    cat = scene.cat
    # Moon
    moon = scene.bodies["moon"]
    if moon.alt > 2:
        illum = round(moon.illumination * 100)
        out.append(
            Suggestion(
                ObjectRef.body("moon"),
                "Měsíc",
                "Měsíc",
                "☽",
                (
                    position_sentence(moon.alt, moon.az),
                    f"Osvětlený z {illum} %. " + BODY_FACTS["moon"],
                ),
                100.0 + _altitude_bonus(moon.alt),
                moon.alt,
                moon.az,
            )
        )
    # planets
    for b in scene.bodies.values():
        if b.info.kind != "planet" or b.alt < 3 or b.mag > min(lim, 2.5):
            continue
        if b.elongation < 10:
            continue
        sent = [position_sentence(b.alt, b.az)]
        fem = b.id == "venus"
        col = color_word(PLANET_BV.get(b.id), feminine=fem)
        if _brightest_nearby(scene, b.alt, b.az, b.mag):
            sent.append(f"Nejjasnější bod v té části oblohy, {col}, nebliká.")
        else:
            sent.append(f"{brightness_word(b.mag, fem).capitalize()} {col} bod, nebliká.")
        sent.append(BODY_FACTS[b.id])
        ease = 80.0 - 6.0 * b.mag + _altitude_bonus(b.alt)
        out.append(
            Suggestion(
                ObjectRef.body(b.id),
                b.name,
                "planeta",
                b.info.symbol,
                tuple(sent),
                ease,
                b.alt,
                b.az,
            )
        )
    # bright named stars
    for i in cat.named_stars[:40]:
        mag = float(cat.mag[i])
        alt = float(scene.star_alt[i])
        if mag > min(1.3, lim) or alt < 10 or i not in cat.cs_star_names:
            continue
        ref = ObjectRef.star(i)
        info = object_info(scene, ref)
        assert info is not None
        fem = is_feminine(info)
        sent = [position_sentence(alt, float(scene.star_az[i]))]
        sent.append(
            f"{brightness_word(mag, True).capitalize()}, {color_word(info.bv, True)}, bliká."
        )
        fact = STAR_FACTS.get(info.name)
        if fact:
            sent.append(fact)
        del fem
        ease = 52.0 - 10.0 * mag + _altitude_bonus(alt)
        out.append(
            Suggestion(
                ref, info.name, "hvězda", "✦", tuple(sent), ease, alt, float(scene.star_az[i])
            )
        )
    # asterisms (only when it's dark enough to see them)
    if lim >= 2.0:
        for a in cat.asterisms:
            alts = scene.star_alt[list(a.stars)]
            if alts.min() < 10:
                continue
            ref = ObjectRef("asterism", a.id)
            pos = scene.altaz_of(ref)
            assert pos is not None
            names = ", ".join(cat.star_label(s) for s in a.stars[:3])
            second = f"Hvězdy {names}." if len(a.stars) <= 3 else position_sentence(*pos)
            asterism_sent = (a.text, second)
            ease = 58.0 + _altitude_bonus(float(alts.mean())) - 2.0 * len(a.stars)
            out.append(Suggestion(ref, a.name, "obrazec", "◌", asterism_sent, ease, pos[0], pos[1]))
    # Pleiades in dark sky
    if lim >= 3.0:
        for d in cat.deep_sky:
            if d.id != "M45":
                continue
            alt, az = scene.radec_altaz(d.ra, d.dec)
            if alt > 15:
                out.append(
                    Suggestion(
                        ObjectRef("dso", d.id),
                        d.name,
                        d.kind,
                        "⁘",
                        (position_sentence(alt, az), d.text),
                        40.0 + _altitude_bonus(alt),
                        alt,
                        az,
                    )
                )
    # visible satellites right now
    for s in scene.satellites:
        if s.sunlit and s.alt > 10 and scene.sun_alt < -6:
            out.append(
                Suggestion(
                    ObjectRef("sat", s.name),
                    s.name,
                    "družice",
                    "▲",
                    (
                        position_sentence(s.alt, s.az),
                        "Právě letí! Pohybující se světlo, které nebliká.",
                    ),
                    150.0,
                    s.alt,
                    s.az,
                )
            )
    out.sort(key=lambda sug: (-sug.ease, sug.title))
    # keep variety: at most two plain stars
    result: list[Suggestion] = []
    stars = 0
    for sug in out:
        if sug.kind == "hvězda":
            if stars >= 2:
                continue
            stars += 1
        result.append(sug)
        if len(result) >= limit:
            break
    return result
