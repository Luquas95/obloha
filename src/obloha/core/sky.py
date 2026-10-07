"""Sky scene: everything's horizontal coordinates for one instant and place."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property, lru_cache

import numpy as np
from numpy.typing import NDArray

from obloha.core.bodies import BODIES, BodyState, compute_body, moon_phase_angle
from obloha.core.catalog import Catalog, catalog
from obloha.core.coords import horizon_matrix, nev_to_altaz, radec_to_vec, refraction
from obloha.core.ephem import ts_from_datetime
from obloha.core.location import Location

FloatArray = NDArray[np.float64]

OBLIQUITY_J2000 = 23.4392911


@dataclass(frozen=True)
class ObjectRef:
    """Reference to anything selectable on the map."""

    kind: str  # "star", "body", "dso", "sat", "asterism", "constellation", "point"
    key: str

    @staticmethod
    def star(index: int) -> ObjectRef:
        return ObjectRef("star", str(index))

    @staticmethod
    def body(body_id: str) -> ObjectRef:
        return ObjectRef("body", body_id)


@dataclass(frozen=True)
class SatPosition:
    """Current position of a satellite (computed by ``satellites``)."""

    name: str
    alt: float
    az: float
    sunlit: bool
    range_km: float
    mag: float | None = None


@lru_cache(maxsize=1)
def ecliptic_vectors(n: int = 361) -> FloatArray:
    """ICRS unit vectors along the J2000 ecliptic."""
    lam = np.radians(np.linspace(0.0, 360.0, n))
    eps = np.radians(OBLIQUITY_J2000)
    return np.stack([np.cos(lam), np.sin(lam) * np.cos(eps), np.sin(lam) * np.sin(eps)], axis=-1)


@lru_cache(maxsize=1)
def equatorial_grid() -> list[FloatArray]:
    """Polylines (ICRS vectors) of an RA/Dec grid: RA every 2 h, Dec every 30°."""
    lines: list[FloatArray] = []
    dec = np.linspace(-89.0, 89.0, 179)
    for ra in range(0, 360, 30):
        lines.append(radec_to_vec(np.full_like(dec, float(ra)), dec))
    ra_s = np.linspace(0.0, 360.0, 361)
    for d in (-60.0, -30.0, 0.0, 30.0, 60.0):
        lines.append(radec_to_vec(ra_s, np.full_like(ra_s, d)))
    return lines


@dataclass
class SkyScene:
    """Horizontal coordinates of stars, bodies and helper lines at one instant."""

    when: datetime
    location: Location
    matrix: FloatArray
    star_alt: FloatArray
    star_az: FloatArray
    bodies: dict[str, BodyState]
    moon_phase: float
    satellites: list[SatPosition] = field(default_factory=list)
    cat: Catalog = field(default_factory=catalog)

    @property
    def sun_alt(self) -> float:
        return self.bodies["sun"].alt

    def transform(self, vectors: FloatArray, refract: bool = True) -> tuple[FloatArray, FloatArray]:
        """ICRS vectors -> apparent (alt, az)."""
        alt, az = nev_to_altaz(vectors @ self.matrix.T)
        if refract:
            alt = alt + refraction(alt)
        return alt, az

    @cached_property
    def mw(self) -> tuple[FloatArray, FloatArray]:
        return self.transform(self.cat.mw_vectors)

    @cached_property
    def borders(self) -> tuple[FloatArray, FloatArray]:
        return self.transform(self.cat.border_vectors)

    @cached_property
    def ecliptic(self) -> tuple[FloatArray, FloatArray]:
        return self.transform(ecliptic_vectors())

    @cached_property
    def eq_grid(self) -> list[tuple[FloatArray, FloatArray]]:
        return [self.transform(v, refract=False) for v in equatorial_grid()]

    def radec_altaz(self, ra: float, dec: float) -> tuple[float, float]:
        alt, az = self.transform(radec_to_vec(np.array([ra]), np.array([dec])))
        return float(alt[0]), float(az[0])

    def altaz_of(self, ref: ObjectRef) -> tuple[float, float] | None:
        """Horizontal position of any object reference."""
        if ref.kind == "star":
            i = int(ref.key)
            return float(self.star_alt[i]), float(self.star_az[i])
        if ref.kind == "body":
            b = self.bodies.get(ref.key)
            return (b.alt, b.az) if b else None
        if ref.kind == "dso":
            d = next((d for d in self.cat.deep_sky if d.id == ref.key), None)
            return self.radec_altaz(d.ra, d.dec) if d else None
        if ref.kind == "sat":
            s = next((s for s in self.satellites if s.name == ref.key), None)
            return (s.alt, s.az) if s else None
        if ref.kind == "constellation":
            c = self.cat.constellations[int(ref.key)]
            return self.radec_altaz(c.ra, c.dec)
        if ref.kind == "asterism":
            a = next((a for a in self.cat.asterisms if a.id == ref.key), None)
            if a is None:
                return None
            v = self.cat.vectors[list(a.stars)].mean(axis=0)
            alt, az = self.transform(v[None, :] / np.linalg.norm(v))
            return float(alt[0]), float(az[0])
        if ref.kind == "point":
            alt_s, az_s = ref.key.split(",")
            return float(alt_s), float(az_s)
        return None


def build_scene(
    when: datetime, location: Location, satellites: list[SatPosition] | None = None
) -> SkyScene:
    """Compute a :class:`SkyScene` for ``when`` at ``location``."""
    t = ts_from_datetime(when)
    cat = catalog()
    m = horizon_matrix(t, location.lat, location.lon)
    alt, az = nev_to_altaz(cat.vectors @ m.T)
    alt = alt + refraction(alt)
    bodies = {b.id: compute_body(b, t, location) for b in BODIES}
    return SkyScene(
        when=when,
        location=location,
        matrix=m,
        star_alt=alt,
        star_az=az,
        bodies=bodies,
        moon_phase=moon_phase_angle(t),
        satellites=list(satellites or []),
        cat=cat,
    )


def limiting_magnitude_for_sun(sun_alt: float, user_limit: float) -> float:
    """Faintest magnitude visible given the Sun altitude (twilight) and user limit."""
    pts = (
        (-18.0, user_limit),
        (-12.0, min(user_limit, 4.0)),
        (-6.0, 1.5),
        (-1.0, -1.0),
        (0.0, -4.0),
    )
    if sun_alt <= pts[0][0]:
        return user_limit
    if sun_alt >= pts[-1][0]:
        return -4.0
    for (a0, m0), (a1, m1) in itertools.pairwise(pts):
        if a0 <= sun_alt <= a1:
            f = (sun_alt - a0) / (a1 - a0)
            return min(user_limit, m0 + f * (m1 - m0))
    return user_limit  # pragma: no cover


def sky_quality_limit(quality: str) -> float:
    """Default limiting magnitude by observing site type."""
    return {"město": 3.5, "předměstí": 4.8, "venkov": 6.0}.get(quality, 3.5)
