from datetime import timedelta

import pytest

from obloha.beginner.compass import (
    Compass,
    CompassReader,
    FakeSensor,
    SensorSample,
    heading_and_pitch,
    termux_available,
)
from obloha.beginner.describe import (
    brightness_word,
    color_word,
    direction_arrow,
    direction_name,
    direction_word,
    fist_range_text,
    fist_text,
    fists,
    height_word,
    position_sentence,
)
from obloha.beginner.glossary import GLOSSARY, explain, mark_terms
from obloha.beginner.identify import identify, parse_direction
from obloha.beginner.lessons import LESSONS, LessonProgress, available_lessons
from obloha.beginner.whatsup import suggestions
from obloha.core.objects import object_info
from obloha.core.sky import ObjectRef, SatPosition, build_scene


@pytest.fixture(scope="module")
def scene():
    from obloha.core.location import PRAGUE
    from tests.conftest import FIXED_UTC

    return build_scene(FIXED_UTC, PRAGUE)


@pytest.mark.parametrize(
    ("alt", "word"),
    [
        (-3, "pod obzorem"),
        (5, "těsně nad obzorem"),
        (9.9, "těsně nad obzorem"),
        (10, "nízko"),
        (24.9, "nízko"),
        (25, "napůl k nebi"),
        (54.9, "napůl k nebi"),
        (55, "vysoko"),
        (75, "skoro nad hlavou"),
        (90, "skoro nad hlavou"),
    ],
)
def test_height_words(alt, word):
    assert height_word(alt) == word


@pytest.mark.parametrize(
    ("alt", "text"),
    [
        (2, "kousek nad obzorem"),
        (5, "asi půl pěsti"),
        (10, "asi 1 pěst"),
        (19, "asi 2 pěsti"),
        (15, "asi 1,5 pěsti"),
        (52, "asi 5 pěstí"),
    ],
)
def test_fists(alt, text):
    assert fist_text(alt) == text
    assert fists(alt) * 10 == pytest.approx(round(alt / 5) * 5, abs=0.01)


def test_fist_range():
    assert fist_range_text(66) == "6–7 pěstí"
    assert fist_range_text(35) == "3–4 pěsti"
    assert fist_range_text(5) == "asi půl pěsti"


@pytest.mark.parametrize(
    ("az", "word", "name", "arrow"),
    [
        (0, "na severu", "sever", "↑"),
        (130, "na jihovýchodě", "jihovýchod", "↘"),
        (180, "na jihu", "jih", "↓"),
        (230, "na jihozápadě", "jihozápad", "↙"),
        (350, "na severu", "sever", "↑"),
        (290, "na západě", "západ", "←"),
    ],
)
def test_directions(az, word, name, arrow):
    assert direction_word(az) == word
    assert direction_name(az) == name
    assert direction_arrow(az) == arrow


def test_position_sentences():
    assert position_sentence(19, 130) == "Nízko na jihovýchodě, asi 2 pěsti nad obzorem."
    assert position_sentence(66, 230) == "Vysoko na jihozápadě, 6–7 pěstí nad obzorem."
    assert position_sentence(85, 10) == "Skoro přímo nad hlavou."
    assert position_sentence(40, 180).startswith("Na jihu, napůl k nebi")
    assert position_sentence(-5, 90).startswith("Teď je pod obzorem")
    assert position_sentence(5, 270).startswith("Těsně nad obzorem na západě")


def test_colour_and_brightness_words():
    assert color_word(-0.1) == "bílomodrý"
    assert color_word(-0.1, feminine=True) == "bílomodrá"
    assert color_word(0.9, gender="n") == "nažloutlé"
    assert color_word(1.6) == "červenooranžový"
    assert color_word(None) == "bílý"
    assert brightness_word(-4) == "oslnivě jasný"
    assert brightness_word(0.0, True) == "jasná"
    assert brightness_word(3.0) == "slabý"


def test_whatsup_deterministic(scene):
    a = suggestions(scene)
    b = suggestions(scene)
    assert [s.title for s in a] == [s.title for s in b]
    assert 3 <= len(a) <= 5
    assert a[0].title == "Saturn"
    assert "nebliká" in a[0].text
    assert "Letní trojúhelník" in [s.title for s in a]
    assert all(1 <= len(s.sentences) <= 4 for s in a)


def test_whatsup_daytime(scene, prague, fixed_utc):
    day = build_scene(fixed_utc - timedelta(hours=7), prague)
    titles = [s.title for s in suggestions(day)]
    assert "Letní trojúhelník" not in titles


def test_whatsup_satellite_first(scene):
    import dataclasses

    sat = SatPosition("ISS", 40.0, 200.0, True, 500.0, -3.0)
    sc = dataclasses.replace(scene, satellites=[sat])
    assert suggestions(sc)[0].title == "ISS"


def test_identify_saturn(scene):
    b = scene.bodies["saturn"]
    res = identify(scene, b.alt + 1.5, b.az - 2.0)
    assert res.best.ref == ObjectRef.body("saturn")
    assert res.best.probability > 0.5
    assert "nebliká" in res.best.explanation.lower()
    assert res.alternatives and res.alternatives[0].startswith("Pokud to bliká")


def test_identify_between_two_stars(scene):
    cat = scene.cat
    vega = cat.star_by_key("Alioth")
    deneb = cat.star_by_key("Mizar")
    # a point between Alioth and Mizar (4.5° apart), slightly closer to Alioth
    a1, z1 = scene.star_alt[vega], scene.star_az[vega]
    a2, z2 = scene.star_alt[deneb], scene.star_az[deneb]
    from obloha.core.coords import altaz_to_nev, nev_to_altaz

    v = 0.6 * altaz_to_nev(a1, z1) + 0.4 * altaz_to_nev(a2, z2)
    alt, az = nev_to_altaz(v)
    res = identify(scene, float(alt), float(az))
    names = [c.name for c in res.candidates]
    assert names[:2] == ["Alioth", "Mizar"]
    assert res.candidates[0].probability > res.candidates[1].probability


def test_identify_moving(scene):
    import dataclasses

    sc = dataclasses.replace(scene, satellites=[SatPosition("ISS", 30, 100, True, 600, -2.5)])
    res = identify(sc, 32, 105, moving=True)
    assert res.best.name == "ISS" and res.best.kind == "družice"
    assert any("letadlo" in a for a in res.alternatives)


def test_parse_direction():
    assert parse_direction("jihovýchod, 2 pěsti") == (20.0, 135.0)
    assert parse_direction("JZ 30°") == (30.0, 225.0)
    assert parse_direction("západ nízko") == (12.0, 270.0)
    assert parse_direction("sever") == (20.0, 0.0)
    with pytest.raises(ValueError):
        parse_direction("tamhle")


def test_lessons_selection(scene):
    avail = [lesson.id for lesson in available_lessons(scene)]
    assert avail[0] == "brightest_planet"
    assert "summer_triangle" in avail and "dipper_polaris" in avail
    assert "orion" not in avail  # Orion is below the horizon on autumn evenings
    for lesson in LESSONS:
        if lesson.id in avail:
            for level in (0, 1, 2):
                view = lesson.build(scene, level)
                assert 2 <= len(view.steps) <= 4
                if level == 2:
                    assert view.highlights
                if level >= 1:
                    assert view.hint_circle is not None


def test_lesson_progress(scene):
    p = LessonProgress()
    first = p.start(scene)
    assert first.id == "brightest_planet"
    assert p.position(scene) == (1, len(LESSONS))
    assert p.next_hint() == 1 and p.next_hint() == 2 and p.next_hint() == 2
    second = p.found(scene)
    assert second.id == "summer_triangle" and p.hint == 0
    assert "brightest_planet" in p.done
    view = second.build(scene, 0)
    assert any("Altair" in s for s in view.steps)
    assert p.next_title(scene) == "Od Velkého vozu k Polárce"
    assert p.skip(scene).id != "summer_triangle"


def test_lessons_daytime_none(prague, fixed_utc):
    day = build_scene(fixed_utc - timedelta(hours=7), prague)
    assert available_lessons(day) == []
    assert LessonProgress().start(day) is None


def test_glossary_marks():
    parts = mark_terms("Saturn je v opozici, magnituda 0,6 a výška 19°. Opozice!")
    terms = [p.term for p in parts if p.term]
    assert terms == ["opozice", "magnituda", "výška"]
    assert "".join(p.text for p in parts).startswith("Saturn je v opozici")
    assert explain("zenit")
    assert all(1 <= v.count(".") <= 3 for v in GLOSSARY.values())


def test_object_info(scene):
    cat = scene.cat
    vega = object_info(scene, ObjectRef.star(cat.star_by_key("Vega")))
    assert vega.constellation == "Lyra" and vega.kind_cs == "hvězda"
    sat = object_info(scene, ObjectRef.body("saturn"))
    assert sat.is_planet and not sat.twinkles and sat.distance_au > 8
    assert object_info(scene, ObjectRef("dso", "M31")).kind_cs == "objekt"
    assert object_info(scene, ObjectRef("asterism", "summer_triangle")).name == "Letní trojúhelník"
    assert object_info(scene, ObjectRef("constellation", "0")).kind_cs == "souhvězdí"
    assert object_info(scene, ObjectRef("nothing", "x")) is None


# ------------------------------------------------------------------ compass
def _sample(heading_deg, tilt_up_deg=0.0, noise=0.0):
    """Phone upright, back camera towards ``heading_deg`` (synthetic field)."""
    import math

    h = math.radians(heading_deg + noise)
    t = math.radians(tilt_up_deg)
    # world: E, N, U (right-handed); Earth field: north 20, down 40
    field = (0.0, 20.0, -40.0)
    # device axes in world coords: x = right, y = up(top), z = towards user
    look = (math.cos(t) * math.sin(h), math.cos(t) * math.cos(h), math.sin(t))
    right = (math.cos(h), -math.sin(h), 0.0)
    z = tuple(-c for c in look)
    y = (
        z[1] * right[2] - z[2] * right[1],
        z[2] * right[0] - z[0] * right[2],
        z[0] * right[1] - z[1] * right[0],
    )

    def dev(v):
        return (
            sum(a * b for a, b in zip(v, right, strict=True)),
            sum(a * b for a, b in zip(v, y, strict=True)),
            sum(a * b for a, b in zip(v, z, strict=True)),
        )

    return SensorSample(dev((0.0, 0.0, 9.81)), dev(field))


@pytest.mark.parametrize("heading", [0, 45, 135, 180, 270, 359])
def test_heading_from_sensors(heading):
    az, alt = heading_and_pitch(_sample(heading))
    assert (az - heading + 180) % 360 - 180 == pytest.approx(0, abs=0.5)
    assert alt == pytest.approx(0, abs=0.5)
    az, alt = heading_and_pitch(_sample(heading, tilt_up_deg=30))
    assert alt == pytest.approx(30, abs=0.5)


def test_compass_smoothing_and_wraparound():
    c = Compass(alpha=0.5)
    for h in (350, 10, 350, 10, 0, 0, 0):
        c.update(_sample(h))
    assert min(c.heading, 360 - c.heading) < 6
    assert not c.unstable and c.warning() is None


def test_compass_unstable():
    c = Compass()
    for i in range(12):
        c.update(_sample(0, noise=(-60 if i % 2 else 60)))
    assert c.unstable
    assert "nestabilní" in c.warning()


def test_compass_reader_with_fake_sensor():
    reader = CompassReader(FakeSensor([_sample(90)] * 5))
    reader.start()
    reader._thread.join(timeout=2)
    assert abs(reader.compass.heading - 90) < 1
    reader.stop()


def test_termux_detection(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/data/termux-sensor")
    assert termux_available({"TERMUX_VERSION": "0.118"})
    assert not termux_available({"TERMUX_VERSION": "0.118", "SSH_CONNECTION": "1 2 3 4"})
    assert not termux_available({})
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert not termux_available({"TERMUX_VERSION": "0.118"})
