#!/usr/bin/env python3
"""Build the compact star catalog shipped in ``src/obloha/data``.

Source: the npm package ``d3-celestial`` (BSD-3-Clause, (c) Olaf Frohn).
The package is fetched with ``npm pack d3-celestial`` into ``scripts/_work``
(or taken from ``--source DIR`` pointing at an extracted ``package`` folder).

Outputs:

* ``catalog.npz`` - numeric arrays (stars, constellation lines as star index
  pairs, constellation borders as polylines, Milky Way sample points),
* ``catalog.json`` - star designations and constellation metadata.

Run: ``uv run python scripts/build_catalog.py``
"""

from __future__ import annotations

import argparse
import itertools
import json
import subprocess
import tarfile
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "src" / "obloha" / "data"
WORK = ROOT / "scripts" / "_work"
MATCH_TOLERANCE_DEG = 0.12


def fetch_package() -> Path:
    """Download and extract d3-celestial via ``npm pack``."""
    WORK.mkdir(parents=True, exist_ok=True)
    out = subprocess.run(
        ["npm", "pack", "d3-celestial", "--silent"],
        cwd=WORK,
        check=True,
        capture_output=True,
        text=True,
    )
    tgz = WORK / out.stdout.strip().splitlines()[-1]
    dest = WORK / "d3-celestial"
    with tarfile.open(tgz) as tar:
        tar.extractall(dest, filter="data")
    return dest / "package"


def load(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def ra_of(lon: float) -> float:
    return lon % 360.0


def unit(ra: np.ndarray, dec: np.ndarray) -> np.ndarray:
    r, d = np.radians(ra), np.radians(dec)
    return np.stack([np.cos(d) * np.cos(r), np.cos(d) * np.sin(r), np.sin(d)], axis=-1)


def parse_stars(features: list[dict[str, Any]]) -> dict[str, np.ndarray]:
    hip = np.array([int(f["id"]) for f in features], dtype=np.int32)
    ra = np.array([ra_of(f["geometry"]["coordinates"][0]) for f in features], dtype=np.float64)
    dec = np.array([f["geometry"]["coordinates"][1] for f in features], dtype=np.float64)
    mag = np.array([float(f["properties"]["mag"]) for f in features], dtype=np.float32)
    bv = np.array(
        [float(f["properties"]["bv"]) if f["properties"].get("bv") else np.nan for f in features],
        dtype=np.float32,
    )
    return {"hip": hip, "ra": ra, "dec": dec, "mag": mag, "bv": bv}


def build_lines(
    pkg: Path, stars: dict[str, np.ndarray], faint: dict[str, np.ndarray], abbrs: list[str]
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, np.ndarray]:
    """Convert constellation polylines into star index pairs.

    Vertices not found among stars <= 6 mag are taken from the 8 mag catalog
    and appended to the star arrays.
    """
    lines = load(pkg / "data" / "constellations.lines.json")["features"]
    vec = unit(stars["ra"], stars["dec"])
    fvec = unit(faint["ra"], faint["dec"])
    cos_tol = np.cos(np.radians(MATCH_TOLERANCE_DEG))
    extra: dict[int, int] = {}
    star_arrays = {k: list(v) for k, v in stars.items()}
    pairs_a: list[int] = []
    pairs_b: list[int] = []
    pairs_c: list[int] = []

    def find(lon: float, lat: float) -> int:
        v = unit(np.array([ra_of(lon)]), np.array([lat]))[0]
        dots = vec @ v
        i = int(np.argmax(dots))
        if dots[i] >= cos_tol:
            return i
        fd = fvec @ v
        j = int(np.argmax(fd))
        if fd[j] < cos_tol:
            raise ValueError(f"no star near line vertex {lon} {lat}")
        if j not in extra:
            extra[j] = len(star_arrays["hip"])
            for key in star_arrays:
                star_arrays[key].append(faint[key][j])
        return extra[j]

    for feat in lines:
        con = abbrs.index(feat["id"])
        for poly in feat["geometry"]["coordinates"]:
            idx = [find(p[0], p[1]) for p in poly]
            for a, b in itertools.pairwise(idx):
                if a != b:
                    pairs_a.append(a)
                    pairs_b.append(b)
                    pairs_c.append(con)
    merged = {
        "hip": np.array(star_arrays["hip"], dtype=np.int32),
        "ra": np.array(star_arrays["ra"], dtype=np.float64),
        "dec": np.array(star_arrays["dec"], dtype=np.float64),
        "mag": np.array(star_arrays["mag"], dtype=np.float32),
        "bv": np.array(star_arrays["bv"], dtype=np.float32),
    }
    print(f"  line vertices from 8 mag catalog: {len(extra)}")
    return (
        merged,
        np.array(pairs_a, dtype=np.int32),
        np.array(pairs_b, dtype=np.int32),
        np.array(pairs_c, dtype=np.int16),
    )


def build_borders(pkg: Path) -> tuple[np.ndarray, np.ndarray]:
    feats = load(pkg / "data" / "constellations.borders.json")["features"]
    pts: list[tuple[float, float]] = []
    offsets = [0]
    for feat in feats:
        for line in feat["geometry"]["coordinates"]:
            pts.extend((ra_of(p[0]), p[1]) for p in line)
            offsets.append(len(pts))
    return np.array(pts, dtype=np.float32), np.array(offsets, dtype=np.int32)


def _edges(rings: list[list[list[float]]]) -> np.ndarray:
    """Return edges (lon1, lat1, lon2, lat2) with the antimeridian jump unwrapped."""
    out = []
    for ring in rings:
        for a, b in itertools.pairwise(ring):
            lon1, lat1, lon2, lat2 = a[0], a[1], b[0], b[1]
            d = lon2 - lon1
            if d > 180:
                lon2 -= 360
            elif d < -180:
                lon2 += 360
            out.append((lon1, lat1, lon2, lat2))
    return np.array(out, dtype=np.float64)


def inside_grid(rings: list[list[list[float]]], lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """Even-odd test using vertical rays to the north pole (works for bands)."""
    e = _edges(rings)
    result = np.zeros((len(lats), len(lons)), dtype=bool)
    lo = np.minimum(e[:, 0], e[:, 2])
    hi = np.maximum(e[:, 0], e[:, 2])
    for j, lon in enumerate(lons):
        crossings = []
        for shift in (-360.0, 0.0, 360.0):
            x = lon + shift
            m = (lo <= x) & (x < hi)
            if not m.any():
                continue
            s = e[m]
            t = (x - s[:, 0]) / (s[:, 2] - s[:, 0])
            crossings.append(s[:, 1] + t * (s[:, 3] - s[:, 1]))
        if not crossings:
            continue
        c = np.sort(np.concatenate(crossings))
        above = len(c) - np.searchsorted(c, lats, side="right")
        result[:, j] = (above % 2) == 1
    return result


def build_milky_way(pkg: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    feats = load(pkg / "data" / "mw.json")["features"]
    lons = np.arange(-179.5, 180.0, 1.0)
    lats = np.arange(-89.5, 90.0, 1.0)
    level = np.zeros((len(lats), len(lons)), dtype=np.uint8)
    for feat in feats:
        lvl = int(feat["id"][2:])
        rings = [ring for poly in feat["geometry"]["coordinates"] for ring in poly]
        mask = inside_grid(rings, lons, lats)
        level[mask] = np.maximum(level[mask], lvl)
    ra_l, dec_l, lv_l = [], [], []
    for i, lat in enumerate(lats):
        step = max(1, round(1.0 / max(np.cos(np.radians(lat)), 1e-3)))
        for j in range(0, len(lons), step):
            if level[i, j]:
                ra_l.append(ra_of(lons[j]))
                dec_l.append(lat)
                lv_l.append(level[i, j])
    print(f"  milky way sample points: {len(ra_l)}")
    return (
        np.array(ra_l, dtype=np.float32),
        np.array(dec_l, dtype=np.float32),
        np.array(lv_l, dtype=np.uint8),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="extracted d3-celestial package dir")
    args = parser.parse_args()
    pkg = args.source or fetch_package()
    print(f"source: {pkg}")

    stars = parse_stars(load(pkg / "data" / "stars.6.json")["features"])
    faint = parse_stars(load(pkg / "data" / "stars.8.json")["features"])
    print(f"  stars <= 6 mag: {len(stars['hip'])}")
    cons = load(pkg / "data" / "constellations.json")["features"]
    abbrs = [c["id"] for c in cons]
    stars, la, lb, lc = build_lines(pkg, stars, faint, abbrs)
    border_pts, border_off = build_borders(pkg)
    mw_ra, mw_dec, mw_lv = build_milky_way(pkg)

    names = load(pkg / "data" / "starnames.json")
    star_meta: dict[str, dict[str, str]] = {}
    for i, hip in enumerate(stars["hip"]):
        n = names.get(str(int(hip)))
        if not n:
            continue
        entry = {
            k: v
            for k, v in {
                "name": n.get("name", ""),
                "bayer": n.get("bayer", ""),
                "flam": n.get("flam", ""),
                "con": n.get("c", ""),
            }.items()
            if v
        }
        if entry:
            star_meta[str(i)] = entry
    constellations = [
        {
            "abbr": c["id"],
            "en": c["properties"]["en"],
            "la": c["properties"]["name"],
            "gen": c["properties"].get("gen", ""),
            "rank": int(c["properties"].get("rank", 3)),
            "ra": ra_of(c["properties"]["display"][0]),
            "dec": c["properties"]["display"][1],
        }
        for c in cons
    ]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        DATA_DIR / "catalog.npz",
        star_hip=stars["hip"],
        star_ra=stars["ra"].astype(np.float32),
        star_dec=stars["dec"].astype(np.float32),
        star_mag=stars["mag"],
        star_bv=stars["bv"],
        line_a=la,
        line_b=lb,
        line_con=lc,
        border_pts=border_pts,
        border_off=border_off,
        mw_ra=mw_ra,
        mw_dec=mw_dec,
        mw_level=mw_lv,
    )
    with (DATA_DIR / "catalog.json").open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "source": "d3-celestial (BSD-3-Clause)",
                "stars": star_meta,
                "constellations": constellations,
            },
            fh,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    print(f"wrote {DATA_DIR / 'catalog.npz'} and catalog.json")


if __name__ == "__main__":
    main()
