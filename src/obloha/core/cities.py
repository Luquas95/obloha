"""Offline city search (diacritics-insensitive, typo tolerant)."""

from __future__ import annotations

import bisect
import math
import re
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from obloha.core.location import Location
from obloha.core.textnorm import fold, levenshtein


@dataclass(frozen=True)
class City:
    id: int
    name: str
    country: str
    country_name: str
    region: str
    district: str
    lat: float
    lon: float
    elevation: float | None
    tz: str
    population: int

    @property
    def detail(self) -> str:
        """Disambiguation like ``okr. Kladno`` or ``Wien, Rakousko``."""
        if self.country == "CZ":
            return self.district or self.region
        parts = [p for p in (self.region, self.country_name) if p and p != self.name]
        return ", ".join(parts)

    @property
    def label(self) -> str:
        d = self.detail
        return f"{self.name}, {d}" if d else self.name

    def to_location(self) -> Location:
        return Location(self.name, self.lat, self.lon, self.elevation or 0.0, self.tz, self.detail)


class CityDB:
    """In-memory index over ``cities.sqlite``."""

    def __init__(self) -> None:
        path = resources.files("obloha.data") / "cities.sqlite"
        with resources.as_file(path) as p:
            db = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            countries = dict(db.execute("SELECT code, name FROM country"))
            self.cities: list[City] = [
                City(i, n, c, countries.get(c, c), r or "", d or "", la, lo, e, tz, pop)
                for i, n, c, r, d, la, lo, e, tz, pop in db.execute(
                    "SELECT id, name, country, region, district, lat, lon, elevation, tz,"
                    " population FROM place ORDER BY id"
                )
            ]
            folds = list(db.execute("SELECT id, fold FROM place ORDER BY id"))
            alts = list(db.execute("SELECT place, fold FROM alt"))
            db.close()
        self.keys: dict[str, list[int]] = {}
        for i, f in folds:
            self.keys.setdefault(f, []).append(i)
        for i, f in alts:
            ids = self.keys.setdefault(f, [])
            if i not in ids:
                ids.append(i)
        self.sorted_keys = sorted(self.keys)
        self.by_length: dict[int, list[str]] = {}
        for k in self.sorted_keys:
            self.by_length.setdefault(len(k), []).append(k)

    def __len__(self) -> int:
        return len(self.cities)

    def _rank(self, city: City) -> tuple[int, int]:
        home = 0 if city.country in ("CZ", "SK") else 1
        return (-city.population, home)

    def search(self, query: str, limit: int = 10) -> list[City]:
        """Search by name; exact > prefix > word prefix > typo matches."""
        q = fold(query)
        if not q:
            return []
        scored: dict[int, tuple[int, int, int]] = {}

        def add(ids: list[int], level: int) -> None:
            for i in ids:
                c = self.cities[i]
                key = (level, *self._rank(c))
                if i not in scored or key < scored[i]:
                    scored[i] = key

        for i in self.keys.get(q, []):
            c = self.cities[i]
            weight = max(c.population, 1) * (3 if fold(c.name) == q else 1)
            weight *= 20 if c.country in ("CZ", "SK") else 1
            scored[i] = (0, -weight, 0)
        lo = bisect.bisect_left(self.sorted_keys, q)
        for k in self.sorted_keys[lo:]:
            if not k.startswith(q):
                break
            add(self.keys[k], 2)
        words = q.split()
        if len(scored) < limit:
            for k, ids in self.keys.items():
                kw = k.split()
                if len(kw) > 1 and all(any(w2.startswith(w) for w2 in kw) for w in words):
                    add(ids, 3)
        if len(scored) < 3 and len(q) >= 3:
            max_d = 1 if len(q) <= 5 else 2
            for length in range(len(q) - max_d, len(q) + max_d + 1):
                for k in self.by_length.get(length, ()):
                    if k[0] != q[0] and k[-1] != q[-1]:
                        continue
                    d = levenshtein(q, k, max_d)
                    if d <= max_d:
                        add(self.keys[k], 3 + d)
        best = sorted(scored.items(), key=lambda kv: kv[1])
        return [self.cities[i] for i, _ in best[:limit]]

    def nearest(self, lat: float, lon: float) -> City:
        """Nearest place (great-circle distance)."""
        best: tuple[float, City] | None = None
        cl = math.cos(math.radians(lat))
        for c in self.cities:
            d = (c.lat - lat) ** 2 + ((c.lon - lon + 180) % 360 - 180) ** 2 * cl * cl
            if best is None or d < best[0]:
                best = (d, c)
        assert best is not None
        return best[1]

    def find(self, name: str, country: str | None = None) -> City | None:
        """Exact (folded) name lookup, most populous first."""
        for c in self.search(name, limit=30):
            if fold(c.name) == fold(name) and (country is None or c.country == country):
                return c
        return None


@lru_cache(maxsize=1)
def city_db() -> CityDB:
    return CityDB()


def timezone_at(lat: float, lon: float) -> str:
    """IANA time zone for coordinates (timezonefinder if installed, else nearest city)."""
    try:
        from timezonefinder import TimezoneFinder

        tz = TimezoneFinder().timezone_at(lat=lat, lng=lon)
        if tz:
            return str(tz)
    except ImportError:  # pragma: no cover - optional dependency
        pass
    return city_db().nearest(lat, lon).tz


_DMS = re.compile(
    r"""(?P<sign>[-+−])?\s*(?P<deg>\d+(?:[.,]\d+)?)\s*(?:°|d|\s)?\s*
        (?:(?P<min>\d+(?:[.,]\d+)?)\s*(?:['′]|m|\s)?\s*)?
        (?:(?P<sec>\d+(?:[.,]\d+)?)\s*(?:["″]|s)?\s*)?
        (?P<hem>[NSEWnsewSJVZ])?""",
    re.VERBOSE,
)


def _parse_one(text: str, is_lat: bool) -> float:
    m = _DMS.fullmatch(text.strip())
    if not m:
        raise ValueError(f"nerozumím souřadnici {text!r}")
    value = float(m["deg"].replace(",", "."))
    if m["min"]:
        value += float(m["min"].replace(",", ".")) / 60
    if m["sec"]:
        value += float(m["sec"].replace(",", ".")) / 3600
    hem = (m["hem"] or "").upper()
    negative = m["sign"] in ("-", "−")
    if (hem in ("S", "J") and is_lat) or (hem in ("W", "Z") and not is_lat):
        negative = not negative
    lat_letter = hem in ("N", "S", "J")
    lon_letter = hem in ("E", "W", "V", "Z")
    if (lat_letter and not is_lat) or (lon_letter and is_lat):
        raise ValueError(f"neočekávaná světová strana v {text!r}")
    value = -value if negative else value
    limit = 90 if is_lat else 180
    if abs(value) > limit:
        raise ValueError(f"souřadnice {value} je mimo rozsah ±{limit}°")
    return value


def parse_coordinates(text: str) -> tuple[float, float]:
    """Parse ``50.0755, 14.4378``, ``50°4'32"N 14°26'16"E`` or ``50 4.5 N 14 26 E``.

    Czech hemisphere letters work too: ``49,2 S 16,6 V`` (S = sever = north).
    """
    t = text.strip().replace(";", ",")
    # Czech style "49,2 S" uses S for north: normalise V/Z and S(ever)/J(ih)
    czech = bool(re.search(r"\d\s*[°'″\"]?\s*[SJ]\b.*\d\s*[°'″\"]?\s*[VZ]\b", t))
    if czech:
        t = re.sub(r"\bS\b", "N", t)
        t = re.sub(r"\bJ\b", "S", t)
        t = re.sub(r"\bV\b", "E", t)
        t = re.sub(r"\bZ\b", "W", t)
    m = re.match(r"^(.*?[NSns])\s*,?\s*(.*[EWew])$", t)
    if m:
        return _parse_one(m[1], True), _parse_one(m[2], False)
    if t.count(",") == 1 and not re.search(r"\d,\d", t):
        a, b = t.split(",")
    elif t.count(",") == 1:
        parts = t.split()
        if len(parts) != 2:
            raise ValueError(f"nerozumím souřadnicím {text!r}")
        a, b = parts
    elif "," in t:
        a, b = t.split(", ", 1) if ", " in t else t.split(",", 1)
    else:
        parts = t.split()
        if len(parts) != 2:
            raise ValueError(f"nerozumím souřadnicím {text!r}")
        a, b = parts
    return _parse_one(a, True), _parse_one(b, False)
