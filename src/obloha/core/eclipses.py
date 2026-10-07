"""Solar and lunar eclipses, including local circumstances for an observer.

* Lunar eclipses: candidates and magnitudes from Skyfield's ``eclipselib``
  (Explanatory Supplement 11.2.3, Danjon shadow enlargement); contact times
  are found here by root-finding on the same shadow geometry.
* Solar eclipses: Skyfield has no solar eclipse search, so we search new
  Moons with small ecliptic latitude and compute *local* circumstances from
  the topocentric apparent positions of the Sun and the Moon (separation of
  the disc centres versus the sum of their apparent radii). The global type
  (total/annular/hybrid/partial) is derived from the shadow axis geometry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from skyfield import almanac
from skyfield.eclipselib import lunar_eclipses
from skyfield.searchlib import find_discrete

from obloha.core.ephem import ephemeris, timescale, to_datetime, ts_from_datetime
from obloha.core.location import Location

SUN_RADIUS_KM = 696_340.0
MOON_RADIUS_KM = 1737.1
EARTH_RADIUS_KM = 6378.137

LUNAR_TYPES = ("polostínové", "částečné", "úplné")


@dataclass(frozen=True)
class LunarEclipse:
    """A lunar eclipse with contacts (UTC) and visibility from a place."""

    maximum: datetime
    kind: int  # 0 penumbral, 1 partial, 2 total
    umbral_magnitude: float
    penumbral_magnitude: float
    penumbral_begin: datetime
    penumbral_end: datetime
    partial_begin: datetime | None
    partial_end: datetime | None
    total_begin: datetime | None
    total_end: datetime | None
    moon_alt_at_max: float
    visible: bool  # any part of the eclipse with Moon above the horizon

    @property
    def type_name(self) -> str:
        return LUNAR_TYPES[self.kind]


@dataclass(frozen=True)
class SolarEclipse:
    """A solar eclipse with global type and local circumstances."""

    global_maximum: datetime
    global_type: str  # "úplné", "prstencové", "hybridní", "částečné"
    local_type: str | None  # "částečné", "úplné", "prstencové" or None (not seen)
    begin: datetime | None
    maximum: datetime | None
    end: datetime | None
    magnitude: float  # fraction of the Sun's diameter covered at local maximum
    obscuration: float  # fraction of the Sun's area covered
    sun_alt_at_max: float

    @property
    def visible(self) -> bool:
        return self.local_type is not None


def _dt(t: Any) -> datetime:
    return to_datetime(t)


def _lunar_geometry(t: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (separation, moon radius, umbra radius, penumbra radius) in radians."""
    eph = ephemeris()
    e = eph["earth"].at(t)
    sun = e.observe(eph["sun"]).apparent().position.km
    moon = (eph["moon"] - eph["earth"]).at(t).position.km
    d_s = np.linalg.norm(sun, axis=0)
    d_m = np.linalg.norm(moon, axis=0)
    cosang = np.sum(-sun * moon, axis=0) / (d_s * d_m)
    sep = np.arccos(np.clip(cosang, -1, 1))
    pi_m = EARTH_RADIUS_KM / d_m
    pi_s = EARTH_RADIUS_KM / d_s
    s_s = SUN_RADIUS_KM / d_s
    pi_1 = 1.01 * pi_m
    return sep, np.arcsin(MOON_RADIUS_KM / d_m), pi_1 + pi_s - s_s, pi_1 + pi_s + s_s


def _contacts(t_max: Any, fn: Any, hours: float = 4.0) -> tuple[datetime | None, datetime | None]:
    """Find the sign changes of ``fn`` before and after ``t_max`` (fn < 0 inside)."""
    ts = timescale()
    n = int(hours * 60) + 1
    before = ts.tt_jd(t_max.tt - np.linspace(0, hours / 24.0, n))
    after = ts.tt_jd(t_max.tt + np.linspace(0, hours / 24.0, n))

    def root(times: Any) -> datetime | None:
        v = fn(times)
        if v[0] >= 0:
            return None
        idx = np.flatnonzero(v >= 0)
        if not len(idx):
            return None
        i = int(idx[0])
        a, b = times.tt[i - 1], times.tt[i]
        vb = v[i]
        for _ in range(30):
            m = (a + b) / 2
            vm = fn(ts.tt_jd(np.array([m])))[0]
            if (vm >= 0) == (vb >= 0):
                b, vb = m, vm
            else:
                a = m
        return _dt(ts.tt_jd((a + b) / 2))

    return root(before), root(after)


def find_lunar_eclipses(start: datetime, end: datetime, location: Location) -> list[LunarEclipse]:
    """All lunar eclipses between ``start`` and ``end``."""
    ts = timescale()
    t0, t1 = ts_from_datetime(start), ts_from_datetime(end)
    times, codes, details = lunar_eclipses(t0, t1, ephemeris())
    out: list[LunarEclipse] = []
    for i, t in enumerate(times):

        def pen(tt: Any) -> np.ndarray:
            sep, mr, _, pr = _lunar_geometry(tt)
            return np.asarray(sep - (pr + mr))

        def par(tt: Any) -> np.ndarray:
            sep, mr, ur, _ = _lunar_geometry(tt)
            return np.asarray(sep - (ur + mr))

        def tot(tt: Any) -> np.ndarray:
            sep, mr, ur, _ = _lunar_geometry(tt)
            return np.asarray(sep - (ur - mr))

        tt = ts.tt_jd(np.array([t.tt]))
        p0, p1 = _contacts(tt[0], pen, 5.0)
        u0, u1 = _contacts(tt[0], par) if codes[i] >= 1 else (None, None)
        c0, c1 = _contacts(tt[0], tot, 2.0) if codes[i] == 2 else (None, None)
        b = p0 or _dt(t)
        e = p1 or _dt(t)
        sample = [b + (e - b) * k / 40 for k in range(41)]
        alts = (
            location.observer.at(ts.from_datetimes(sample))
            .observe(ephemeris()["moon"])
            .apparent()
            .altaz("standard")[0]
            .degrees
        )
        alt_max = float(
            location.observer.at(t)
            .observe(ephemeris()["moon"])
            .apparent()
            .altaz("standard")[0]
            .degrees
        )
        out.append(
            LunarEclipse(
                maximum=_dt(t),
                kind=int(codes[i]),
                umbral_magnitude=float(details["umbral_magnitude"][i]),
                penumbral_magnitude=float(details["penumbral_magnitude"][i]),
                penumbral_begin=b,
                penumbral_end=e,
                partial_begin=u0,
                partial_end=u1,
                total_begin=c0,
                total_end=c1,
                moon_alt_at_max=alt_max,
                visible=bool(np.any(alts > 0)),
            )
        )
    return out


def _local_solar(t: Any, location: Location) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Topocentric (separation, sun radius, moon radius) in degrees, plus sun alt."""
    eph = ephemeris()
    obs = location.observer.at(t)
    s = obs.observe(eph["sun"]).apparent()
    m = obs.observe(eph["moon"]).apparent()
    sep = s.separation_from(m).degrees
    rs = np.degrees(np.arcsin(SUN_RADIUS_KM / s.distance().km))
    rm = np.degrees(np.arcsin(MOON_RADIUS_KM / m.distance().km))
    return np.asarray(sep), np.asarray(rs), np.asarray(rm)


def _global_type(t: Any) -> tuple[str, bool]:
    """Global eclipse type from the geocentric shadow axis.

    Returns the type and whether any eclipse at all happens (penumbra touches
    the Earth).
    """
    eph = ephemeris()
    earth = eph["earth"].at(t)
    sun = earth.observe(eph["sun"]).position.km
    moon = earth.observe(eph["moon"]).position.km
    axis = moon - sun
    axis /= np.linalg.norm(axis)
    # closest approach of the shadow axis to the Earth's centre
    closest = moon - np.dot(moon, axis) * axis
    gamma_km = float(np.linalg.norm(closest))
    d_sm = float(np.linalg.norm(moon - sun))
    # penumbra / umbra cone half-angles
    f_pen = math.asin((SUN_RADIUS_KM + MOON_RADIUS_KM) / d_sm)
    f_umb = math.asin((SUN_RADIUS_KM - MOON_RADIUS_KM) / d_sm)
    dist_along = float(np.dot(-moon, axis))  # moon -> fundamental plane
    pen_radius = MOON_RADIUS_KM + dist_along * math.tan(f_pen)
    umb_radius = MOON_RADIUS_KM - dist_along * math.tan(f_umb)  # >0 total, <0 annular
    any_eclipse = gamma_km < EARTH_RADIUS_KM + pen_radius
    if gamma_km > EARTH_RADIUS_KM + abs(umb_radius):
        return "částečné", any_eclipse
    # Central eclipse: compare umbra at the surface near the axis point.
    depth = math.sqrt(max(EARTH_RADIUS_KM**2 - gamma_km**2, 0.0))
    umb_surface = umb_radius + depth * math.tan(f_umb)
    if umb_radius > 0:
        return "úplné", any_eclipse
    if umb_surface > 0:
        return "hybridní", any_eclipse
    return "prstencové", any_eclipse


def find_solar_eclipses(start: datetime, end: datetime, location: Location) -> list[SolarEclipse]:
    """All solar eclipses between ``start`` and ``end`` with local circumstances."""
    ts = timescale()
    eph = ephemeris()
    t0, t1 = ts_from_datetime(start), ts_from_datetime(end)
    times, phases = find_discrete(t0, t1, almanac.moon_phases(eph))
    out: list[SolarEclipse] = []
    for t, ph in zip(times, phases, strict=False):
        if int(ph) != 0:
            continue
        # quick filter: ecliptic latitude of the Moon at new Moon
        lat, _, _ = eph["earth"].at(t).observe(eph["moon"]).frame_latlon(_ecliptic_frame())
        if abs(lat.degrees) > 1.6:
            continue
        # refine the global maximum: minimum geocentric Sun-Moon separation
        grid = ts.tt_jd(t.tt + np.linspace(-0.3, 0.3, 721))
        e = eph["earth"].at(grid)
        gsep = e.observe(eph["sun"]).separation_from(e.observe(eph["moon"])).degrees
        tg = grid[int(np.argmin(gsep))]
        gtype, any_ecl = _global_type(tg)
        if not any_ecl:
            continue
        # local circumstances (±4 h around global maximum, 30 s steps)
        local_grid = ts.tt_jd(tg.tt + np.linspace(-4 / 24, 4 / 24, 961))
        sep, rs, rm = _local_solar(local_grid, location)
        overlap = rs + rm - sep
        if not np.any(overlap > 0):
            out.append(SolarEclipse(_dt(tg), gtype, None, None, None, None, 0.0, 0.0, 0.0))
            continue
        sun_alt = (
            location.observer.at(local_grid)
            .observe(eph["sun"])
            .apparent()
            .altaz("standard")[0]
            .degrees
        )
        visible = (overlap > 0) & (sun_alt > -0.27)
        if not np.any(visible):
            out.append(SolarEclipse(_dt(tg), gtype, None, None, None, None, 0.0, 0.0, 0.0))
            continue
        idx = np.flatnonzero(visible)
        # maximum among visible samples, refined with a parabola
        k = int(idx[np.argmax(overlap[idx] / (2 * rs[idx]))])
        tmax = local_grid[k]
        if 0 < k < len(local_grid) - 1 and visible[k - 1] and visible[k + 1]:
            y0, y1, y2 = sep[k - 1], sep[k], sep[k + 1]
            denom = y0 - 2 * y1 + y2
            if denom > 0:
                frac = 0.5 * (y0 - y2) / denom
                tmax = ts.tt_jd(local_grid.tt[k] + frac * (local_grid.tt[1] - local_grid.tt[0]))
        s1, r_s, r_m = (float(x) for x in _local_solar(tmax, location))
        mag = (r_s + r_m - s1) / (2 * r_s)
        if s1 <= abs(r_m - r_s):
            local_type = "úplné" if r_m >= r_s else "prstencové"
        else:
            local_type = "částečné"
        all_contact = np.flatnonzero(overlap > 0)
        begin = _refine_contact(local_grid, overlap, int(all_contact[0]), location, rising=True)
        end_t = _refine_contact(local_grid, overlap, int(all_contact[-1]), location, rising=False)
        out.append(
            SolarEclipse(
                global_maximum=_dt(tg),
                global_type=gtype,
                local_type=local_type,
                begin=begin,
                maximum=_dt(tmax),
                end=end_t,
                magnitude=float(mag),
                obscuration=_obscuration(r_s, r_m, s1),
                sun_alt_at_max=float(
                    location.observer.at(tmax)
                    .observe(eph["sun"])
                    .apparent()
                    .altaz("standard")[0]
                    .degrees
                ),
            )
        )
    return out


def _refine_contact(
    grid: Any, overlap: np.ndarray, i: int, location: Location, rising: bool
) -> datetime:
    ts = timescale()
    j = i - 1 if rising else i + 1
    if j < 0 or j >= len(grid):
        return _dt(grid[i])
    a, b = grid.tt[j], grid.tt[i]
    for _ in range(25):
        m = (a + b) / 2
        sep, rs, rm = _local_solar(ts.tt_jd(m), location)
        if float(rs + rm - sep) > 0:
            b = m
        else:
            a = m
    return _dt(ts.tt_jd((a + b) / 2))


def _obscuration(rs: float, rm: float, d: float) -> float:
    """Fraction of the solar disc area covered by the lunar disc."""
    if d >= rs + rm:
        return 0.0
    if d <= abs(rm - rs):
        return 1.0 if rm >= rs else (rm * rm) / (rs * rs)
    a1 = rs * rs * math.acos((d * d + rs * rs - rm * rm) / (2 * d * rs))
    a2 = rm * rm * math.acos((d * d + rm * rm - rs * rs) / (2 * d * rm))
    a3 = 0.5 * math.sqrt((-d + rs + rm) * (d + rs - rm) * (d - rs + rm) * (d + rs + rm))
    return (a1 + a2 - a3) / (math.pi * rs * rs)


def _ecliptic_frame() -> Any:
    from skyfield.framelib import ecliptic_frame

    return ecliptic_frame


def eclipses_between(
    start: datetime, end: datetime, location: Location
) -> tuple[list[SolarEclipse], list[LunarEclipse]]:
    """Convenience wrapper returning both kinds."""
    return find_solar_eclipses(start, end, location), find_lunar_eclipses(start, end, location)


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


__all__ = [
    "LunarEclipse",
    "SolarEclipse",
    "eclipses_between",
    "find_lunar_eclipses",
    "find_solar_eclipses",
    "timedelta",
]
