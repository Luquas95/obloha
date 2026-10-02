import numpy as np
import pytest

from obloha.core.projection import FullSky, Panorama, Stereographic, wrap180

ALT = np.array([0.0, 10.0, 45.0, 80.0, 30.0])
AZ = np.array([0.0, 90.0, 180.0, 270.0, 135.0])


def test_fullsky_orientation():
    p = FullSky(100, 100)
    x, y, ok = p.forward(np.array([90.0, 0.0, 0.0, 0.0, 0.0]), np.array([0, 0, 90, 180, 270.0]))
    assert ok.all()
    assert x[0] == pytest.approx(p.cx) and y[0] == pytest.approx(p.cy)
    assert y[1] < p.cy  # north up
    assert x[2] < p.cx  # east left
    assert y[3] > p.cy  # south down
    assert x[4] > p.cx  # west right


@pytest.mark.parametrize(
    "proj",
    [FullSky(160, 120), Stereographic(160, 120, 135.0, 30.0, 120.0), Panorama(160, 120, 180, 150)],
)
def test_inverse_roundtrip(proj):
    x, y, ok = proj.forward(ALT, AZ)
    alt, az, _ = proj.inverse(x[ok], y[ok])
    assert np.allclose(alt, ALT[ok], atol=1e-6)
    assert np.allclose(wrap180(az - AZ[ok]), 0, atol=1e-6)


def test_stereographic_center_and_direction():
    p = Stereographic(100, 80, center_az=180, center_alt=20, fov=90)
    x, y, _ = p.forward(np.array([20.0, 20.0, 40.0]), np.array([180.0, 200.0, 180.0]))
    assert x[0] == pytest.approx(49.5) and y[0] == pytest.approx(39.5)
    assert x[1] > x[0]  # larger azimuth (towards west) is right when facing south
    assert y[2] < y[0]
    assert p.degrees_per_dot() == pytest.approx(0.9)


def test_stereographic_zenith_view():
    p = Stereographic(100, 100, center_az=0, center_alt=90, fov=120)
    x, _, ok = p.forward(np.array([90.0]), np.array([0.0]))
    assert ok[0] and x[0] == pytest.approx(49.5)


def test_panorama_horizon_bottom():
    p = Panorama(200, 100, center_az=180, fov=200, bottom_alt=-5)
    assert p.y_of_alt(-5) == pytest.approx(99)
    assert p.top_alt == pytest.approx(95)
    assert p.x_of_az(180) == pytest.approx(99.5)
    _, _, ok = p.forward(np.array([10.0]), np.array([0.0]))
    assert not ok[0]
