"""Eclipses.

Reference values: NASA Five Millennium Canon of Lunar Eclipses and NASA
solar eclipse local circumstances (eclipse.gsfc.nasa.gov), transcribed in
docs/VERIFY.md. Times in UTC; Prague local time = UTC+2 in summer.
"""

from datetime import UTC, datetime

import pytest

from obloha.core.eclipses import _obscuration, find_lunar_eclipses, find_solar_eclipses

LUNAR_2026_2028 = [
    # (greatest eclipse UTC, type code, umbral magnitude)
    ("2026-03-03 11:34", 2, 1.15),
    ("2026-08-28 04:13", 1, 0.93),
    ("2027-02-20 23:13", 0, -0.06),
    ("2027-07-18 16:03", 0, -1.07),
    ("2027-08-17 07:14", 0, -0.52),
    ("2028-01-12 04:13", 1, 0.07),
    ("2028-07-06 18:20", 1, 0.39),
    ("2028-12-31 16:52", 2, 1.25),
]


def _t(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


@pytest.fixture(scope="module")
def lunar():
    from obloha.core.location import PRAGUE

    return find_lunar_eclipses(_t("2026-01-01 00:00"), _t("2029-01-01 00:00"), PRAGUE)


def test_lunar_eclipse_catalog(lunar):
    assert len(lunar) == len(LUNAR_2026_2028)
    for got, (when, kind, mag) in zip(lunar, LUNAR_2026_2028, strict=True):
        assert abs((got.maximum - _t(when)).total_seconds()) <= 120
        assert got.kind == kind
        assert got.umbral_magnitude == pytest.approx(mag, abs=0.02)


def test_lunar_contacts_and_visibility(lunar):
    total = lunar[0]
    assert total.penumbral_begin < total.partial_begin < total.total_begin < total.maximum
    assert total.maximum < total.total_end < total.partial_end < total.penumbral_end
    assert not total.visible  # 3. 3. 2026: Moon below the horizon in Prague
    assert lunar[1].visible  # 28. 8. 2026: partial, Moon setting in the morning
    assert lunar[-1].visible and lunar[-1].moon_alt_at_max > 5
    assert lunar[2].partial_begin is None


@pytest.fixture(scope="module")
def solar():
    from obloha.core.location import PRAGUE

    return find_solar_eclipses(_t("2026-01-01 00:00"), _t("2028-01-01 00:00"), PRAGUE)


def test_solar_global_types(solar):
    got = [(e.global_maximum.date().isoformat(), e.global_type) for e in solar]
    assert got == [
        ("2026-02-17", "prstencové"),
        ("2026-08-12", "úplné"),
        ("2027-02-06", "prstencové"),
        ("2027-08-02", "úplné"),
    ]


def test_solar_2026_08_12_from_prague(solar):
    e = solar[1]
    assert e.local_type == "částečné"
    # NASA: greatest eclipse 17:46 UT globally; Prague maximum ≈ 18:12 UT,
    # magnitude ≈ 0.88 with the Sun very low in the west.
    assert abs((e.global_maximum - _t("2026-08-12 17:46")).total_seconds()) <= 300
    assert abs((e.maximum - _t("2026-08-12 18:12")).total_seconds()) <= 300
    assert e.magnitude == pytest.approx(0.88, abs=0.03)
    assert 0 < e.sun_alt_at_max < 5
    assert e.begin < e.maximum < e.end


def test_solar_2027_08_02_from_prague(solar):
    e = solar[3]
    assert e.local_type == "částečné"
    assert abs((e.global_maximum - _t("2027-08-02 10:07")).total_seconds()) <= 300
    assert abs((e.maximum - _t("2027-08-02 09:15")).total_seconds()) <= 300
    assert e.magnitude == pytest.approx(0.52, abs=0.04)
    assert e.sun_alt_at_max > 40


def test_not_visible_annular(solar):
    assert not solar[0].visible
    assert solar[0].maximum is None


def test_obscuration_geometry():
    assert _obscuration(1.0, 1.0, 3.0) == 0.0
    assert _obscuration(1.0, 1.1, 0.0) == 1.0
    assert _obscuration(1.0, 0.9, 0.0) == pytest.approx(0.81)
    half = _obscuration(1.0, 1.0, 1.0)
    assert 0.3 < half < 0.45
