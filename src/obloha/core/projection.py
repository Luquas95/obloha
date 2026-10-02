"""Sky projections from (alt, az) to sub-pixel canvas coordinates and back.

All projections work in *dot* coordinates: for braille rendering one terminal
cell holds 2×4 dots, for half blocks 1×2. Dots are assumed to be square.
``x`` grows to the right, ``y`` grows downwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from obloha.core.coords import altaz_to_nev, nev_to_altaz

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]


def wrap180(deg: FloatArray | float) -> FloatArray:
    """Wrap angles into [-180, 180)."""
    return (np.asarray(deg, dtype=np.float64) + 180.0) % 360.0 - 180.0


class Projection(Protocol):
    """Common interface of all projections."""

    width: int
    height: int

    def forward(self, alt: FloatArray, az: FloatArray) -> tuple[FloatArray, FloatArray, BoolArray]:
        """Return dot coordinates and a mask of points that are on the canvas."""
        ...

    def inverse(self, x: FloatArray, y: FloatArray) -> tuple[FloatArray, FloatArray, BoolArray]:
        """Return (alt, az) for dot coordinates and a validity mask."""
        ...

    def degrees_per_dot(self) -> float: ...


@dataclass
class FullSky:
    """Azimuthal equidistant projection: zenith in the centre, horizon a circle.

    North is up and east is on the *left*, as when lying on your back with
    your head to the north. ``min_alt`` lets the circle include a bit of the
    sky below the horizon.
    """

    width: int
    height: int
    min_alt: float = 0.0
    margin: int = 2

    @property
    def cx(self) -> float:
        return (self.width - 1) / 2.0

    @property
    def cy(self) -> float:
        return (self.height - 1) / 2.0

    @property
    def radius(self) -> float:
        return max(1.0, min(self.width, self.height) / 2.0 - self.margin)

    def _r(self, alt: FloatArray) -> FloatArray:
        return (90.0 - alt) / (90.0 - self.min_alt) * self.radius

    def forward(self, alt: FloatArray, az: FloatArray) -> tuple[FloatArray, FloatArray, BoolArray]:
        alt = np.asarray(alt, dtype=np.float64)
        az = np.radians(np.asarray(az, dtype=np.float64))
        r = self._r(alt)
        x = self.cx - r * np.sin(az)
        y = self.cy - r * np.cos(az)
        ok = (alt >= self.min_alt) & (x >= 0) & (x < self.width) & (y >= 0) & (y < self.height)
        return x, y, ok

    def inverse(self, x: FloatArray, y: FloatArray) -> tuple[FloatArray, FloatArray, BoolArray]:
        dx = np.asarray(x, dtype=np.float64) - self.cx
        dy = np.asarray(y, dtype=np.float64) - self.cy
        r = np.hypot(dx, dy)
        alt = 90.0 - r / self.radius * (90.0 - self.min_alt)
        az = np.degrees(np.arctan2(-dx, -dy)) % 360.0
        return alt, az, alt >= self.min_alt

    def degrees_per_dot(self) -> float:
        return (90.0 - self.min_alt) / self.radius


@dataclass
class Stereographic:
    """Stereographic view in one direction (looking outward, horizon below)."""

    width: int
    height: int
    center_az: float = 180.0
    center_alt: float = 30.0
    fov: float = 90.0

    def __post_init__(self) -> None:
        self.fov = float(np.clip(self.fov, 10.0, 200.0))
        self.center_alt = float(np.clip(self.center_alt, -30.0, 90.0))
        a = np.radians(self.center_az)
        self._c0 = altaz_to_nev(self.center_alt, self.center_az)
        right = np.array([-np.sin(a), np.cos(a), 0.0])
        self._up = np.cross(self._c0, right)
        self._up /= np.linalg.norm(self._up)
        self._right = np.cross(self._up, self._c0)
        self._scale = (self.width / 2.0) / (2.0 * np.tan(np.radians(self.fov) / 4.0))

    def forward(self, alt: FloatArray, az: FloatArray) -> tuple[FloatArray, FloatArray, BoolArray]:
        p = altaz_to_nev(alt, az)
        z = p @ self._c0
        denom = np.maximum(1.0 + z, 1e-9)
        sx = 2.0 * (p @ self._right) / denom
        sy = 2.0 * (p @ self._up) / denom
        x = (self.width - 1) / 2.0 + self._scale * sx
        y = (self.height - 1) / 2.0 - self._scale * sy
        ok = (z > -0.5) & (x >= 0) & (x < self.width) & (y >= 0) & (y < self.height)
        return x, y, ok

    def inverse(self, x: FloatArray, y: FloatArray) -> tuple[FloatArray, FloatArray, BoolArray]:
        sx = (np.asarray(x, dtype=np.float64) - (self.width - 1) / 2.0) / self._scale
        sy = ((self.height - 1) / 2.0 - np.asarray(y, dtype=np.float64)) / self._scale
        rho2 = sx * sx + sy * sy
        k = 4.0 / (4.0 + rho2)
        z = (4.0 - rho2) / (4.0 + rho2)
        p = (
            (k * sx)[..., None] * self._right
            + (k * sy)[..., None] * self._up
            + z[..., None] * self._c0
        )
        alt, az = nev_to_altaz(p)
        return alt, az, np.ones_like(alt, dtype=bool)

    def degrees_per_dot(self) -> float:
        return self.fov / self.width


@dataclass
class Panorama:
    """Cylindrical "view from the window": horizon at the bottom.

    ``x`` is linear in azimuth around ``center_az``, ``y`` linear in altitude.
    ``bottom_alt`` is the altitude at the bottom edge of the canvas (slightly
    negative so that the horizon and the roofs are visible).
    """

    width: int
    height: int
    center_az: float = 180.0
    fov: float = 120.0
    bottom_alt: float = -6.0

    def __post_init__(self) -> None:
        self.fov = float(np.clip(self.fov, 30.0, 360.0))

    def degrees_per_dot(self) -> float:
        return self.fov / self.width

    @property
    def top_alt(self) -> float:
        return self.bottom_alt + self.height * self.degrees_per_dot()

    def forward(self, alt: FloatArray, az: FloatArray) -> tuple[FloatArray, FloatArray, BoolArray]:
        d = self.degrees_per_dot()
        dx = wrap180(np.asarray(az, dtype=np.float64) - self.center_az)
        x = (self.width - 1) / 2.0 + dx / d
        y = (self.height - 1) - (np.asarray(alt, dtype=np.float64) - self.bottom_alt) / d
        ok = (x >= 0) & (x < self.width) & (y >= 0) & (y < self.height)
        return x, y, ok

    def inverse(self, x: FloatArray, y: FloatArray) -> tuple[FloatArray, FloatArray, BoolArray]:
        d = self.degrees_per_dot()
        az = (self.center_az + (np.asarray(x, dtype=np.float64) - (self.width - 1) / 2.0) * d) % 360
        alt = self.bottom_alt + ((self.height - 1) - np.asarray(y, dtype=np.float64)) * d
        return alt, az, alt <= 90.0

    def y_of_alt(self, alt: float) -> float:
        return (self.height - 1) - (alt - self.bottom_alt) / self.degrees_per_dot()

    def x_of_az(self, az: float) -> float:
        return (self.width - 1) / 2.0 + float(wrap180(az - self.center_az)) / self.degrees_per_dot()
