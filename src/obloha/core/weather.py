"""Cloud forecast (Open-Meteo) and the hourly observing score."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from obloha.core.almanac import altitude_series
from obloha.core.bodies import BODY_BY_ID
from obloha.core.location import Location

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
HOURLY = "cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,visibility"
CACHE_TTL = timedelta(hours=1)
CACHE_MAX_AGE = timedelta(hours=36)


@dataclass(frozen=True)
class HourWeather:
    when: datetime  # UTC, start of hour
    cloud: float  # %
    low: float
    mid: float
    high: float
    visibility_km: float | None


@dataclass(frozen=True)
class Forecast:
    hours: tuple[HourWeather, ...]
    fetched_at: datetime
    stale: bool = False

    def at(self, when: datetime) -> HourWeather | None:
        key = when.replace(minute=0, second=0, microsecond=0)
        for h in self.hours:
            if h.when == key:
                return h
        return None


@dataclass(frozen=True)
class WeatherResult:
    forecast: Forecast | None
    status: str  # user-facing Czech


def _cache_file(cache: Path, location: Location) -> Path:
    return cache / "weather" / f"{location.lat:.2f}_{location.lon:.2f}.json"


def parse_open_meteo(data: dict[str, Any], fetched_at: datetime, stale: bool = False) -> Forecast:
    hourly = data["hourly"]
    hours = []
    for i, ts in enumerate(hourly["time"]):
        when = datetime.fromisoformat(ts).replace(tzinfo=UTC)

        def val(key: str, i: int = i) -> float:
            v = hourly.get(key, [None] * (i + 1))[i]
            return float(v) if v is not None else 0.0

        vis = hourly.get("visibility", [None] * (i + 1))[i]
        hours.append(
            HourWeather(
                when,
                val("cloud_cover"),
                val("cloud_cover_low"),
                val("cloud_cover_mid"),
                val("cloud_cover_high"),
                float(vis) / 1000.0 if vis is not None else None,
            )
        )
    return Forecast(tuple(hours), fetched_at, stale)


def load_cached(cache: Path, location: Location, now: datetime) -> Forecast | None:
    path = _cache_file(cache, location)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    fetched = datetime.fromisoformat(payload["fetched_at"])
    if now - fetched > CACHE_MAX_AGE:
        return None
    return parse_open_meteo(payload["data"], fetched, stale=now - fetched > CACHE_TTL)


async def fetch_forecast(
    cache: Path,
    location: Location,
    now: datetime | None = None,
    offline: bool = False,
    timeout: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> WeatherResult:
    """Return a forecast from cache or Open-Meteo. Never raises on network errors."""
    now = now or datetime.now(UTC)
    cached = load_cached(cache, location, now)
    if cached is not None and not cached.stale:
        return WeatherResult(cached, "předpověď z mezipaměti")
    if offline:
        if cached:
            return WeatherResult(cached, "offline režim, starší předpověď")
        return WeatherResult(None, "offline režim: počasí není k dispozici")
    params: dict[str, str | float | int] = {
        "latitude": round(location.lat, 3),
        "longitude": round(location.lon, 3),
        "hourly": HOURLY,
        "timezone": "UTC",
        "forecast_days": 3,
    }
    own = client is None
    cl = client or httpx.AsyncClient(timeout=timeout)
    try:
        resp = await cl.get(OPEN_METEO, params=params)
        resp.raise_for_status()
        data = resp.json()
        forecast = parse_open_meteo(data, now)
    except httpx.TimeoutException:
        return _fallback(cached, "Open-Meteo neodpovídá (timeout)")
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return _fallback(cached, f"předpověď se nepodařilo stáhnout ({type(exc).__name__})")
    finally:
        if own:
            await cl.aclose()
    path = _cache_file(cache, location)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"fetched_at": now.isoformat(), "data": data}), encoding="utf-8")
    except OSError:  # pragma: no cover
        pass
    return WeatherResult(forecast, "předpověď Open-Meteo")


def _fallback(cached: Forecast | None, reason: str) -> WeatherResult:
    if cached:
        return WeatherResult(cached, f"{reason}, starší předpověď")
    return WeatherResult(None, f"{reason}: počasí není k dispozici")


@dataclass(frozen=True)
class HourScore:
    when: datetime
    score: int  # 0-100
    darkness: float
    moon: float
    clouds: float | None


def darkness_factor(sun_alt: float) -> float:
    if sun_alt >= -6:
        return 0.0
    if sun_alt <= -18:
        return 1.0
    return 0.15 + 0.85 * (-6 - sun_alt) / 12.0


def moon_factor(illumination: float, moon_alt: float) -> float:
    """1 = Moon does not disturb, lower = brighter sky."""
    if moon_alt <= 0:
        return 1.0
    return float(1.0 - 0.55 * illumination * math.sqrt(math.sin(math.radians(min(moon_alt, 90)))))


def cloud_factor(h: HourWeather) -> float:
    # thin high clouds (cirrus) block less light than low and mid clouds
    thin_high = max(0.0, h.high - h.low - h.mid)
    eff = min(100.0, max(h.low, h.cloud - 0.4 * thin_high))
    f = float((1.0 - eff / 100.0) ** 1.3)
    if h.visibility_km is not None and h.visibility_km < 10:
        f *= max(0.3, h.visibility_km / 10.0)
    return f


def night_scores(
    start: datetime,
    end: datetime,
    location: Location,
    forecast: Forecast | None,
    moon_illumination: float,
) -> list[HourScore]:
    """Hourly observing score (0–100) for hours between ``start`` and ``end``."""
    first = start.replace(minute=0, second=0, microsecond=0)
    hours = []
    t = first
    while t < end:
        hours.append(t)
        t += timedelta(hours=1)
    mids = [h + timedelta(minutes=30) for h in hours]
    sun = altitude_series(BODY_BY_ID["sun"], mids, location)
    moon = altitude_series(BODY_BY_ID["moon"], mids, location)
    out = []
    for h, s, m in zip(hours, sun, moon, strict=False):
        d = darkness_factor(float(s))
        mf = moon_factor(moon_illumination, float(m))
        hw = forecast.at(h) if forecast else None
        cf = cloud_factor(hw) if hw else None
        value = d * mf * (cf if cf is not None else 1.0)
        out.append(HourScore(h, round(100 * value), d, mf, hw.cloud if hw else None))
    return out


def best_window(scores: list[HourScore], threshold: int = 50) -> tuple[datetime, datetime] | None:
    """Longest run of hours with score >= threshold (ties: higher total)."""
    best: tuple[int, int, int, int] | None = None  # length, total, start, end
    i = 0
    vals = np.array([s.score for s in scores])
    while i < len(scores):
        if vals[i] < threshold:
            i += 1
            continue
        j = i
        while j + 1 < len(scores) and vals[j + 1] >= threshold:
            j += 1
        cand = (j - i + 1, int(vals[i : j + 1].sum()), i, j)
        if best is None or cand[:2] > best[:2]:
            best = cand
        i = j + 1
    if best is None:
        return None
    return scores[best[2]].when, scores[best[3]].when + timedelta(hours=1)


def score_word(score: int) -> str:
    if score >= 75:
        return "výborné"
    if score >= 55:
        return "dobré"
    if score >= 30:
        return "průměrné"
    if score > 0:
        return "špatné"
    return "nelze pozorovat"
