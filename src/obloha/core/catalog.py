"""Star catalog, constellations, asterisms and deep-sky objects."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property, lru_cache
from importlib import resources
from typing import Any

import numpy as np
from numpy.typing import NDArray

from obloha.core.coords import radec_to_vec
from obloha.core.textnorm import fold

GREEK = {
    "α": "alfa",
    "β": "beta",
    "γ": "gama",
    "δ": "delta",
    "ε": "epsilon",
    "ζ": "zéta",
    "η": "éta",
    "θ": "théta",
    "ι": "ióta",
    "κ": "kappa",
    "λ": "lambda",
    "μ": "mí",
    "ν": "ný",
    "ξ": "ksí",
    "ο": "omikron",
    "π": "pí",
    "ρ": "ró",
    "σ": "sigma",
    "τ": "tau",
    "υ": "ypsilon",
    "φ": "fí",
    "χ": "chí",
    "ψ": "psí",
    "ω": "omega",
}


@dataclass(frozen=True)
class Constellation:
    index: int
    abbr: str
    name_cs: str
    name_la: str
    name_en: str
    genitive: str
    rank: int
    ra: float
    dec: float


@dataclass(frozen=True)
class Asterism:
    id: str
    name: str
    stars: tuple[int, ...]
    lines: tuple[tuple[int, int], ...]
    text: str


@dataclass(frozen=True)
class DeepSky:
    id: str
    name: str
    name_en: str
    ra: float
    dec: float
    mag: float
    kind: str
    text: str


def _data_file(name: str) -> Any:
    return resources.files("obloha.data") / name


class Catalog:
    """Loaded star catalog with Czech names."""

    def __init__(self) -> None:
        with _data_file("catalog.npz").open("rb") as fh:
            npz = np.load(fh)
            arrays = {k: npz[k] for k in npz.files}
        self.hip: NDArray[np.int32] = arrays["star_hip"]
        self.ra: NDArray[np.float64] = arrays["star_ra"].astype(np.float64)
        self.dec: NDArray[np.float64] = arrays["star_dec"].astype(np.float64)
        self.mag: NDArray[np.float32] = arrays["star_mag"]
        self.bv: NDArray[np.float32] = arrays["star_bv"]
        self.line_a: NDArray[np.int32] = arrays["line_a"]
        self.line_b: NDArray[np.int32] = arrays["line_b"]
        self.line_con: NDArray[np.int16] = arrays["line_con"]
        self.border_pts: NDArray[np.float32] = arrays["border_pts"]
        self.border_off: NDArray[np.int32] = arrays["border_off"]
        self.mw_ra: NDArray[np.float32] = arrays["mw_ra"]
        self.mw_dec: NDArray[np.float32] = arrays["mw_dec"]
        self.mw_level: NDArray[np.uint8] = arrays["mw_level"]
        with _data_file("catalog.json").open("r", encoding="utf-8") as fh:
            meta = json.load(fh)
        with _data_file("names_cs.json").open("r", encoding="utf-8") as fh:
            cs = json.load(fh)
        self.star_meta: dict[int, dict[str, str]] = {int(k): v for k, v in meta["stars"].items()}
        self._hip_index = {int(h): i for i, h in enumerate(self.hip)}
        self._en_index = {v["name"]: i for i, v in self.star_meta.items() if v.get("name")}
        self.cs_star_names: dict[int, str] = {}
        for key, value in cs["stars"].items():
            idx = self.star_by_key(key)
            if idx is not None:
                self.cs_star_names[idx] = value
        self.constellations: list[Constellation] = [
            Constellation(
                index=i,
                abbr=c["abbr"],
                name_cs=cs["constellations"].get(c["abbr"][:3], c["la"]),
                name_la=c["la"],
                name_en=c["en"],
                genitive=c["gen"],
                rank=c["rank"],
                ra=c["ra"],
                dec=c["dec"],
            )
            for i, c in enumerate(meta["constellations"])
        ]
        self._con_by_abbr = {c.abbr: c for c in self.constellations}
        self.asterisms: list[Asterism] = []
        for a in cs["asterisms"]:
            members = [self.star_by_key(k) for k in a["stars"]]
            if any(i is None for i in members):
                continue
            self.asterisms.append(
                Asterism(
                    id=a["id"],
                    name=a["name"],
                    stars=tuple(int(i) for i in members if i is not None),
                    lines=tuple((int(p[0]), int(p[1])) for p in a["lines"]),
                    text=a["text"],
                )
            )
        self.deep_sky: list[DeepSky] = [
            DeepSky(d["id"], d["name"], d["en"], d["ra"], d["dec"], d["mag"], d["kind"], d["text"])
            for d in cs["deep_sky"]
        ]
        self.cs_constellation_table: dict[str, str] = cs["constellations"]

    def __len__(self) -> int:
        return len(self.hip)

    @cached_property
    def vectors(self) -> NDArray[np.float64]:
        """ICRS unit vectors of all stars (N, 3)."""
        return radec_to_vec(self.ra, self.dec)

    @cached_property
    def mw_vectors(self) -> NDArray[np.float64]:
        return radec_to_vec(self.mw_ra.astype(np.float64), self.mw_dec.astype(np.float64))

    @cached_property
    def border_vectors(self) -> NDArray[np.float64]:
        pts = self.border_pts.astype(np.float64)
        return radec_to_vec(pts[:, 0], pts[:, 1])

    def star_by_key(self, key: str) -> int | None:
        """Look up a star by English proper name or ``HIP:<n>``."""
        if key.startswith("HIP:"):
            return self._hip_index.get(int(key[4:]))
        return self._en_index.get(key)

    def star_by_hip(self, hip: int) -> int | None:
        return self._hip_index.get(hip)

    def constellation(self, abbr: str) -> Constellation | None:
        return self._con_by_abbr.get(abbr)

    def constellation_cs(self, abbr: str) -> str:
        """Czech constellation name for an IAU abbreviation."""
        c = self.cs_constellation_table.get(abbr)
        return c if c is not None else abbr

    def star_name(self, i: int) -> str | None:
        """Czech (or proper) name of a star, ``None`` for unnamed stars."""
        if i in self.cs_star_names:
            return self.cs_star_names[i]
        meta = self.star_meta.get(i, {})
        return meta.get("name") or None

    def star_designation(self, i: int) -> str:
        """Bayer/Flamsteed designation like ``α Lyr`` or ``HIP 91262``."""
        meta = self.star_meta.get(i, {})
        con = meta.get("con", "")
        if meta.get("bayer"):
            return f"{meta['bayer']} {con}".strip()
        if meta.get("flam"):
            return f"{meta['flam']} {con}".strip()
        return f"HIP {int(self.hip[i])}"

    def star_label(self, i: int) -> str:
        return self.star_name(i) or self.star_designation(i)

    def star_constellation(self, i: int) -> str | None:
        con = self.star_meta.get(i, {}).get("con")
        return con or None

    @cached_property
    def named_stars(self) -> list[int]:
        """Indices of stars with a proper name, brightest first."""
        idx = [i for i in range(len(self)) if self.star_name(i)]
        return sorted(idx, key=lambda i: float(self.mag[i]))

    @cached_property
    def search_index(self) -> list[tuple[str, str, int]]:
        """(folded text, kind, index) entries for star/constellation search."""
        out: list[tuple[str, str, int]] = []
        for i in self.named_stars:
            out.append((fold(self.star_label(i)), "star", i))
            en = self.star_meta.get(i, {}).get("name")
            if en and fold(en) != fold(self.star_label(i)):
                out.append((fold(en), "star", i))
        for c in self.constellations:
            for name in {c.name_cs, c.name_la, c.name_en}:
                out.append((fold(name), "constellation", c.index))
        for k, d in enumerate(self.deep_sky):
            for name in {d.name, d.name_en, d.id}:
                out.append((fold(name), "deepsky", k))
        return out


@lru_cache(maxsize=1)
def catalog() -> Catalog:
    """Shared catalog instance."""
    return Catalog()
