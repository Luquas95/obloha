"""Ephemeris and timescale loading (fully offline).

DE421 comes from the ``skyfield-data`` wheel, the timescale uses Skyfield's
built-in Delta T and leap second tables, so nothing is downloaded.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from importlib import resources
from typing import Any

from skyfield.api import Timescale, load, load_constellation_map, load_file

#: Supported time range (DE421 covers 1899-07-29 .. 2053-10-08).
MIN_DATE = datetime(1900, 1, 1, tzinfo=UTC)
MAX_DATE = datetime(2050, 1, 1, tzinfo=UTC)


class OutOfRangeError(ValueError):
    """Raised when a time lies outside of the DE421 range we support."""


def de421_path() -> str:
    """Return the filesystem path of the bundled DE421 kernel."""
    return str(resources.files("skyfield_data") / "data" / "de421.bsp")


@lru_cache(maxsize=1)
def ephemeris() -> Any:
    """Load the DE421 planetary ephemeris."""
    return load_file(de421_path())


@lru_cache(maxsize=1)
def timescale() -> Timescale:
    """Return a timescale built from Skyfield's bundled tables."""
    # builtin=True reads only tables shipped inside the skyfield package; the
    # module-level ``load`` (directory ".") never creates or writes files here
    return load.timescale(builtin=True)


@lru_cache(maxsize=1)
def constellation_map() -> Any:
    """Return Skyfield's IAU constellation lookup function."""
    return load_constellation_map()


def check_range(when: datetime) -> datetime:
    """Return ``when`` if it is inside the supported range, else raise."""
    if when.tzinfo is None:
        raise ValueError("datetime must be timezone aware")
    if not MIN_DATE <= when < MAX_DATE:
        raise OutOfRangeError(f"Čas {when:%Y-%m-%d} je mimo rozsah efemeridy DE421 (1900–2049).")
    return when


def ts_from_datetime(when: datetime) -> Any:
    """Convert an aware datetime to a Skyfield ``Time``."""
    return timescale().from_datetime(check_range(when).astimezone(UTC))


def to_datetime(t: Any) -> datetime:
    """Convert a scalar Skyfield ``Time`` to an aware UTC datetime (whole seconds)."""
    result: datetime = t.utc_datetime().replace(microsecond=0)
    return result
