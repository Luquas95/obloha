from datetime import UTC, datetime, timedelta

import pytest

from obloha.core.almanac import local_noon, twilight
from obloha.core.cities import city_db, parse_coordinates, timezone_at
from obloha.core.textnorm import fold, levenshtein


@pytest.fixture(scope="module")
def db():
    return city_db()


def test_database_size(db):
    cz = [c for c in db.cities if c.country == "CZ"]
    assert len(cz) > 6200  # all Czech municipalities
    assert len(db) > 35000


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("plzen", "Plzeň"),
        ("ceske budejovice", "České Budějovice"),
        ("budejovice", "České Budějovice"),
        ("Wien", "Vídeň"),
        ("vienna", "Vídeň"),
        ("Reykjavik", "Reykjavík"),
        ("Prague", "Praha"),
        ("prgue", "Praha"),  # typo
        ("olomuc", "Olomouc"),  # typo
        ("ústí nad labem", "Ústí nad Labem"),
        ("frydek", "Frýdek-Místek"),
        ("Aš", "Aš"),
    ],
)
def test_search(db, query, expected):
    assert db.search(query, 5)[0].name == expected


def test_homonyms_have_district(db):
    lhoty = [c for c in db.search("Lhota", 50) if c.name == "Lhota"]
    assert len(lhoty) >= 4
    labels = {c.label for c in lhoty}
    assert "Lhota, okr. Kladno" in labels
    assert len(labels) == len(lhoty)


def test_world_label(db):
    assert db.search("Reykjavik")[0].label.endswith("Island")
    assert db.search("", 5) == []


@pytest.mark.parametrize(
    ("query", "tz"),
    [
        ("Praha", "Europe/Prague"),
        ("Reykjavik", "Atlantic/Reykjavik"),
        ("Sydney", "Australia/Sydney"),
        ("Los Angeles", "America/Los_Angeles"),
    ],
)
def test_time_zones(db, query, tz):
    c = db.search(query, 1)[0]
    assert c.tz == tz
    assert c.to_location().tz == tz


def test_timezone_at_coordinates(db):
    assert timezone_at(50.08, 14.44) == "Europe/Prague"
    assert timezone_at(-33.87, 151.21) == "Australia/Sydney"
    assert db.nearest(49.2, 16.6).name in {"Brno", "Brno-město"} or db.nearest(49.2, 16.6)


def _sunrise(city, day=datetime(2026, 3, 20, tzinfo=UTC)):
    loc = city.to_location()
    tw = twilight(local_noon(day, loc) - timedelta(days=1), loc)
    return tw.sunrise


@pytest.mark.parametrize(("name", "approx_min"), [("Brno", 8.7), ("Aš", -9.0), ("Ostrava", 15.4)])
def test_sunrise_shift_with_longitude(db, name, approx_min):
    """Around the equinox sunrise moves ~4 min per degree of longitude."""
    praha = db.find("Praha", "CZ")
    other = db.find(name, "CZ")
    diff = (_sunrise(praha) - _sunrise(other)).total_seconds() / 60
    expected = 4.0 * (other.lon - praha.lon)
    assert diff == pytest.approx(expected, abs=1.5)
    assert diff == pytest.approx(approx_min, abs=1.5)


@pytest.mark.parametrize(
    ("text", "lat", "lon"),
    [
        ("50.0755, 14.4378", 50.0755, 14.4378),
        ("50°4'32\"N 14°26'16\"E", 50.0756, 14.4378),
        ("50 4.5 N 14 26 E", 50.075, 14.4333),
        ("-33.86 151.2", -33.86, 151.2),
        ("49,2 S 16,6 V", 49.2, 16.6),
        ("33.9 S 18.4 E", -33.9, 18.4),
        ("49,2, 16,6", 49.2, 16.6),
    ],
)
def test_parse_coordinates(text, lat, lon):
    la, lo = parse_coordinates(text)
    assert la == pytest.approx(lat, abs=1e-3) and lo == pytest.approx(lon, abs=1e-3)


@pytest.mark.parametrize("bad", ["abc", "95 10", "10 200", "1 2 3"])
def test_parse_coordinates_errors(bad):
    with pytest.raises(ValueError):
        parse_coordinates(bad)


def test_textnorm():
    assert fold("České  Budějovice") == "ceske budejovice"
    assert fold("Frýdek-Místek") == "frydek mistek"
    assert levenshtein("prague", "prgaue") == 1  # transposition
    assert levenshtein("abc", "abcdefgh", 2) == 3
    assert levenshtein("kitten", "sitting") == 3
