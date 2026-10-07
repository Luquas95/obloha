"""Interaction tests with Textual's Pilot (keyboard, mouse/touch, dialogs)."""

from datetime import timedelta

import pytest
from textual.widgets import ContentSwitcher, Input

from obloha.beginner.compass import FakeSensor
from obloha.core.sky import ObjectRef
from obloha.ui.modals import (
    HelpScreen,
    IdentifyScreen,
    PlaceScreen,
    SearchScreen,
    TimeScreen,
)
from obloha.ui.panes.lists import EventsPane
from obloha.ui.panes.sky import SkyPane
from tests.test_beginner import _sample
from tests.ui_helpers import FIXED, make_app

pytestmark = pytest.mark.ui


def pane(app):
    return app.main.query_one("#switcher", ContentSwitcher).current


async def test_switch_screens_and_quit():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        for key, name in [
            ("2", "tonight-pane"),
            ("3", "satellites-pane"),
            ("4", "events-pane"),
            ("5", "settings-pane"),
            ("1", "sky-pane"),
        ]:
            await pilot.press(key)
            assert pane(app) == name
        await pilot.press("4", "q")
        assert pane(app) == "sky-pane"
        await pilot.press("q")
    assert app.return_code == 0 or app.return_code is None


async def test_mode_toggle_and_layers():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        assert app.model.beginner
        await pilot.press("m")
        assert not app.model.beginner
        before = app.model.layers.constellation_lines
        await pilot.press("c")
        assert app.model.layers.constellation_lines != before
        await pilot.press("g")
        assert app.model.layers.grid == "altaz"
        await pilot.press("v")
        assert app.model.adv_view == "direction"
        fov = app.model.dir_fov
        await pilot.press("plus")
        assert app.model.dir_fov < fov
        await pilot.press("S")
        assert app.model.dir_az == 180
        await pilot.press("left_square_bracket")
        assert app.model.adv_limit == 5.0
        await pilot.press("right", "up", "enter")
        await pilot.pause()


async def test_beginner_navigation_and_lessons():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("right")
        assert app.model.win_az == 195
        await pilot.press("up")
        assert app.model.win_bottom == 4
        await pilot.press("u")
        assert app.model.lesson_active and app.model.lesson.current == "brightest_planet"
        sky = app.main.query_one(SkyPane)
        assert sky.query_one("#lesson-box").display
        await pilot.press("x")
        assert app.model.lesson.hint == 1
        await pilot.click("#lesson-found")
        assert "brightest_planet" in app.model.lesson.done
        assert app.model.lesson.current == "summer_triangle"


async def test_time_controls():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("full_stop")
        assert app.model.now() == FIXED + timedelta(hours=1)
        await pilot.press("comma", "comma")
        assert app.model.now() == FIXED - timedelta(hours=1)
        await pilot.press("s")
        assert app.model.time.step == timedelta(days=1)
        await pilot.press("greater_than_sign")
        assert app.model.time.rate == 10
        await pilot.press("0")
        assert app.model.time.live
        await pilot.press("T")
        assert isinstance(app.screen, TimeScreen)
        await pilot.press(*"2027-08-02 12:00", "enter")
        assert app.model.now().strftime("%Y-%m-%d %H:%M") == "2027-08-02 10:00"
        await pilot.press("T")
        await pilot.press(*"2099-01-01", "enter")
        assert app.model.now().year == 2027  # out of range refused


async def test_search_dialog():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("slash")
        assert isinstance(app.screen, SearchScreen)
        await pilot.press(*"vega")
        await pilot.press("enter")
        assert app.model.selected == ObjectRef.star(app.model.scene().cat.star_by_key("Vega"))
        await pilot.press("slash", *"sirius", "enter")
        # Sirius is below the horizon: view does not move but a message tells when it rises
        assert app.model.selected.kind == "star"


async def test_night_vision_and_help():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("n")
        assert app.model.night
        assert app.get_css_variables()["ob-text"] == "#e0403a"
        await pilot.press("H")
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.press("m", "question_mark")
        assert isinstance(app.screen, HelpScreen)


async def test_place_picker_and_compare():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("L")
        assert isinstance(app.screen, PlaceScreen)
        await pilot.press(*"plzen")
        await pilot.pause()
        await pilot.press("ctrl+o")
        await pilot.press("enter")
        assert app.model.location.name == "Plzeň"
        assert app.model.location.label == "okr. Plzeň-město"
        assert app.model.st.recent[0].name == "Plzeň"
        assert len(app.compare_places()) == 1  # Plzeň is the current place now
        await pilot.press("L", *"50.08, 14.44", "enter")
        assert app.model.location.lat == pytest.approx(50.08)
        assert app.model.location.tz == "Europe/Prague"
        assert len(app.compare_places()) == 2
        app.run_named_action("compare")
        await pilot.pause()
        await pilot.press("escape")


async def test_identify_dialog_beginner():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        b = app.model.scene().bodies["saturn"]
        app.model.identify_point = (b.alt, b.az)
        await pilot.press("question_mark")
        assert isinstance(app.screen, IdentifyScreen)
        assert app.screen.result.best.name == "Saturn"
        await pilot.click("#identify-select")
        assert app.model.selected == ObjectRef.body("saturn")


async def test_events_jump():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("4")
        events = app.main.query_one(EventsPane)
        assert events.table.row_count > 20
        await pilot.press("down", "down")
        ev = events.current()
        await pilot.press("j")
        assert app.model.now() == ev.when
        assert pane(app) == "sky-pane"
        await pilot.press("4", "f")
        assert len(events.kinds) == 1


async def test_touch_click_and_drag():
    app = make_app(mode="advanced")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        sky = app.main.query_one(SkyPane)
        hit = next(h for h in sky.last_result.hits if h.ref == ObjectRef.body("saturn"))
        await pilot.click("#skymap", offset=(hit.col, hit.row))
        assert app.model.selected == ObjectRef.body("saturn")
        await pilot.click("#skymap", offset=(hit.col, hit.row), times=2)
        assert app.model.adv_view == "direction"
        az = app.model.dir_az
        sky.map.post_message(sky.map.Dragged(-6, 0))
        await pilot.pause()
        assert app.model.dir_az != az


async def test_mobile_touch_buttons():
    app = make_app()
    async with app.run_test(size=(46, 44)) as pilot:
        assert app.is_mobile
        await pilot.pause()
        await pilot.click("#touch-turn_right")
        assert app.model.win_az == 195
        await pilot.click("#touch-menu")
        await pilot.pause()
        await pilot.press("down", "enter")  # "2 Dnes v noci"
        assert pane(app) == "tonight-pane"
        await pilot.resize_terminal(120, 40)
        await pilot.pause()
        assert not app.is_mobile


async def test_compass_hidden_without_termux():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("c")
        assert app.compass_reader is None and not app.model.compass_on


async def test_compass_with_fake_sensor():
    app = make_app(compass=True, compass_factory=lambda: FakeSensor([_sample(135)] * 20))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("c")
        assert app.model.compass_on
        app.compass_reader._thread.join(timeout=2)
        app.tick()
        assert abs(app.model.win_az - 135) < 2
        await pilot.press("c")
        assert not app.model.compass_on


async def test_settings_changes_persist(tmp_path):
    app = make_app(persist=True)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.press("5")
        await pilot.click("#set-night")
        assert app.model.night
        inp = app.main.query_one("#set-limit", Input)
        inp.value = "4.5"
        await pilot.pause()
        assert app.model.adv_limit == 4.5
        await pilot.click("#set-fav-add")
        assert app.model.cfg.favorites
    from obloha.config import load_config

    cfg, _ = load_config()
    assert cfg.display.night and cfg.display.limiting_mag == 4.5


async def test_partial_repaint_only_changed_rows():
    app = make_app(mode="advanced")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        sky = app.main.query_one(SkyPane)
        rows = sky.map.size.height
        n = sky.map.rows_repainted
        sky.map.redraw()  # nothing changed: no row is repainted
        assert sky.map.rows_repainted == n
        app.model.cursor = (app.model.cursor[0] + 5, app.model.cursor[1])
        sky.map.redraw()  # only the rows around the old and new cursor change
        assert 0 < sky.map.rows_repainted - n <= 4 < rows


async def test_background_workers_compute_and_do_not_loop_on_errors():
    app = make_app(sync=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("4")
        await app.workers.wait_for_complete()
        await pilot.pause()
        events = app.main.query_one(EventsPane)
        assert events.table.row_count > 20
        calls = []

        def broken():
            calls.append(1)
            raise RuntimeError("boom")

        app.model._events = None
        app.model.events = broken  # type: ignore[method-assign]
        for _ in range(5):
            app.refresh_all(full=True)
            await app.workers.wait_for_complete()
            await pilot.pause()
        assert len(calls) == 1


async def test_night_vision_has_only_red_hues():
    import re

    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("n")
        for keys in ([], ["question_mark"], ["escape", "L"], ["escape", "5"]):
            await pilot.press(*keys)
            await pilot.pause()
            svg = app.export_screenshot()
            colors = set(re.findall(r"#([0-9a-fA-F]{6})\b", svg))
            bad = []
            for c in colors:
                r, g, b = (int(c[i : i + 2], 16) for i in (0, 2, 4))
                if c.lower() in ("c5c8c6", "292929", "ff5f57", "febc2e", "28c840"):
                    continue  # SVG window chrome drawn by the exporter, not the app
                if b > r or g > r or min(r, g, b) > 180:
                    bad.append(c)
            assert not bad, (keys, sorted(bad)[:10])
