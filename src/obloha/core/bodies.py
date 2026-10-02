"""Positions and physical data of the Sun, the Moon and the planets."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from skyfield.magnitudelib import planetary_magnitude

from obloha.core.ephem import constellation_map, ephemeris, ts_from_datetime
from obloha.core.location import Location


@dataclass(frozen=True)
class BodyInfo:
    """Static description of a Solar System body."""

    id: str
    key: str
    name: str
    symbol: str
    ascii: str
    color: str
    kind: str  # "star" (Sun), "moon", "planet"
    radius_km: float
    feminine: bool = False

    @property
    def color_int(self) -> int:
        return int(self.color.lstrip("#"), 16)


BODIES: tuple[BodyInfo, ...] = (
    BodyInfo("sun", "sun", "Slunce", "☉", "O", "#ffe27a", "sun", 696_000.0),
    BodyInfo("moon", "moon", "Měsíc", "☽", "C", "#f4f1e0", "moon", 1737.4),
    BodyInfo("mercury", "mercury", "Merkur", "☿", "Me", "#c9b8a6", "planet", 2439.7),
    BodyInfo("venus", "venus", "Venuše", "♀", "Ve", "#fff4d0", "planet", 6051.8, feminine=True),
    BodyInfo("mars", "mars", "Mars", "♂", "Ma", "#ff8a5c", "planet", 3389.5),
    BodyInfo("jupiter", "jupiter barycenter", "Jupiter", "♃", "Ju", "#ffe2b0", "planet", 69911.0),
    BodyInfo("saturn", "saturn barycenter", "Saturn", "♄", "Sa", "#f0d58a", "planet", 58232.0),
    BodyInfo("uranus", "uranus barycenter", "Uran", "♅", "Ur", "#a8e6e8", "planet", 25362.0),
    BodyInfo("neptune", "neptune barycenter", "Neptun", "♆", "Ne", "#8fb0ff", "planet", 24622.0),
)
BODY_BY_ID: dict[str, BodyInfo] = {b.id: b for b in BODIES}
PLANETS: tuple[BodyInfo, ...] = tuple(b for b in BODIES if b.kind == "planet")
AU_KM = 149_597_870.7

#: Fallback absolute magnitudes H (for when Mallama's formula returns NaN).
_FALLBACK_H = {"saturn": -8.9, "neptune": -7.0, "mercury": -0.6, "uranus": -7.1}


@dataclass(frozen=True)
class BodyState:
    """Apparent topocentric state of a body at one instant."""

    info: BodyInfo
    alt: float
    az: float
    ra: float  # degrees, astrometric ICRS (for the map)
    dec: float
    ra_date: float  # degrees, apparent equinox of date (for display)
    dec_date: float
    distance_au: float
    mag: float
    illumination: float  # 0..1
    elongation: float  # degrees from the Sun
    angular_radius: float  # degrees
    constellation: str  # IAU abbreviation

    @property
    def id(self) -> str:
        return self.info.id

    @property
    def name(self) -> str:
        return self.info.name


def body_target(info: BodyInfo) -> Any:
    return ephemeris()[info.key]


def moon_magnitude(phase_angle_deg: float, distance_km: float) -> float:
    """Approximate visual magnitude of the Moon (Allen; full moon ≈ −12.7)."""
    pa = abs(phase_angle_deg)
    mag = -12.73 + 0.026 * pa + 4e-9 * pa**4
    return mag + 5.0 * math.log10(distance_km / 384_400.0)


def _phase_angle(observer_pos: Any, target_pos: Any, sun_pos: Any) -> float:
    """Angle Sun-target-observer in degrees (vectors in AU, barycentric)."""
    to_obs = np.asarray(observer_pos) - np.asarray(target_pos)
    to_sun = np.asarray(sun_pos) - np.asarray(target_pos)
    c = np.dot(to_obs, to_sun) / (np.linalg.norm(to_obs) * np.linalg.norm(to_sun))
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


def compute_body(info: BodyInfo, t: Any, location: Location) -> BodyState:
    """Compute the apparent state of one body at Skyfield time ``t``."""
    eph = ephemeris()
    obs = location.observer.at(t)
    astrometric = obs.observe(body_target(info))
    apparent = astrometric.apparent()
    alt, az, dist = apparent.altaz("standard")
    ra, dec, _ = astrometric.radec()
    ra_d, dec_d, _ = apparent.radec("date")
    sun_bary = eph["sun"].at(t).position.au
    obs_bary = obs.position.au
    tgt_bary = obs_bary + astrometric.position.au
    elong = 0.0
    if info.id == "sun":
        illum = 1.0
        mag = -26.74
        phase = 0.0
    else:
        phase = _phase_angle(obs_bary, tgt_bary, sun_bary)
        illum = (1.0 + math.cos(math.radians(phase))) / 2.0
        sun_dir = sun_bary - obs_bary
        tgt_dir = astrometric.position.au
        c = np.dot(sun_dir, tgt_dir) / (np.linalg.norm(sun_dir) * np.linalg.norm(tgt_dir))
        elong = float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))
        if info.id == "moon":
            mag = moon_magnitude(phase, dist.km)
        else:
            try:
                mag = float(planetary_magnitude(astrometric))
            except ValueError:  # pragma: no cover - all planets are supported
                mag = float("nan")
            if math.isnan(mag):
                r = float(np.linalg.norm(tgt_bary - sun_bary))
                mag = _FALLBACK_H.get(info.id, 0.0) + 5 * math.log10(r * dist.au)
    return BodyState(
        info=info,
        alt=float(alt.degrees),
        az=float(az.degrees),
        ra=float(ra._degrees),
        dec=float(dec.degrees),
        ra_date=float(ra_d._degrees),
        dec_date=float(dec_d.degrees),
        distance_au=float(dist.au),
        mag=float(mag),
        illumination=illum,
        elongation=elong,
        angular_radius=math.degrees(math.asin(min(1.0, info.radius_km / dist.km))),
        constellation=str(constellation_map()(astrometric)),
    )


def compute_bodies(when: datetime, location: Location) -> dict[str, BodyState]:
    """Compute all bodies for ``when``."""
    t = ts_from_datetime(when)
    return {b.id: compute_body(b, t, location) for b in BODIES}


def moon_phase_angle(t: Any) -> float:
    """Ecliptic longitude difference Moon − Sun in degrees (0 new, 180 full)."""
    from skyfield import almanac

    return float(almanac.moon_phase(ephemeris(), t).degrees)


PHASE_NAMES = (
    (0.0, "nov"),
    (22.5, "dorůstající srpek"),
    (67.5, "první čtvrť"),
    (112.5, "dorůstající Měsíc"),
    (157.5, "úplněk"),
    (202.5, "ubývající Měsíc"),
    (247.5, "poslední čtvrť"),
    (292.5, "ubývající srpek"),
    (337.5, "nov"),
)


def phase_name(angle_deg: float) -> str:
    """Czech name of the Moon phase for a Sun-Moon longitude difference."""
    a = angle_deg % 360.0
    name = PHASE_NAMES[0][1]
    for start, label in PHASE_NAMES:
        if a >= start:
            name = label
    return name


def moon_symbol(angle_deg: float, ascii_only: bool = False) -> str:
    """Symbol for the Moon by phase: ● new, ◐ waxing, ○ full, ◑ waning.

    Shapes follow the northern hemisphere view (waxing Moon lit on the right).
    """
    a = angle_deg % 360.0
    if a < 22.5 or a >= 337.5:
        return "o" if ascii_only else "●"
    if a < 157.5:
        return "D" if ascii_only else "◐"
    if a < 202.5:
        return "O" if ascii_only else "○"
    return "C" if ascii_only else "◑"


def waxing(angle_deg: float) -> bool:
    return (angle_deg % 360.0) < 180.0
