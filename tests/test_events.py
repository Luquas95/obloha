"""Calendar events.

Reference times (UTC, rounded to minutes) are from the USNO "Phases of the
Moon" and "Earth's Seasons" tables for 2026–2027 (see docs/VERIFY.md).
"""

from datetime import UTC, datetime

import pytest

from obloha.core.ephem import ts_from_datetime
from obloha.core.events import (
    EVENT_KINDS,
    compute_events,
    dst_events,
    meteor_events,
    moon_phase_events,
    season_events,
)

NEW_MOONS_2026 = [
    "01-18 19:52",
    "02-17 12:01",
    "03-19 01:23",
    "04-17 11:52",
    "05-16 20:01",
    "06-15 02:54",
    "07-14 09:44",
    "08-12 17:37",
    "09-11 03:27",
    "10-10 15:50",
    "11-09 07:02",
    "12-09 00:52",
]
FULL_MOONS_2026 = [
    "01-03 10:03",
    "02-01 22:09",
    "03-03 11:38",
    "04-02 02:12",
    "05-01 17:23",
    "05-31 08:45",
    "06-29 23:57",
    "07-29 14:36",
    "08-28 04:18",
    "09-26 16:49",
    "10-26 04:12",
    "11-24 14:53",
    "12-24 01:28",
]
SEASONS = [
    "2026-03-20 14:46",
    "2026-06-21 08:24",
    "2026-09-23 00:05",
    "2026-12-21 20:50",
    "2027-03-20 20:25",
    "2027-06-21 14:11",
    "2027-09-23 06:02",
    "2027-12-22 02:42",
]


def _ref(text, year=2026):
    if text.count("-") == 2:
        return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    return datetime.strptime(f"{year}-{text}", "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


def _span(y0, y1):
    return ts_from_datetime(datetime(y0, 1, 1, tzinfo=UTC)), ts_from_datetime(
        datetime(y1, 1, 1, tzinfo=UTC)
    )


def test_moon_phases_2026(prague):
    events = moon_phase_events(*_span(2026, 2027), prague)
    new = [e.when for e in events if e.title == "nov Měsíce"]
    full = [e.when for e in events if e.title == "úplněk"]
    assert len(new) == len(NEW_MOONS_2026) and len(full) == len(FULL_MOONS_2026)
    for got, ref in zip(new + full, NEW_MOONS_2026 + FULL_MOONS_2026, strict=True):
        assert abs((got - _ref(ref)).total_seconds()) <= 120, (got, ref)


def test_seasons_2026_2027(prague):
    events = season_events(*_span(2026, 2028), prague)
    assert len(events) == 8
    for got, ref in zip(events, SEASONS, strict=True):
        assert abs((got.when - _ref(ref)).total_seconds()) <= 60, (got.when, ref)


def test_meteor_showers_with_moon(prague):
    ev = meteor_events(datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC), prague)
    assert [e.title for e in ev] == ["Perseidy (maximum, až ~100 meteorů/h)"]
    # Perseids 2026 peak right after new Moon: no Moon interference
    assert ev[0].extra["moon_factor"] == 1.0
    ev = meteor_events(
        datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 31, tzinfo=UTC), prague
    )
    names = [e.title.split()[0] for e in ev]
    assert names == ["Drakonidy", "Orionidy"]


def test_dst_events(prague):
    ev = dst_events(datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC), prague)
    assert len(ev) == 1
    assert ev[0].title == "konec letního času (03:00 → 02:00)"
    assert ev[0].when == datetime(2026, 10, 25, 1, tzinfo=UTC)
    ev = dst_events(datetime(2026, 3, 1, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC), prague)
    assert ev[0].title == "začátek letního času (02:00 → 03:00)"


@pytest.fixture(scope="module")
def autumn_events():
    from obloha.core.location import PRAGUE

    return compute_events(
        datetime(2026, 10, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC), PRAGUE
    )


def test_calendar_contents(autumn_events):
    titles = [e.title for e in autumn_events]
    assert "Saturn v opozici" in titles
    assert "Venuše v dolní konjunkci" in titles
    assert any(t.startswith("Merkur v největší večerní") for t in titles)
    assert any(t.startswith("Měsíc a Jupiter") for t in titles)
    assert any(t.startswith("Měsíc v perigeu") for t in titles)
    assert "zimní slunovrat" in titles
    assert [e.when for e in autumn_events] == sorted(e.when for e in autumn_events)
    assert {e.kind for e in autumn_events} <= set(EVENT_KINDS)


def test_saturn_opposition_date(autumn_events):
    opp = next(e for e in autumn_events if e.title == "Saturn v opozici")
    assert opp.when.date().isoformat() == "2026-10-04"


def test_kind_filter(prague):
    ev = compute_events(
        datetime(2026, 10, 1, tzinfo=UTC),
        datetime(2026, 11, 1, tzinfo=UTC),
        prague,
        kinds=["season", "dst"],
    )
    assert [e.kind for e in ev] == ["dst"]


def test_inner_planet_conjunctions_are_not_oppositions(prague):
    from obloha.core.events import opposition_events

    ev = opposition_events(*_span(2026, 2027), prague)
    inner = [e.title for e in ev if e.bodies[0] in ("mercury", "venus")]
    assert inner and not any("opozici" in t for t in inner)
    assert "Venuše v horní konjunkci" in inner and "Venuše v dolní konjunkci" in inner


def test_moon_conjunction_is_topocentric(prague):
    from obloha.core.events import conjunction_events

    t0 = ts_from_datetime(datetime(2026, 10, 5, tzinfo=UTC))
    t1 = ts_from_datetime(datetime(2026, 10, 8, tzinfo=UTC))
    ev = [e for e in conjunction_events(t0, t1, prague) if e.bodies == ("moon", "jupiter")]
    assert len(ev) == 1
    # geocentric minimum is 0.2°, from Prague the Moon passes 0.6° away
    assert ev[0].extra["separation"] == pytest.approx(0.58, abs=0.05)
