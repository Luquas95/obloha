"""Sun and Moon rise/set, twilight and planet visibility.

Reference policy (see docs/VERIFY.md): exact ±1 min checks compare our
wrapper with Skyfield's independent ``risings_and_settings`` +
``find_discrete`` code path (consistency check). Published values for Prague
(timeanddate.com / Hvězdářská ročenka, rounded to minutes) are checked with
±2 min because they are given for a slightly different horizon convention.
"""

import math
from datetime import UTC, datetime, timedelta

import pytest
from skyfield import almanac as sf_almanac
from skyfield.searchlib import find_discrete

from obloha.core.almanac import (
    local_noon,
    moon_info,
    night_start,
    planets_tonight,
    rise_transit_set,
    sky_phase,
    twilight,
)
from obloha.core.bodies import BODY_BY_ID, compute_bodies, moon_symbol, phase_name
from obloha.core.ephem import ephemeris, timescale, ts_from_datetime


def _skyfield_sun_events(day_noon_utc, loc):
    ts = timescale()
    t0 = ts_from_datetime(day_noon_utc - timedelta(hours=12))
    t1 = ts.tt_jd(t0.tt + 1.0)
    # Horizon -50′ = refraction 34′ + solar semi-diameter 16′ (same convention as USNO).
    f = sf_almanac.risings_and_settings(
        ephemeris(), ephemeris()["sun"], loc.topos, horizon_degrees=-0.8333
    )
    times, ups = find_discrete(t0, t1, f)
    rise = next(t.utc_datetime() for t, u in zip(times, ups, strict=False) if u)
    sett = next(t.utc_datetime() for t, u in zip(times, ups, strict=False) if not u)
    return rise, sett


# (date, UTC offset hours) — includes both DST transitions of 2026
DATES = [
    (datetime(2026, 1, 15), 1),
    (datetime(2026, 3, 28), 1),  # day before switch to CEST
    (datetime(2026, 3, 29), 2),  # switch day
    (datetime(2026, 6, 21), 2),
    (datetime(2026, 10, 25), 1),  # switch back to CET
    (datetime(2026, 12, 21), 1),
]


@pytest.mark.parametrize(("day", "offset"), DATES)
def test_sunrise_sunset_consistency(prague, day, offset):
    noon = local_noon(day.replace(tzinfo=UTC), prague)
    ref_rise, ref_set = _skyfield_sun_events(noon, prague)
    tw_prev = twilight(noon - timedelta(days=1), prague)
    tw = twilight(noon, prague)
    assert abs((tw_prev.sunrise - ref_rise).total_seconds()) < 60
    assert abs((tw.sunset - ref_set).total_seconds()) < 60
    assert tw.sunset.astimezone(prague.zone).utcoffset() == timedelta(hours=offset)


@pytest.mark.parametrize(
    ("day", "rise_local", "set_local"),
    [
        # timeanddate.com, Prague (UTC+1/+2), rounded to minutes
        (datetime(2026, 6, 21), "04:52", "21:15"),
        (datetime(2026, 12, 21), "07:59", "16:02"),
    ],
)
def test_sun_times_published_prague(prague, day, rise_local, set_local):
    noon = local_noon(day.replace(tzinfo=UTC), prague)
    tw_prev = twilight(noon - timedelta(days=1), prague)
    tw = twilight(noon, prague)

    def minutes(dt):
        loc = dt.astimezone(prague.zone)
        return loc.hour * 60 + loc.minute + loc.second / 60

    def ref(text):
        h, m = text.split(":")
        return int(h) * 60 + int(m)

    assert abs(minutes(tw_prev.sunrise) - ref(rise_local)) <= 2
    assert abs(minutes(tw.sunset) - ref(set_local)) <= 2


def test_moon_rise_set_consistency(prague):
    start = datetime(2026, 10, 1, 10, tzinfo=UTC)
    rts = rise_transit_set(BODY_BY_ID["moon"], start, prague, hours=26)
    ts = timescale()
    t0 = ts_from_datetime(start)
    t1 = ts.tt_jd(t0.tt + 26 / 24)
    dist = prague.observer.at(t0).observe(ephemeris()["moon"]).distance().km
    radius = math.degrees(math.asin(1737.4 / dist))
    f = sf_almanac.risings_and_settings(
        ephemeris(), ephemeris()["moon"], prague.topos, radius_degrees=radius
    )
    times, ups = find_discrete(t0, t1, f)
    rise = next(t.utc_datetime() for t, u in zip(times, ups, strict=False) if u)
    assert abs((rts.rise - rise).total_seconds()) < 60
    assert rts.transit is not None and rts.transit_alt is not None


def test_twilight_order_and_night_length(prague, fixed_utc):
    tw = twilight(night_start(fixed_utc, prague), prague)
    order = [
        tw.sunset,
        tw.civil_end,
        tw.nautical_end,
        tw.astro_end,
        tw.astro_start,
        tw.nautical_start,
        tw.civil_start,
        tw.sunrise,
    ]
    assert all(o is not None for o in order)
    assert order == sorted(order)
    assert timedelta(hours=8) < tw.astro_night < timedelta(hours=10)


def test_no_astronomical_night_in_june(prague):
    tw = twilight(local_noon(datetime(2026, 6, 21, tzinfo=UTC), prague), prague)
    assert tw.astro_end is None
    assert tw.astro_night == timedelta()


def test_night_start_before_noon(prague):
    morning = datetime(2026, 10, 2, 3, tzinfo=UTC)
    assert night_start(morning, prague).date() == datetime(2026, 10, 1).date()


def test_sky_phase_names():
    assert sky_phase(10) == "den"
    assert sky_phase(-3) == "občanský soumrak"
    assert sky_phase(-9) == "nautický soumrak"
    assert sky_phase(-15) == "astronomický soumrak"
    assert sky_phase(-25) == "astronomická noc"


def test_moon_info_fixed(fixed_utc):
    mi = moon_info(fixed_utc)
    assert 0.65 < mi.illumination < 0.75
    assert not mi.waxing
    assert mi.phase_name == "ubývající Měsíc"
    assert mi.next_new.date().isoformat() == "2026-10-10"
    assert mi.next_full.date().isoformat() == "2026-10-26"
    assert 19 < mi.age_days < 22


def test_phase_helpers():
    assert phase_name(0) == "nov"
    assert phase_name(90) == "první čtvrť"
    assert phase_name(180) == "úplněk"
    assert phase_name(350) == "nov"
    assert moon_symbol(250) == "◑"
    assert moon_symbol(100, ascii_only=True) == "D"
    assert moon_symbol(180) == "○"
    assert moon_symbol(5) == "●"


def test_bodies_fixed(prague, fixed_utc):
    b = compute_bodies(fixed_utc, prague)
    assert b["sun"].alt < -18
    assert b["saturn"].alt > 10 and 90 < b["saturn"].az < 135
    assert 0 < b["saturn"].mag < 1
    assert b["venus"].mag < -3.5
    assert b["moon"].distance_au * 149_597_870 < 410_000
    assert all(len(s.constellation) == 3 for s in b.values())


def test_planets_tonight_sorted(prague, fixed_utc):
    ps = planets_tonight(night_start(fixed_utc, prague), prague)
    assert ps[0].info.id == "saturn"
    assert [p.score for p in ps] == sorted((p.score for p in ps), reverse=True)
    venus = next(p for p in ps if p.info.id == "venus")
    assert not venus.observable
