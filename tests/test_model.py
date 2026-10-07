from datetime import UTC, datetime, timedelta

import pytest

from obloha.config import State, load_config
from obloha.core.cities import city_db
from obloha.core.sky import ObjectRef
from obloha.ui.compare import compare_rows
from obloha.ui.formatting import bar, date_long, duration, num, plural, tz_abbr
from obloha.ui.modals import parse_time_input
from obloha.ui.model import AppModel
from tests.ui_helpers import FIXED


@pytest.fixture
def model():
    cfg, doc = load_config()
    return AppModel(cfg, doc, State(), fixed_time=FIXED, offline=True, persist=False)


def test_texts(model):
    scene = model.scene()
    assert "astronomická noc" in model.beginner_status(scene)
    l1, l2 = model.advanced_status(scene)
    assert "Saturn u opozice" in l1 and "50,08° N" in l2
    assert model.time_text() == "◼ zastaveno · čt 1. 10. 2026 · 21:00:00 SELČ"
    assert 0 <= model.score_now(scene) <= 100


def test_view_actions(model):
    model.rotate(30)
    assert model.win_az == 210
    model.zoom(True)
    assert model.win_fov == 120
    model.toggle_mode()
    model.zoom(True)
    assert model.adv_view == "direction"
    for _ in range(6):
        model.zoom(False)
    assert model.adv_view == "full"
    assert model.toggle_layer("grid") == "síť: výška/azimut"
    assert "zapnuto" in model.toggle_layer("ecliptic")
    assert model.change_magnitude(1) == "mezní magnituda 6,5"
    model.face(90)
    assert model.adv_view == "direction" and model.dir_az == 90
    model.move_cursor(5, 5)
    assert model.toggle_view() == "celá obloha"


def test_point_at_below_horizon(model):
    sirius = ObjectRef.star(model.scene().cat.star_by_key("Sirius"))
    visible, msg = model.point_at(sirius)
    assert not visible and msg.startswith("Teď je pod obzorem, vyjde v")
    visible, msg = model.point_at(ObjectRef.body("saturn"))
    assert visible and msg == ""


def test_tonight_and_events(model):
    data = model.tonight()
    assert data.twilight.sunset and data.planets[0].info.id == "saturn"
    assert data.best_score > 50
    assert model.events(days=10)
    assert model.passes() == []
    assert "Nejsou stažené dráhy" in model.sat_age_warning()


def test_locations_and_favorites(model):
    brno = city_db().find("Brno", "CZ").to_location()
    assert model.add_favorite(brno) and not model.add_favorite(brno)
    assert model.next_favorite().name == "Brno"
    model.set_location(brno)
    assert model.cfg.location.name == "Brno" and model.st.recent[0].name == "Brno"
    model.remove_favorite(0)
    assert model.cfg.favorites == []


def test_lessons_flow(model):
    assert model.start_lessons() == "Najdi nejjasnější planetu dnes večer"
    assert model.lesson_view(model.scene()) is not None
    assert model.hint() == 1
    assert model.found().startswith("Výborně")
    assert model.start_lessons() == "úkoly skryty"


def test_compare_rows(model):
    places = [model.location, city_db().find("Ostrava", "CZ").to_location()]
    rows = dict(compare_rows(model, places))
    assert rows["časové pásmo"] == ["Europe/Prague", "Europe/Prague"]
    assert rows["západ Slunce"][0] > rows["západ Slunce"][1]  # Ostrava is further east
    assert "zatmění" in " ".join(rows)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-10-01 21:00", datetime(2026, 10, 1, 19, 0, tzinfo=UTC)),
        ("1. 10. 2026 21:00", datetime(2026, 10, 1, 19, 0, tzinfo=UTC)),
        ("22:30", datetime(2026, 10, 1, 20, 30, tzinfo=UTC)),
        ("zítra 5:30", datetime(2026, 10, 2, 3, 30, tzinfo=UTC)),
        ("+2h", FIXED + timedelta(hours=2)),
        ("-3d", FIXED - timedelta(days=3)),
        ("teď", FIXED),
    ],
)
def test_parse_time_input(text, expected):
    from obloha.core.location import PRAGUE

    assert parse_time_input(text, FIXED, PRAGUE.zone) == expected


def test_parse_time_input_error():
    from obloha.core.location import PRAGUE

    with pytest.raises(ValueError):
        parse_time_input("včera ráno nějak", FIXED, PRAGUE.zone)


def test_formatting():
    from zoneinfo import ZoneInfo

    assert num(-0.12) == "−0,1"
    assert duration(timedelta(hours=10, minutes=5)) == "10 h 05 m"
    assert bar(0.5, 4) == "██░░"
    assert plural(3, "pěst", "pěsti", "pěstí") == "pěsti"
    assert date_long(FIXED, ZoneInfo("Europe/Prague")) == "čt 1. 10. 2026"
    assert tz_abbr(FIXED, ZoneInfo("Asia/Kolkata")) == "IST"
    assert tz_abbr(FIXED, ZoneInfo("America/Caracas")) == "UTC−4"


def test_local_zone(monkeypatch):
    from obloha.ui.formatting import local_zone

    monkeypatch.setenv("TZ", "America/New_York")
    assert str(local_zone()) == "America/New_York"


def test_events_clamped_near_ephemeris_end(model):
    model.time.set_time(datetime(2049, 12, 20, tzinfo=UTC))
    model.events()  # must not raise although 3 months would leave DE421
    assert model.passes() == []
