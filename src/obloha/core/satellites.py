"""Satellites: TLE download and cache (CelesTrak), passes and visibility."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from skyfield.api import EarthSatellite

from obloha.core.ephem import ephemeris, timescale, to_datetime, ts_from_datetime
from obloha.core.location import Location
from obloha.core.sky import SatPosition

CELESTRAK = "https://celestrak.org/NORAD/elements/gp.php"
STALE_DAYS = 7

#: Standard magnitudes (1000 km range, 50 % illuminated), McCants/heavens-above style.
STD_MAG = {25544: -1.8, 48274: -0.8, 20580: 2.2}
NAMES_CS = {25544: "ISS", 48274: "Tiangong", 20580: "Hubble"}


@dataclass(frozen=True)
class FetchResult:
    """Outcome of a refresh attempt (``status`` is user-facing Czech)."""

    ok: bool
    status: str
    count: int = 0


def parse_tle(text: str) -> list[tuple[str, str, str]]:
    """Parse 3-line TLE text into (name, line1, line2) triples."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    out: list[tuple[str, str, str]] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            name = lines[i][2:7].strip()
            out.append((name, lines[i], lines[i + 1]))
            i += 2
        elif i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            out.append((lines[i].strip(), lines[i + 1], lines[i + 2]))
            i += 3
        else:
            i += 1
    return out


def tle_checksum_ok(line: str) -> bool:
    total = sum(int(c) if c.isdigit() else 1 if c == "-" else 0 for c in line[:68])
    return line[68:69].isdigit() and total % 10 == int(line[68])


class SatelliteStore:
    """Cached TLE sets in ``<cache>/tle``."""

    def __init__(self, cache: Path) -> None:
        self.dir = cache / "tle"
        self.meta_path = self.dir / "meta.json"

    def _meta(self) -> dict[str, Any]:
        try:
            data: dict[str, Any] = json.loads(self.meta_path.read_text(encoding="utf-8"))
            return data
        except (OSError, ValueError):
            return {}

    def fetched_at(self) -> datetime | None:
        value = self._meta().get("fetched_at")
        return datetime.fromisoformat(value) if value else None

    def age(self, now: datetime | None = None) -> timedelta | None:
        fetched = self.fetched_at()
        if fetched is None:
            return None
        return (now or datetime.now(UTC)) - fetched

    def is_stale(self, now: datetime | None = None) -> bool:
        age = self.age(now)
        return age is None or age > timedelta(days=STALE_DAYS)

    def needs_refresh(self, refresh_hours: float, now: datetime | None = None) -> bool:
        age = self.age(now)
        return age is None or age > timedelta(hours=refresh_hours)

    def save(self, text: str, now: datetime | None = None) -> int:
        triples = parse_tle(text)
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "satellites.tle").write_text(
            "\n".join("\n".join(t) for t in triples) + "\n", encoding="utf-8"
        )
        self.meta_path.write_text(
            json.dumps(
                {"fetched_at": (now or datetime.now(UTC)).isoformat(), "count": len(triples)}
            ),
            encoding="utf-8",
        )
        return len(triples)

    def load(self) -> list[EarthSatellite]:
        try:
            text = (self.dir / "satellites.tle").read_text(encoding="utf-8")
        except OSError:
            return []
        return satellites_from_tle(text)

    def age_text(self, now: datetime | None = None) -> str:
        """Czech description like ``stáří 6 h`` or ``žádná data``."""
        age = self.age(now)
        if age is None:
            return "žádná data o drahách"
        return f"stáří {format_age(age)}"


def format_age(age: timedelta) -> str:
    hours = age.total_seconds() / 3600
    if hours < 1:
        return f"{max(1, round(hours * 60))} min"
    if hours < 48:
        return f"{round(hours)} h"
    return f"{round(hours / 24)} d"


def satellites_from_tle(text: str) -> list[EarthSatellite]:
    ts = timescale()
    out = []
    for name, l1, l2 in parse_tle(text):
        sat = EarthSatellite(l1, l2, name, ts)
        num = int(sat.model.satnum)
        if num in NAMES_CS:
            sat.name = NAMES_CS[num]
        out.append(sat)
    return out


def celestrak_urls(groups: list[str], catnr: list[int], starlink: bool) -> list[str]:
    urls = [f"{CELESTRAK}?GROUP={g}&FORMAT=tle" for g in groups]
    urls += [f"{CELESTRAK}?CATNR={n}&FORMAT=tle" for n in catnr]
    if starlink:
        urls.append(f"{CELESTRAK}?GROUP=starlink&FORMAT=tle")
    return urls


async def refresh_tle(
    store: SatelliteStore,
    groups: list[str],
    catnr: list[int],
    starlink: bool = False,
    offline: bool = False,
    timeout: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> FetchResult:
    """Download TLEs from CelesTrak; on any failure the old cache stays in use."""
    if offline:
        return FetchResult(False, "offline režim, používám uložená data")
    chunks: list[str] = []
    own = client is None
    cl = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    try:
        for url in celestrak_urls(groups, catnr, starlink):
            resp = await cl.get(url)
            resp.raise_for_status()
            chunks.append(resp.text)
    except httpx.TimeoutException:
        return FetchResult(False, "CelesTrak neodpovídá (timeout), používám uložená data")
    except httpx.HTTPError as exc:
        return FetchResult(
            False,
            f"stažení drah selhalo ({type(exc).__name__}), používám uložená data",
        )
    finally:
        if own:
            await cl.aclose()
    text = "\n".join(chunks)
    if not parse_tle(text):
        return FetchResult(False, "CelesTrak vrátil neplatná data, používám uložená data")
    n = store.save(text)
    return FetchResult(True, f"dráhy aktualizovány ({n} satelitů)", n)


@dataclass(frozen=True)
class PassPoint:
    when: datetime
    alt: float
    az: float


@dataclass(frozen=True)
class SatPass:
    """One pass of a satellite above ``min_alt``."""

    name: str
    rise: PassPoint
    peak: PassPoint
    set: PassPoint
    visible: bool
    visible_from: datetime | None
    visible_to: datetime | None
    mag: float | None
    track: tuple[PassPoint, ...]


def standard_magnitude(sat: EarthSatellite) -> float | None:
    return STD_MAG.get(int(sat.model.satnum))


def satellite_magnitude(std_mag: float, range_km: float, phase_angle_deg: float) -> float:
    """Brightness from the standard magnitude (diffuse sphere phase law)."""
    phi = math.radians(max(0.0, min(180.0, phase_angle_deg)))
    f = (math.sin(phi) + (math.pi - phi) * math.cos(phi)) / math.pi
    f90 = 1.0 / math.pi
    if f <= 1e-6:
        return 99.0
    return std_mag + 5.0 * math.log10(range_km / 1000.0) - 2.5 * math.log10(f / f90)


def _phase_angle(sat: EarthSatellite, t: Any, location: Location) -> np.ndarray:
    eph = ephemeris()
    earth = eph["earth"]
    sat_pos = (earth + sat).at(t).position.km
    obs_pos = location.observer.at(t).position.km
    sun_pos = eph["sun"].at(t).position.km
    to_obs = obs_pos - sat_pos
    to_sun = sun_pos - sat_pos
    cos = np.sum(to_obs * to_sun, axis=0) / (
        np.linalg.norm(to_obs, axis=0) * np.linalg.norm(to_sun, axis=0)
    )
    result: np.ndarray = np.degrees(np.arccos(np.clip(cos, -1, 1)))
    return result


def find_passes(
    sat: EarthSatellite,
    start: datetime,
    end: datetime,
    location: Location,
    min_alt: float = 10.0,
    step_s: int = 10,
) -> list[SatPass]:
    """Passes above ``min_alt`` with visibility (sunlit satellite, dark observer)."""
    ts = timescale()
    eph = ephemeris()
    t0, t1 = ts_from_datetime(start), ts_from_datetime(end)
    times, events = sat.find_events(location.topos, t0, t1, altitude_degrees=min_alt)
    out: list[SatPass] = []
    diff = sat - location.topos
    std = standard_magnitude(sat)
    i = 0
    while i < len(events):
        if events[i] != 0:
            i += 1
            continue
        try:
            j = next(k for k in range(i + 1, len(events)) if events[k] == 2)
        except StopIteration:
            break
        peaks = [k for k in range(i + 1, j) if events[k] == 1]
        k_peak = peaks[0] if peaks else i
        tr, tp, tset = times[i], times[k_peak], times[j]
        n = max(3, int((tset.tt - tr.tt) * 86400 / step_s) + 1)
        grid = ts.tt_jd(np.linspace(tr.tt, tset.tt, n))
        alt, az, dist = diff.at(grid).altaz()
        sunlit = sat.at(grid).is_sunlit(eph)
        sun_alt = location.observer.at(grid).observe(eph["sun"]).apparent().altaz()[0].degrees
        vis = sunlit & (sun_alt < -6.0) & (alt.degrees >= min_alt - 0.5)
        mag = None
        if std is not None and vis.any():
            phase = _phase_angle(sat, grid, location)
            mags = [
                satellite_magnitude(std, float(d), float(p))
                for d, p, v in zip(dist.km, phase, vis, strict=False)
                if v
            ]
            mag = min(mags)
        track = tuple(
            PassPoint(to_datetime(grid[m]), float(alt.degrees[m]), float(az.degrees[m]))
            for m in range(0, n, max(1, n // 40))
        )

        def point(t: Any) -> PassPoint:
            a, z, _ = diff.at(t).altaz()
            return PassPoint(to_datetime(t), float(a.degrees), float(z.degrees))

        vis_idx = np.flatnonzero(vis)
        out.append(
            SatPass(
                name=sat.name,
                rise=point(tr),
                peak=point(tp),
                set=point(tset),
                visible=bool(vis.any()),
                visible_from=to_datetime(grid[int(vis_idx[0])]) if len(vis_idx) else None,
                visible_to=to_datetime(grid[int(vis_idx[-1])]) if len(vis_idx) else None,
                mag=mag,
                track=track,
            )
        )
        i = j + 1
    return out


def passes_for_all(
    sats: list[EarthSatellite],
    start: datetime,
    location: Location,
    days: int = 7,
    min_alt: float = 10.0,
    visible_only: bool = False,
) -> list[SatPass]:
    end = start + timedelta(days=days)
    out: list[SatPass] = []
    for sat in sats:
        out.extend(find_passes(sat, start, end, location, min_alt))
    if visible_only:
        out = [p for p in out if p.visible]
    out.sort(key=lambda p: p.rise.when)
    return out


def current_positions(
    sats: list[EarthSatellite], when: datetime, location: Location, limit: int = 200
) -> list[SatPosition]:
    """Satellites above the horizon at ``when`` (for the sky map)."""
    t = ts_from_datetime(when)
    eph = ephemeris()
    out = []
    for sat in sats[:limit]:
        alt, az, dist = (sat - location.topos).at(t).altaz()
        if alt.degrees <= 0:
            continue
        sunlit = bool(sat.at(t).is_sunlit(eph))
        std = standard_magnitude(sat)
        mag = None
        if std is not None and sunlit:
            phase = float(_phase_angle(sat, t, location))
            mag = satellite_magnitude(std, float(dist.km), phase)
        out.append(
            SatPosition(
                sat.name, float(alt.degrees), float(az.degrees), sunlit, float(dist.km), mag
            )
        )
    return out
