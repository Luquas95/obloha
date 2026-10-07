from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from skyfield.api import Star

from obloha.core.catalog import catalog
from obloha.core.coords import (
    altaz_to_radec,
    format_dec,
    format_ra,
    icrs_to_altaz,
    radec_to_vec,
    refraction,
    separation_deg,
    unrefract,
    vec_to_radec,
)
from obloha.core.ephem import OutOfRangeError, ts_from_datetime


def _star_altaz(name, when, loc):
    c = catalog()
    i = c.star_by_key(name)
    t = ts_from_datetime(when)
    alt, az = icrs_to_altaz(c.vectors[i : i + 1], t, loc.lat, loc.lon)
    return float(alt[0]), float(az[0])


def test_polaris_altitude_equals_latitude(prague, fixed_utc):
    alt, az = _star_altaz("Polaris", fixed_utc, prague)
    # Polaris is 0.74° from the pole, so alt = lat ± 0.74°.
    assert abs(alt - prague.lat) < 0.8
    assert min(az, 360 - az) < 1.2


def test_vega_upper_culmination(prague):
    start = datetime(2026, 8, 1, 12, tzinfo=UTC)
    samples = [start + timedelta(minutes=m) for m in range(0, 24 * 60, 2)]
    best = max((_star_altaz("Vega", s, prague), s) for s in samples)
    (alt, az), _ = best
    expected = 90.0 - (50.0755 - 38.78)
    assert alt == pytest.approx(expected, abs=0.15)
    assert az == pytest.approx(180.0, abs=3.0)


def test_matches_skyfield_full_reduction(prague, fixed_utc):
    c = catalog()
    t = ts_from_datetime(fixed_utc)
    for name in ("Vega", "Sirius", "Capella", "Altair"):
        i = c.star_by_key(name)
        alt, az = icrs_to_altaz(c.vectors[i : i + 1], t, prague.lat, prague.lon)
        star = Star(ra_hours=c.ra[i] / 15.0, dec_degrees=c.dec[i])
        a2, z2, _ = prague.observer.at(t).observe(star).apparent().altaz("standard")
        assert float(separation_deg(alt[0], az[0], a2.degrees, z2.degrees)) < 0.05


def test_altaz_radec_roundtrip(prague, fixed_utc):
    t = ts_from_datetime(fixed_utc)
    ra = np.array([10.0, 120.0, 279.23, 350.0])
    dec = np.array([-20.0, 5.0, 38.78, 60.0])
    alt, az = icrs_to_altaz(radec_to_vec(ra, dec), t, prague.lat, prague.lon)
    ra2, dec2 = altaz_to_radec(alt, az, t, prague.lat, prague.lon)
    assert np.allclose(dec2, dec, atol=0.02)
    assert np.allclose((ra2 - ra + 180) % 360 - 180, 0, atol=0.03)


def test_vec_roundtrip():
    ra, dec = vec_to_radec(radec_to_vec(123.0, -45.0))
    assert float(ra) == pytest.approx(123.0)
    assert float(dec) == pytest.approx(-45.0)


def test_refraction_values():
    assert float(refraction(np.array([0.0]))[0]) == pytest.approx(0.48, abs=0.05)
    assert float(refraction(np.array([45.0]))[0]) == pytest.approx(1.0 / 60, abs=0.003)
    assert float(refraction(np.array([-5.0]))[0]) == 0.0
    h = np.array([5.0, 20.0, 60.0])
    assert np.allclose(unrefract(h + refraction(h)), h, atol=0.01)


def test_formatting():
    assert format_ra(12.75) == "0h 51m"
    assert format_dec(2.8) == "+2° 48′"
    assert format_dec(-0.5) == "−0° 30′"


def test_out_of_range():
    with pytest.raises(OutOfRangeError):
        ts_from_datetime(datetime(2060, 1, 1, tzinfo=UTC))
    with pytest.raises(ValueError):
        ts_from_datetime(datetime(2020, 1, 1))
