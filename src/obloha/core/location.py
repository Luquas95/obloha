"""Observer location."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import Any
from zoneinfo import ZoneInfo

from skyfield.api import wgs84

from obloha.core.ephem import ephemeris


@dataclass(frozen=True)
class Location:
    """A place on Earth from which the sky is observed."""

    name: str
    lat: float
    lon: float
    elevation: float = 0.0
    tz: str = "UTC"
    label: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        if not -90.0 <= self.lat <= 90.0:
            raise ValueError(f"neplatná zeměpisná šířka {self.lat}")
        if not -180.0 <= self.lon <= 180.0:
            raise ValueError(f"neplatná zeměpisná délka {self.lon}")
        ZoneInfo(self.tz)  # validate

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    @cached_property
    def topos(self) -> Any:
        """Skyfield geographic position."""
        return wgs84.latlon(self.lat, self.lon, elevation_m=self.elevation)

    @cached_property
    def observer(self) -> Any:
        """Skyfield vector sum earth + topos (for ``observe``)."""
        return ephemeris()["earth"] + self.topos

    def coords_text(self) -> str:
        """Human readable coordinates, e.g. ``50,08° N  14,44° E``."""
        ns = "N" if self.lat >= 0 else "S"
        ew = "E" if self.lon >= 0 else "W"
        lat = f"{abs(self.lat):.2f}".replace(".", ",")
        lon = f"{abs(self.lon):.2f}".replace(".", ",")
        return f"{lat}° {ns}  {lon}° {ew}"


PRAGUE = Location("Praha", 50.0755, 14.4378, 235.0, "Europe/Prague")
