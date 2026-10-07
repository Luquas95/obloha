"""Uniform information about any selectable object (star, body, DSO, …)."""

from __future__ import annotations

from dataclasses import dataclass

from obloha.core.coords import vec_to_radec
from obloha.core.ephem import constellation_map
from obloha.core.sky import ObjectRef, SkyScene

KIND_CS = {
    "star": "hvězda",
    "planet": "planeta",
    "moon": "Měsíc",
    "sun": "hvězda (Slunce)",
    "dso": "objekt",
    "sat": "družice",
    "asterism": "obrazec",
    "constellation": "souhvězdí",
}

#: approximate B−V of planets (for colour words)
PLANET_BV = {
    "mercury": 0.9,
    "venus": 0.8,
    "mars": 1.4,
    "jupiter": 0.85,
    "saturn": 0.95,
    "uranus": 0.55,
    "neptune": 0.4,
    "moon": 0.9,
    "sun": 0.65,
}

#: grammatical gender of names (True = feminine) for adjectives in descriptions
FEMININE_STARS = {"Vega", "Capella", "Spika", "Polárka", "Mira", "Gemma", "Alkyone"}


@dataclass(frozen=True)
class ObjectInfo:
    ref: ObjectRef
    name: str
    kind: str  # key of KIND_CS
    alt: float
    az: float
    ra: float
    dec: float
    mag: float | None
    bv: float | None
    constellation: str | None  # Czech name
    distance_au: float | None = None
    illumination: float | None = None
    text: str = ""

    @property
    def kind_cs(self) -> str:
        return KIND_CS.get(self.kind, self.kind)

    @property
    def is_planet(self) -> bool:
        return self.kind == "planet"

    @property
    def twinkles(self) -> bool:
        return self.kind == "star"


def _constellation_of(scene: SkyScene, ra: float, dec: float) -> str:
    from skyfield.api import position_of_radec

    abbr = str(constellation_map()(position_of_radec(ra / 15.0, dec)))
    return scene.cat.constellation_cs(abbr)


def object_info(scene: SkyScene, ref: ObjectRef) -> ObjectInfo | None:
    """Collect name, position and physical data of ``ref`` in ``scene``."""
    cat = scene.cat
    pos = scene.altaz_of(ref)
    if pos is None:
        return None
    alt, az = pos
    if ref.kind == "star":
        i = int(ref.key)
        con = cat.star_constellation(i)
        bv = float(cat.bv[i])
        return ObjectInfo(
            ref,
            cat.star_label(i),
            "star",
            alt,
            az,
            float(cat.ra[i]),
            float(cat.dec[i]),
            float(cat.mag[i]),
            None if bv != bv else bv,
            cat.constellation_cs(con) if con else _constellation_of(scene, cat.ra[i], cat.dec[i]),
        )
    if ref.kind == "body":
        b = scene.bodies[ref.key]
        return ObjectInfo(
            ref,
            b.name,
            b.info.kind,
            alt,
            az,
            b.ra,
            b.dec,
            b.mag,
            PLANET_BV.get(b.id),
            cat.constellation_cs(b.constellation),
            b.distance_au,
            b.illumination,
        )
    if ref.kind == "dso":
        d = next(d for d in cat.deep_sky if d.id == ref.key)
        return ObjectInfo(
            ref,
            d.name,
            "dso",
            alt,
            az,
            d.ra,
            d.dec,
            d.mag,
            None,
            _constellation_of(scene, d.ra, d.dec),
            text=d.text,
        )
    if ref.kind == "sat":
        s = next(s for s in scene.satellites if s.name == ref.key)
        return ObjectInfo(ref, s.name, "sat", alt, az, 0.0, 0.0, s.mag, None, None)
    if ref.kind == "asterism":
        a = next(a for a in cat.asterisms if a.id == ref.key)
        v = cat.vectors[list(a.stars)].mean(axis=0)
        ra, dec = vec_to_radec(v)
        return ObjectInfo(
            ref, a.name, "asterism", alt, az, float(ra), float(dec), None, None, None, text=a.text
        )
    if ref.kind == "constellation":
        c = cat.constellations[int(ref.key)]
        return ObjectInfo(
            ref,
            c.name_cs,
            "constellation",
            alt,
            az,
            c.ra,
            c.dec,
            None,
            None,
            c.name_cs,
            text=f"latinsky {c.name_la}",
        )
    return None


def is_feminine(info: ObjectInfo) -> bool:
    if info.kind == "body":
        return False
    if info.ref.kind == "body":
        return info.ref.key == "venus"
    return info.name in FEMININE_STARS
