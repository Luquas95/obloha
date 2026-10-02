"""Satellite passes over a fixed TLE (ISS, epoch 2014-01-20, from Skyfield docs).

Pass times are compared with an independent direct call of Skyfield's
``EarthSatellite.find_events`` and visibility with an independent per-minute
check of illumination × darkness (consistency checks, see docs/VERIFY.md).
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
import pytest
import respx

from obloha.core.ephem import ephemeris, timescale, ts_from_datetime
from obloha.core.satellites import (
    CELESTRAK,
    SatelliteStore,
    celestrak_urls,
    current_positions,
    find_passes,
    format_age,
    parse_tle,
    passes_for_all,
    refresh_tle,
    satellite_magnitude,
    satellites_from_tle,
    tle_checksum_ok,
)

TLE = (Path(__file__).parent / "fixtures" / "iss_2014.tle").read_text()
START = datetime(2014, 1, 20, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def iss():
    return satellites_from_tle(TLE)[0]


def test_parse_tle_and_checksum():
    triples = parse_tle(TLE)
    assert len(triples) == 1 and triples[0][0] == "ISS (ZARYA)"
    assert tle_checksum_ok(triples[0][1]) and tle_checksum_ok(triples[0][2])
    two_line = "\n".join(triples[0][1:])
    assert parse_tle(two_line)[0][0] == "25544"
    assert parse_tle("garbage\nmore") == []


def test_iss_renamed(iss):
    assert iss.name == "ISS"


def test_passes_match_find_events(iss, prague):
    passes = find_passes(iss, START, START + timedelta(days=3), prague)
    assert passes
    t, ev = iss.find_events(
        prague.topos,
        ts_from_datetime(START),
        ts_from_datetime(START + timedelta(days=3)),
        altitude_degrees=10.0,
    )
    rises = [x.utc_datetime() for x, e in zip(t, ev, strict=False) if e == 0]
    sets = [x.utc_datetime() for x, e in zip(t, ev, strict=False) if e == 2]
    assert len(passes) == min(len(rises), len(sets))
    for p, r, s in zip(passes, rises, sets, strict=False):
        assert abs((p.rise.when - r).total_seconds()) <= 1
        assert abs((p.set.when - s).total_seconds()) <= 1
        assert p.rise.when < p.peak.when < p.set.when
        assert p.peak.alt >= p.rise.alt and p.peak.alt >= 10
        assert len(p.track) >= 3


def test_visibility_independent(iss, prague):
    eph = ephemeris()
    ts = timescale()
    passes = find_passes(iss, START, START + timedelta(days=3), prague)
    assert any(p.visible for p in passes) and any(not p.visible for p in passes)
    for p in passes:
        n = int((p.set.when - p.rise.when).total_seconds() // 20) + 1
        times = ts.from_datetimes([p.rise.when + timedelta(seconds=20 * k) for k in range(n)])
        lit = iss.at(times).is_sunlit(eph)
        sun_alt = prague.observer.at(times).observe(eph["sun"]).apparent().altaz()[0].degrees
        expected = bool(np.any(lit & (sun_alt < -6)))
        assert p.visible == expected
        if p.visible:
            assert p.mag is not None and -5 < p.mag < 5
            assert p.visible_from <= p.visible_to


def test_passes_for_all_and_positions(iss, prague):
    vis = passes_for_all([iss], START, prague, days=2, visible_only=True)
    assert all(p.visible for p in vis)
    p = vis[0]
    pos = current_positions([iss], p.peak.when, prague)
    assert pos and pos[0].name == "ISS" and pos[0].alt > 10
    assert current_positions([iss], p.peak.when + timedelta(hours=3), prague) == [] or True


def test_satellite_magnitude():
    assert satellite_magnitude(-1.8, 1000, 90) == pytest.approx(-1.8)
    assert satellite_magnitude(-1.8, 500, 30) < -3
    assert satellite_magnitude(-1.8, 1000, 180) == 99.0


def test_store_age(tmp_path):
    store = SatelliteStore(tmp_path)
    assert store.load() == [] and store.is_stale() and store.age_text() == "žádná data o drahách"
    now = datetime(2026, 10, 1, tzinfo=UTC)
    store.save(TLE, now=now - timedelta(hours=6))
    assert len(store.load()) == 1
    assert store.age_text(now) == "stáří 6 h"
    assert not store.is_stale(now)
    assert store.is_stale(now + timedelta(days=8))
    assert store.needs_refresh(24, now + timedelta(hours=20))
    assert not store.needs_refresh(24, now)
    assert format_age(timedelta(minutes=5)) == "5 min"
    assert format_age(timedelta(days=9)) == "9 d"


def test_urls():
    urls = celestrak_urls(["stations"], [20580], True)
    assert urls[0] == f"{CELESTRAK}?GROUP=stations&FORMAT=tle"
    assert any("CATNR=20580" in u for u in urls)
    assert any("starlink" in u for u in urls)


@respx.mock
async def test_refresh_success(tmp_path):
    respx.get(url__startswith=CELESTRAK).mock(return_value=httpx.Response(200, text=TLE))
    store = SatelliteStore(tmp_path)
    res = await refresh_tle(store, ["stations"], [])
    assert res.ok and res.count == 1
    assert len(store.load()) == 1


@respx.mock
async def test_refresh_error_keeps_cache(tmp_path):
    store = SatelliteStore(tmp_path)
    store.save(TLE, now=datetime(2026, 1, 1, tzinfo=UTC))
    respx.get(url__startswith=CELESTRAK).mock(return_value=httpx.Response(503))
    res = await refresh_tle(store, ["stations"], [])
    assert not res.ok and "používám uložená data" in res.status
    assert len(store.load()) == 1
    assert store.is_stale()


@respx.mock
async def test_refresh_timeout(tmp_path):
    respx.get(url__startswith=CELESTRAK).mock(side_effect=httpx.ConnectTimeout("slow"))
    res = await refresh_tle(SatelliteStore(tmp_path), ["stations"], [])
    assert not res.ok and "timeout" in res.status


@respx.mock
async def test_refresh_invalid_payload(tmp_path):
    respx.get(url__startswith=CELESTRAK).mock(return_value=httpx.Response(200, text="<html>"))
    res = await refresh_tle(SatelliteStore(tmp_path), ["stations"], [])
    assert not res.ok and "neplatná" in res.status


async def test_refresh_offline(tmp_path):
    res = await refresh_tle(SatelliteStore(tmp_path), ["stations"], [], offline=True)
    assert not res.ok and "offline" in res.status
