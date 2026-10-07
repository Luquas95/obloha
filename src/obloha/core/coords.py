"""Fast vectorised coordinate transforms for many stars at once.

Stars are kept as ICRS unit vectors. For a given time and place we build one
3x3 matrix (precession + nutation + Earth rotation + local frame) and apply
it to all vectors. Aberration (≤ 20″) and polar motion are ignored, which is
far below the resolution of a terminal map. Bodies of the Solar System are
computed with full Skyfield ``observe().apparent()`` instead (see ``bodies``).
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]

#: Refraction is applied only above this true altitude (degrees).
REFRACTION_MIN_ALT = -2.0


def radec_to_vec(ra_deg: FloatArray | float, dec_deg: FloatArray | float) -> FloatArray:
    """Convert RA/Dec in degrees to unit vectors (..., 3)."""
    ra = np.radians(np.asarray(ra_deg, dtype=np.float64))
    dec = np.radians(np.asarray(dec_deg, dtype=np.float64))
    cd = np.cos(dec)
    return np.stack([cd * np.cos(ra), cd * np.sin(ra), np.sin(dec)], axis=-1)


def vec_to_radec(v: FloatArray) -> tuple[FloatArray, FloatArray]:
    """Inverse of :func:`radec_to_vec`, returns degrees."""
    v = np.asarray(v, dtype=np.float64)
    ra = np.degrees(np.arctan2(v[..., 1], v[..., 0])) % 360.0
    dec = np.degrees(np.arcsin(np.clip(v[..., 2], -1.0, 1.0)))
    return ra, dec


def _rot_z(angle_rad: float) -> FloatArray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def local_sidereal_deg(t: Any, lon_deg: float) -> float:
    """Local apparent sidereal time in degrees."""
    return float((t.gast * 15.0 + lon_deg) % 360.0)


def horizon_matrix(t: Any, lat_deg: float, lon_deg: float) -> FloatArray:
    """Matrix mapping ICRS unit vectors to local (north, east, up) vectors."""
    lst = np.radians(local_sidereal_deg(t, lon_deg))
    phi = np.radians(lat_deg)
    local = np.array(
        [
            [-np.sin(phi), 0.0, np.cos(phi)],  # north
            [0.0, 1.0, 0.0],  # east
            [np.cos(phi), 0.0, np.sin(phi)],  # up
        ]
    )
    # Rotate the true-of-date frame so that the local meridian lies at x.
    # Note: rotating by -LST maps hour angle 90° (west) to -y, so east is +y.
    m_date = np.asarray(t.M, dtype=np.float64)
    return np.asarray(local @ _rot_z(-lst) @ m_date)


def nev_to_altaz(nev: FloatArray) -> tuple[FloatArray, FloatArray]:
    """North/east/up vectors -> (alt, az) degrees, az from north through east."""
    alt = np.degrees(np.arcsin(np.clip(nev[..., 2], -1.0, 1.0)))
    az = np.degrees(np.arctan2(nev[..., 1], nev[..., 0])) % 360.0
    return alt, az


def altaz_to_nev(alt_deg: FloatArray | float, az_deg: FloatArray | float) -> FloatArray:
    alt = np.radians(np.asarray(alt_deg, dtype=np.float64))
    az = np.radians(np.asarray(az_deg, dtype=np.float64))
    ca = np.cos(alt)
    return np.stack([ca * np.cos(az), ca * np.sin(az), np.sin(alt)], axis=-1)


def refraction(alt_true_deg: FloatArray) -> FloatArray:
    """Standard atmospheric refraction (Sæmundsson), degrees to add."""
    h = np.asarray(alt_true_deg, dtype=np.float64)
    hc = np.maximum(h, REFRACTION_MIN_ALT)
    r = 1.02 / np.tan(np.radians(hc + 10.3 / (hc + 5.11))) / 60.0
    return np.where(h > REFRACTION_MIN_ALT, r, 0.0)


def unrefract(alt_apparent_deg: FloatArray) -> FloatArray:
    """Approximate inverse of :func:`refraction` (Bennett)."""
    h = np.asarray(alt_apparent_deg, dtype=np.float64)
    hc = np.maximum(h, REFRACTION_MIN_ALT + 0.5)
    r = 1.0 / np.tan(np.radians(hc + 7.31 / (hc + 4.4))) / 60.0
    return np.where(h > REFRACTION_MIN_ALT + 0.5, h - r, h)


def icrs_to_altaz(
    vectors: FloatArray, t: Any, lat_deg: float, lon_deg: float, refract: bool = True
) -> tuple[FloatArray, FloatArray]:
    """Transform ICRS unit vectors to apparent (alt, az) in degrees."""
    nev = vectors @ horizon_matrix(t, lat_deg, lon_deg).T
    alt, az = nev_to_altaz(nev)
    if refract:
        alt = alt + refraction(alt)
    return alt, az


def altaz_to_radec(
    alt_deg: FloatArray | float,
    az_deg: FloatArray | float,
    t: Any,
    lat_deg: float,
    lon_deg: float,
    refracted: bool = True,
) -> tuple[FloatArray, FloatArray]:
    """Inverse transform: apparent alt/az -> ICRS RA/Dec (degrees)."""
    alt = np.asarray(alt_deg, dtype=np.float64)
    if refracted:
        alt = unrefract(alt)
    nev = altaz_to_nev(alt, az_deg)
    icrs = nev @ horizon_matrix(t, lat_deg, lon_deg)
    return vec_to_radec(icrs)


def separation_deg(alt1: Any, az1: Any, alt2: Any, az2: Any) -> FloatArray:
    """Angular distance between two horizontal directions in degrees."""
    a = altaz_to_nev(alt1, az1)
    b = altaz_to_nev(alt2, az2)
    dot = np.clip(np.sum(a * b, axis=-1), -1.0, 1.0)
    return np.degrees(np.arccos(dot))


def format_ra(ra_deg: float) -> str:
    """Format RA as ``0h 51m``."""
    total_min = round((ra_deg % 360.0) / 15.0 * 60.0) % (24 * 60)
    return f"{total_min // 60}h {total_min % 60:02d}m"


def format_dec(dec_deg: float) -> str:
    """Format Dec as ``+2° 48′``."""
    sign = "+" if dec_deg >= 0 else "−"
    total = round(abs(dec_deg) * 60.0)
    return f"{sign}{total // 60}° {total % 60:02d}′"
