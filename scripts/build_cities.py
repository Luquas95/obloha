#!/usr/bin/env python3
"""Build the offline city database ``src/obloha/data/cities.sqlite``.

Sources (fetched into ``scripts/_work``):

* Czech municipalities (all 6 2xx obcí, incl. district and region):
  npm package ``text-to-map`` (MIT), file ``dist/souradnice.csv``,
  derived from open data of ČSÚ / RÚIAN.
* Slovakia and the rest of the world: GeoNames gazetteer (CC BY 4.0) via the
  PyPI package ``geonamescache`` (MIT): Slovak places from ``cities500``,
  other countries from ``cities15000``. Time zones come from GeoNames.
* Region (admin1) names: npm package ``cities.json`` (CC BY 4.0, GeoNames).

Elevations are not part of any of these packages; the column stays NULL
(see docs/VERIFY.md).

Run: ``uv run python scripts/build_cities.py``
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import subprocess
import sys
import tarfile
import unicodedata
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "scripts" / "_work"
OUT = ROOT / "src" / "obloha" / "data" / "cities.sqlite"

COUNTRY_CS = {
    "CZ": "Česko",
    "SK": "Slovensko",
    "DE": "Německo",
    "AT": "Rakousko",
    "PL": "Polsko",
    "HU": "Maďarsko",
    "SI": "Slovinsko",
    "HR": "Chorvatsko",
    "IT": "Itálie",
    "FR": "Francie",
    "ES": "Španělsko",
    "PT": "Portugalsko",
    "GB": "Spojené království",
    "IE": "Irsko",
    "NL": "Nizozemsko",
    "BE": "Belgie",
    "LU": "Lucembursko",
    "CH": "Švýcarsko",
    "DK": "Dánsko",
    "NO": "Norsko",
    "SE": "Švédsko",
    "FI": "Finsko",
    "IS": "Island",
    "EE": "Estonsko",
    "LV": "Lotyšsko",
    "LT": "Litva",
    "UA": "Ukrajina",
    "BY": "Bělorusko",
    "RU": "Rusko",
    "RO": "Rumunsko",
    "BG": "Bulharsko",
    "RS": "Srbsko",
    "BA": "Bosna a Hercegovina",
    "ME": "Černá Hora",
    "MK": "Severní Makedonie",
    "AL": "Albánie",
    "GR": "Řecko",
    "TR": "Turecko",
    "CY": "Kypr",
    "MT": "Malta",
    "US": "USA",
    "CA": "Kanada",
    "MX": "Mexiko",
    "BR": "Brazílie",
    "AR": "Argentina",
    "CL": "Chile",
    "PE": "Peru",
    "CO": "Kolumbie",
    "AU": "Austrálie",
    "NZ": "Nový Zéland",
    "JP": "Japonsko",
    "CN": "Čína",
    "KR": "Jižní Korea",
    "IN": "Indie",
    "ID": "Indonésie",
    "TH": "Thajsko",
    "VN": "Vietnam",
    "EG": "Egypt",
    "MA": "Maroko",
    "TN": "Tunisko",
    "ZA": "Jižní Afrika",
    "KE": "Keňa",
    "IL": "Izrael",
    "AE": "Spojené arabské emiráty",
    "SA": "Saúdská Arábie",
    "IR": "Írán",
    "NA": "Namibie",
    "MD": "Moldavsko",
    "GE": "Gruzie",
    "AM": "Arménie",
}

#: Czech exonyms of foreign cities (GeoNames name, country) -> Czech names.
EXONYMS = {
    ("Vienna", "AT"): ["Vídeň", "Wien"],
    ("Munich", "DE"): ["Mnichov", "München"],
    ("Dresden", "DE"): ["Drážďany"],
    ("Berlin", "DE"): ["Berlín"],
    ("Leipzig", "DE"): ["Lipsko"],
    ("Nuremberg", "DE"): ["Norimberk", "Nürnberg"],
    ("Regensburg", "DE"): ["Řezno"],
    ("Passau", "DE"): ["Pasov"],
    ("Cologne", "DE"): ["Kolín nad Rýnem", "Köln"],
    ("Aachen", "DE"): ["Cáchy"],
    ("Frankfurt am Main", "DE"): ["Frankfurt nad Mohanem"],
    ("Mainz", "DE"): ["Mohuč"],
    ("Hamburg", "DE"): ["Hamburk"],
    ("Linz", "AT"): ["Linec"],
    ("Graz", "AT"): ["Štýrský Hradec"],
    ("Salzburg", "AT"): ["Solnohrad"],
    ("Rome", "IT"): ["Řím", "Roma"],
    ("Venice", "IT"): ["Benátky", "Venezia"],
    ("Naples", "IT"): ["Neapol", "Napoli"],
    ("Milan", "IT"): ["Milán", "Milano"],
    ("Turin", "IT"): ["Turín", "Torino"],
    ("Florence", "IT"): ["Florencie", "Firenze"],
    ("Genoa", "IT"): ["Janov", "Genova"],
    ("Trieste", "IT"): ["Terst"],
    ("Paris", "FR"): ["Paříž"],
    ("London", "GB"): ["Londýn"],
    ("Warsaw", "PL"): ["Varšava", "Warszawa"],
    ("Kraków", "PL"): ["Krakov"],
    ("Wrocław", "PL"): ["Vratislav"],
    ("Ljubljana", "SI"): ["Lublaň"],
    ("Zagreb", "HR"): ["Záhřeb"],
    ("Belgrade", "RS"): ["Bělehrad"],
    ("Budapest", "HU"): ["Budapešť"],
    ("Copenhagen", "DK"): ["Kodaň", "København"],
    ("Brussels", "BE"): ["Brusel"],
    ("Lisbon", "PT"): ["Lisabon"],
    ("Moscow", "RU"): ["Moskva"],
    ("Kyiv", "UA"): ["Kyjev"],
    ("Athens", "GR"): ["Athény"],
    ("Geneva", "CH"): ["Ženeva"],
    ("Zürich", "CH"): ["Curych"],
    ("Bern", "CH"): ["Bern"],
    ("Stockholm", "SE"): ["Stockholm"],
    ("Bucharest", "RO"): ["Bukurešť"],
    ("Sofia", "BG"): ["Sofie"],
    ("Istanbul", "TR"): ["Istanbul"],
    ("New York City", "US"): ["New York"],
    ("Beijing", "CN"): ["Peking"],
    ("Cairo", "EG"): ["Káhira"],
    ("Jerusalem", "IL"): ["Jeruzalém"],
    ("Bratislava", "SK"): ["Prešpurk"],
    ("Košice", "SK"): ["Košice"],
}


def fold(text: str) -> str:
    d = unicodedata.normalize("NFKD", text)
    s = "".join(c for c in d if not unicodedata.combining(c))
    return " ".join(s.casefold().replace("-", " ").split())


def npm_pack(name: str) -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    out = subprocess.run(
        ["npm", "pack", name, "--silent"], cwd=WORK, check=True, capture_output=True, text=True
    )
    tgz = WORK / out.stdout.strip().splitlines()[-1]
    dest = WORK / name
    with tarfile.open(tgz) as tar:
        tar.extractall(dest, filter="data")
    return dest / "package"


def geonamescache_data() -> Path:
    dest = WORK / "geonamescache"
    if not (dest / "geonamescache" / "data" / "cities500.json").exists():
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--no-deps",
                "geonamescache==3.0.2",
                "-d",
                str(WORK),
            ],
            check=True,
        )
        whl = next(WORK.glob("geonamescache-*.whl"))
        with zipfile.ZipFile(whl) as zf:
            zf.extractall(dest)
    return dest / "geonamescache" / "data"


SMALL_WORDS = {"nad", "pod", "u", "v", "ve", "na", "při", "pri"}


def czech_title(name: str) -> str:
    """``ČESKÉ BUDĚJOVICE`` -> ``České Budějovice``, ``ÚSTÍ NAD LABEM`` -> ``Ústí nad Labem``."""
    if not name.isupper():
        return name
    words = []
    for i, w in enumerate(name.lower().split(" ")):
        parts = [p.capitalize() for p in w.split("-")]
        words.append(w if i > 0 and w in SMALL_WORDS else "-".join(parts))
    return " ".join(words)


def is_latin(text: str) -> bool:
    return all(ord(c) < 0x250 or unicodedata.combining(c) for c in text)


def main() -> None:
    ttm = npm_pack("text-to-map")
    cj = npm_pack("cities.json")
    gdata = geonamescache_data()
    admin1 = {a["code"]: a["name"] for a in json.loads((cj / "admin1.json").read_text())}

    rows: list[tuple] = []
    alts: list[tuple[int, str]] = []
    text = (ttm / "dist" / "souradnice.csv").read_text(encoding="utf-8")
    for r in csv.DictReader(io.StringIO(text)):
        rows.append(
            (
                czech_title(r["Obec"]),
                "CZ",
                r["Kraj"],
                f"okr. {r['Okres']}",
                float(r["Latitude"]),
                float(r["Longitude"]),
                None,
                "Europe/Prague",
                0,
            )
        )
    n_cz = len(rows)

    def add_geonames(entry: dict, district: str = "") -> None:
        idx = len(rows)
        cc = entry["countrycode"]
        region = admin1.get(f"{cc}.{entry.get('admin1code', '')}", "")
        exo = EXONYMS.get((entry["name"], cc))
        display = exo[0] if exo else entry["name"]
        if exo:
            alts.append((idx, fold(entry["name"])))
        rows.append(
            (
                display,
                cc,
                region,
                district,
                float(entry["latitude"]),
                float(entry["longitude"]),
                None,
                entry["timezone"],
                int(entry.get("population") or 0),
            )
        )
        seen = {fold(entry["name"])}
        pop = int(entry.get("population") or 0)
        limit = 40 if pop >= 500_000 else 12 if pop >= 100_000 else 4
        for alt in entry.get("alternatenames", []):
            if not is_latin(alt) or len(alt) > 30:
                continue
            f = fold(alt)
            if f and f not in seen:
                seen.add(f)
                alts.append((idx, f))
            if len(seen) > limit:
                break
        for exo in EXONYMS.get((entry["name"], cc), ()):
            alts.append((idx, fold(exo)))

    big = json.loads((gdata / "cities15000.json").read_text())
    for e in big.values():
        if e["countrycode"] not in ("CZ", "SK"):
            add_geonames(e)
    small = json.loads((gdata / "cities500.json").read_text())
    for e in small.values():
        if e["countrycode"] == "SK":
            add_geonames(e)
    # Population and English names of Czech towns (Prague, Pilsen...) from GeoNames,
    # matched by any of the GeoNames names and distance.
    cz_index: dict[str, list[int]] = {}
    for i in range(n_cz):
        cz_index.setdefault(fold(rows[i][0]), []).append(i)
    for e in small.values():
        if e["countrycode"] != "CZ":
            continue
        names_f = {fold(e["name"])} | {fold(a) for a in e.get("alternatenames", []) if is_latin(a)}
        cands = [i for f in names_f for i in cz_index.get(f, [])]
        best = None
        for i in cands:
            d = abs(rows[i][4] - e["latitude"]) + abs(rows[i][5] - e["longitude"])
            if d < 0.15 and (best is None or d < best[0]):
                best = (d, i)
        if best is None:
            continue
        i = best[1]
        if int(e["population"]) > rows[i][8]:
            rows[i] = (*rows[i][:8], int(e["population"]))
        if e["population"] >= 15000:
            for f in sorted(names_f)[:20]:
                if f != fold(rows[i][0]):
                    alts.append((i, f))

    OUT.unlink(missing_ok=True)
    db = sqlite3.connect(OUT)
    db.executescript(
        """
        CREATE TABLE place (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, fold TEXT NOT NULL,
            country TEXT NOT NULL, region TEXT, district TEXT,
            lat REAL NOT NULL, lon REAL NOT NULL, elevation REAL, tz TEXT NOT NULL,
            population INTEGER NOT NULL
        );
        CREATE TABLE alt (place INTEGER NOT NULL, fold TEXT NOT NULL);
        CREATE TABLE country (code TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        """
    )
    db.executemany(
        "INSERT INTO place VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                i,
                r[0],
                fold(r[0]),
                r[1],
                r[2],
                r[3],
                round(r[4], 5),
                round(r[5], 5),
                r[6],
                r[7],
                r[8],
            )
            for i, r in enumerate(rows)
        ],
    )
    db.executemany("INSERT INTO alt VALUES (?,?)", sorted(set(alts)))
    countries = json.loads((gdata / "countries.json").read_text())
    names = {c["iso"]: c["name"] for c in countries.values()}
    names.update(COUNTRY_CS)
    db.executemany("INSERT INTO country VALUES (?,?)", sorted(names.items()))
    db.executemany(
        "INSERT INTO meta VALUES (?,?)",
        [
            (
                "sources",
                "text-to-map (ČSÚ/RÚIAN), GeoNames CC BY 4.0 via geonamescache, cities.json",
            ),
        ],
    )
    db.execute("CREATE INDEX place_fold ON place(fold)")
    db.execute("CREATE INDEX alt_fold ON alt(fold)")
    db.commit()
    db.execute("VACUUM")
    db.close()
    print(
        f"wrote {OUT}: {len(rows)} places ({n_cz} CZ), {len(set(alts))} alt names, "
        f"{OUT.stat().st_size / 1e6:.1f} MB"
    )


if __name__ == "__main__":
    main()
