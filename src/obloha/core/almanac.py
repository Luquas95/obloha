"""Rise/set times, twilight, Moon phase info and the "tonight" overview."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from skyfield import almanac
from skyfield.api import Star
from skyfield.searchlib import find_discrete

from obloha.core.bodies import (
    BODY_BY_ID,
    PLANETS,
    BodyInfo,
    body_target,
    compute_body,
    moon_phase_angle,
    phase_name,
)
from obloha.core.ephem import ephemeris, timescale, to_datetime, ts_from_datetime
from obloha.core.location import Location

TWILIGHT_NAMES = {
    0: "astronomická noc",
    1: "astronomický soumrak",
    2: "nautický soumrak",
    3: "občanský soumrak",
    4: "den",
}


def sky_phase(sun_alt: float) -> str:
    """Czech name of the sky state for a given Sun altitude."""
    if sun_alt >= -0.833:
        return "den"
    if sun_alt >= -6:
        return "občanský soumrak"
    if sun_alt >= -12:
        return "nautický soumrak"
    if sun_alt >= -18:
        return "astronomický soumrak"
    return "astronomická noc"


def _dt(t: Any) -> datetime:
    return to_datetime(t)


@dataclass(frozen=True)
class RiseSet:
    """Next rise, transit and set of an object after a reference time."""

    rise: datetime | None
    transit: datetime | None
    transit_alt: float | None
    set: datetime | None
    always_up: bool = False
    never_up: bool = False


def _first(times: Any, flags: Any) -> datetime | None:
    for t, ok in zip(times, flags, strict=False):
        if ok:
            return _dt(t)
    return None


def target_for(obj: BodyInfo | tuple[float, float]) -> Any:
    """Skyfield target from a body or an (RA°, Dec°) pair."""
    if isinstance(obj, BodyInfo):
        return body_target(obj)
    ra, dec = obj
    return Star(ra_hours=ra / 15.0, dec_degrees=dec)


def rise_transit_set(
    obj: BodyInfo | tuple[float, float],
    start: datetime,
    location: Location,
    hours: float = 24.0,
) -> RiseSet:
    """Find the next rise, upper transit and set within ``hours`` after ``start``."""
    ts = timescale()
    t0 = ts_from_datetime(start)
    t1 = ts.tt_jd(t0.tt + hours / 24.0)
    target = target_for(obj)
    obs = location.observer
    rt, ry = almanac.find_risings(obs, target, t0, t1)
    st, sy = almanac.find_settings(obs, target, t0, t1)
    tt = almanac.find_transits(obs, target, t0, t1)
    rise = _first(rt, ry)
    sett = _first(st, sy)
    transit = _dt(tt[0]) if len(tt) else None
    transit_alt = None
    if len(tt):
        alt, _, _ = obs.at(tt[0]).observe(target).apparent().altaz("standard")
        transit_alt = float(alt.degrees)
    always = never = False
    if rise is None and sett is None:
        alt0, _, _ = obs.at(t0).observe(target).apparent().altaz("standard")
        always = bool(alt0.degrees > 0)
        never = not always
    return RiseSet(rise, transit, transit_alt, sett, always, never)


def local_noon(day: datetime, location: Location) -> datetime:
    """Local noon of the civil date of ``day`` (in the location's zone), as UTC."""
    local = day.astimezone(location.zone)
    noon = datetime(local.year, local.month, local.day, 12, tzinfo=location.zone)
    return noon.astimezone(UTC)


def night_start(when: datetime, location: Location) -> datetime:
    """Noon that starts the night containing ``when`` (before 12:00 → previous day)."""
    local = when.astimezone(location.zone)
    if local.hour < 12:
        local -= timedelta(days=1)
    return local_noon(local, location)


@dataclass
class TwilightTimes:
    """Sun events of one night (noon to noon), all UTC."""

    sunset: datetime | None = None
    civil_end: datetime | None = None
    nautical_end: datetime | None = None
    astro_end: datetime | None = None
    astro_start: datetime | None = None
    nautical_start: datetime | None = None
    civil_start: datetime | None = None
    sunrise: datetime | None = None
    transitions: list[tuple[datetime, int]] = field(default_factory=list)

    @property
    def astro_night(self) -> timedelta:
        """Length of the astronomical night (0 when there is none)."""
        total = timedelta()
        prev: datetime | None = None
        for when, state in self.transitions:
            if state == 0:
                prev = when
            elif prev is not None:
                total += when - prev
                prev = None
        return total


def twilight(start_noon: datetime, location: Location) -> TwilightTimes:
    """Sunset, twilight ends/starts and sunrise for the night after ``start_noon``."""
    ts = timescale()
    t0 = ts_from_datetime(start_noon)
    t1 = ts.tt_jd(t0.tt + 1.0)
    f = almanac.dark_twilight_day(ephemeris(), location.topos)
    times, states = find_discrete(t0, t1, f)
    out = TwilightTimes()
    prev = int(f(t0))
    if prev == 0:
        out.transitions.append((_dt(t0), 0))
    for t, s in zip(times, states, strict=False):
        s = int(s)
        when = _dt(t)
        out.transitions.append((when, s))
        if s < prev:  # getting darker
            if s == 2 and out.civil_end is None:
                out.civil_end = when
            if s == 1 and out.nautical_end is None:
                out.nautical_end = when
            if s == 0 and out.astro_end is None:
                out.astro_end = when
        else:
            if s == 1 and prev == 0:
                out.astro_start = when
            if s == 2 and prev == 1:
                out.nautical_start = when
            if s == 3 and prev == 2:
                out.civil_start = when
        prev = s
    if out.transitions and out.transitions[-1][1] == 0:
        out.transitions.append((_dt(t1), 1))
    sun = BODY_BY_ID["sun"]
    st, sy = almanac.find_settings(location.observer, body_target(sun), t0, t1)
    rt, ry = almanac.find_risings(location.observer, body_target(sun), t0, t1)
    out.sunset = _first(st, sy)
    out.sunrise = _first(rt, ry)
    return out


@dataclass(frozen=True)
class MoonInfo:
    phase_angle: float
    illumination: float
    phase_name: str
    age_days: float
    waxing: bool
    next_new: datetime
    next_full: datetime
    next_first_quarter: datetime
    next_last_quarter: datetime


def moon_info(when: datetime) -> MoonInfo:
    """Phase, illumination, age and the next principal phases."""
    ts = timescale()
    t = ts_from_datetime(when)
    angle = moon_phase_angle(t)
    illum = (1 - math.cos(math.radians(angle))) / 2
    t_back = ts.tt_jd(t.tt - 31.0)
    t_fwd = ts.tt_jd(t.tt + 31.0)
    times, phases = find_discrete(t_back, t_fwd, almanac.moon_phases(ephemeris()))
    last_new = None
    nxt: dict[int, datetime] = {}
    for tt, ph in zip(times, phases, strict=False):
        d = _dt(tt)
        if tt.tt <= t.tt and int(ph) == 0:
            last_new = tt.tt
        if tt.tt > t.tt and int(ph) not in nxt:
            nxt[int(ph)] = d
    age = t.tt - last_new if last_new is not None else angle / 360 * 29.53
    return MoonInfo(
        phase_angle=angle,
        illumination=illum,
        phase_name=phase_name(angle),
        age_days=float(age),
        waxing=angle < 180.0,
        next_new=nxt[0],
        next_full=nxt[2],
        next_first_quarter=nxt[1],
        next_last_quarter=nxt[3],
    )


@dataclass(frozen=True)
class PlanetNight:
    """Visibility of a planet during one night."""

    info: BodyInfo
    mag: float
    constellation: str
    up_from: datetime | None
    up_to: datetime | None
    best_time: datetime | None
    best_alt: float
    visible_minutes: int
    score: float
    rises: datetime | None
    sets: datetime | None

    @property
    def observable(self) -> bool:
        return self.visible_minutes > 0


def _sample_times(start: datetime, end: datetime, step_min: int) -> list[datetime]:
    n = max(2, int((end - start).total_seconds() // (step_min * 60)) + 1)
    return [start + timedelta(minutes=step_min * i) for i in range(n)]


def altitude_series(info: BodyInfo, times: list[datetime], location: Location) -> np.ndarray:
    """Apparent altitude of a body at many times (vectorised)."""
    t = timescale().from_datetimes(times)
    alt, _, _ = location.observer.at(t).observe(body_target(info)).apparent().altaz("standard")
    return np.asarray(alt.degrees)


def sun_altitudes(times: list[datetime], location: Location) -> np.ndarray:
    return altitude_series(BODY_BY_ID["sun"], times, location)


def planets_tonight(
    start_noon: datetime, location: Location, step_min: int = 10, min_alt: float = 5.0
) -> list[PlanetNight]:
    """Planet visibility for the night, sorted best first."""
    times = _sample_times(start_noon, start_noon + timedelta(days=1), step_min)
    sun_alt = sun_altitudes(times, location)
    dark = sun_alt < -6.0
    result: list[PlanetNight] = []
    mid = ts_from_datetime(start_noon + timedelta(hours=12))
    for info in PLANETS:
        alt = altitude_series(info, times, location)
        up = alt > 0
        vis = dark & (alt > min_alt)
        state = compute_body(info, mid, location)
        best_alt = (
            float(alt[vis].max()) if vis.any() else float(alt[dark].max()) if dark.any() else 0
        )
        best_idx = int(np.argmax(np.where(vis, alt, -99))) if vis.any() else None
        up_idx = np.flatnonzero(up & dark)
        rises = sets = None
        for i in range(1, len(times)):
            if up[i] and not up[i - 1] and rises is None:
                rises = times[i]
            if not up[i] and up[i - 1] and sets is None:
                sets = times[i]
        minutes = int(vis.sum()) * step_min
        brightness = max(0.0, 6.0 - state.mag) / 6.0 + 0.3
        score = minutes / 60.0 * brightness * (0.3 + best_alt / 90.0) if minutes else 0.0
        result.append(
            PlanetNight(
                info=info,
                mag=state.mag,
                constellation=state.constellation,
                up_from=times[up_idx[0]] if len(up_idx) else None,
                up_to=times[up_idx[-1]] if len(up_idx) else None,
                best_time=times[best_idx] if best_idx is not None else None,
                best_alt=best_alt,
                visible_minutes=minutes,
                score=score,
                rises=rises,
                sets=sets,
            )
        )
    result.sort(key=lambda p: -p.score)
    return result


def stars_altitude_at(ra: float, dec: float, when: datetime, location: Location) -> float:
    """Apparent altitude of a fixed RA/Dec at ``when``."""
    t = ts_from_datetime(when)
    alt, _, _ = location.observer.at(t).observe(target_for((ra, dec))).apparent().altaz("standard")
    return float(alt.degrees)
