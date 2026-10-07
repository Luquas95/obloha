"""The Textual application."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from textual import events, work
from textual.app import App, ComposeResult
from textual.command import Hit, Hits, Provider
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import ContentSwitcher, OptionList, Static
from textual.widgets.option_list import Option

from obloha.beginner.compass import CompassReader, SensorSource, termux_available
from obloha.beginner.whatsup import suggestions
from obloha.core.almanac import RiseSet
from obloha.core.ephem import OutOfRangeError
from obloha.core.events import Event
from obloha.core.location import Location
from obloha.core.satellites import SatPass, refresh_tle
from obloha.core.sky import ObjectRef
from obloha.core.weather import fetch_forecast
from obloha.keymap import Keymap
from obloha.render.color import int_to_hex, quantize_256
from obloha.ui.modals import (
    BaseModal,
    CompareScreen,
    DetailScreen,
    GlossaryScreen,
    HelpScreen,
    IdentifyScreen,
    PlaceScreen,
    SearchScreen,
    TimeScreen,
)
from obloha.ui.model import AppModel
from obloha.ui.panes.lists import EventsPane, SatellitesPane
from obloha.ui.panes.settings import SettingsPane
from obloha.ui.panes.sky import SkyPane
from obloha.ui.panes.tonight import TonightPane
from obloha.ui.widgets.chrome import HeaderBar, KeyBar, TouchBar

PANES = ("sky-pane", "tonight-pane", "satellites-pane", "events-pane", "settings-pane")
MOBILE_WIDTH = 72
NARROW_WIDTH = 100

BEGINNER_TOUCH = [
    ("◀", "turn_left"),
    ("?", "identify"),
    ("▶", "turn_right"),
    ("úkoly", "lessons"),
    ("≡", "menu"),
]
ADVANCED_TOUCH = [
    ("◀◀", "time_back"),
    ("▌▌", "time_pause"),
    ("▶▶", "time_forward"),
    ("⌕", "search"),
    ("≡", "menu"),
]


class MenuScreen(BaseModal):
    SCOPED_CSS = False
    """Touch friendly menu (≡) with all important actions."""

    ITEMS: ClassVar[list[tuple[str, str]]] = [
        ("1  Obloha", "screen_sky"),
        ("2  Dnes v noci", "screen_tonight"),
        ("3  Satelity", "screen_satellites"),
        ("4  Úkazy", "screen_events"),
        ("5  Nastavení", "screen_settings"),
        ("m  začátečník / pokročilý", "toggle_mode"),
        ("u  úkoly", "lessons"),
        ("n  noční vidění", "night"),
        ("L  místo", "place"),
        ("T  datum a čas", "time_set"),
        ("0  teď", "time_now"),
        ("/  hledat", "search"),
        ("H  nápověda", "help"),
        ("q  konec", "quit"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog") as v:
            v.border_title = "MENU"
            yield OptionList(*[Option(label) for label, _ in self.ITEMS], id="menu-list")

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self.ITEMS[event.option_index][1])


class ActionCommands(Provider):
    """Command palette entries for every keymap action."""

    async def search(self, query: str) -> Hits:
        app = self.app
        assert isinstance(app, ObloApp)
        matcher = self.matcher(query)
        for action in app.keymap.actions.values():
            score = matcher.match(action.description)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(action.description),
                    lambda a=action.id: app.run_named_action(a),
                    help=f"klávesa {app.keymap.label(action.id)}",
                )


class MainScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        app = self.app
        assert isinstance(app, ObloApp)
        yield HeaderBar(id="header")
        with ContentSwitcher(initial="sky-pane", id="switcher"):
            yield SkyPane()
            yield TonightPane()
            yield SatellitesPane()
            yield EventsPane()
            yield SettingsPane()
        yield TouchBar(BEGINNER_TOUCH, id="touch-beginner")
        yield TouchBar(ADVANCED_TOUCH, id="touch-advanced")
        yield Static("", id="mobile-hint")
        yield KeyBar(id="keybar")


class ObloApp(App[None]):
    TITLE = "obloha"
    COMMANDS = App.COMMANDS | {ActionCommands}
    ENABLE_COMMAND_PALETTE = True
    CSS = """
    Screen { background: $ob-bg; color: $ob-text; layers: base overlay; }
    #switcher { height: 1fr; }
    TouchBar { display: none; }
    #mobile-hint { display: none; height: auto; color: $ob-muted; padding: 0 1; }
    .-mobile #mobile-hint { display: block; }
    .-mobile.-beginner #touch-beginner { display: block; }
    .-mobile.-advanced #touch-advanced { display: block; }
    TouchBar Button { background: $ob-selection; color: $ob-text; border: none; }
    DataTable { background: $ob-panel; }
    Static { background: transparent; }
    #header { background: $ob-bg; }
    """

    def __init__(
        self,
        model: AppModel,
        keymap: Keymap | None = None,
        *,
        sync: bool = False,
        network: bool = True,
        ssh: bool = False,
        compass_factory: Callable[[], SensorSource] | None = None,
        compass_available: Callable[[], bool] = termux_available,
        startup_notice: str | None = None,
    ) -> None:
        self.model = model
        super().__init__()
        self.keymap = keymap or Keymap(overrides=model.cfg.keys)
        self.sync = sync
        self.network = network and not model.offline
        self.ssh = ssh
        self.compass_factory = compass_factory
        self.compass_available = compass_available
        self.compass_reader: CompassReader | None = None
        self.startup_notice = startup_notice
        self._rs_cache: dict[tuple[ObjectRef, datetime, Location], RiseSet | None] = {}
        self._ticker: Any = None
        self._last_side = 0.0
        self._pending: set[str] = set()
        self.main = MainScreen()

    # ------------------------------------------------------------------ theme
    def get_css_variables(self) -> dict[str, str]:
        variables = super().get_css_variables()
        model = getattr(self, "model", None)
        if model is None:
            return variables
        t = model.theme
        pairs = {
            "ob-bg": t.background,
            "ob-panel": t.panel,
            "ob-text": t.text,
            "ob-muted": t.muted,
            "ob-suppressed": t.suppressed,
            "ob-border": t.border,
            "ob-accent": t.accent,
            "ob-accent2": t.accent2,
            "ob-selection": t.selection,
            "ob-good": t.good,
            "ob-bad": t.bad,
        }
        for name, value in pairs.items():
            if model.colors256:
                import numpy as np

                value = int(quantize_256(np.array([value], dtype=np.uint32))[0])
            variables[name] = int_to_hex(value)
        return variables

    def apply_theme(self) -> None:
        self.refresh_css(animate=False)
        self.update_layout()
        self.refresh_all(full=True)

    # ------------------------------------------------------------------ lifecycle
    def on_mount(self) -> None:
        self.push_screen(self.main)
        self.update_layout()
        self.refresh_all(full=True)
        self.restart_ticker()
        if self.network:
            self.network_refresh()
        if self.startup_notice:
            self.notify(self.startup_notice, timeout=8)

    def restart_ticker(self) -> None:
        if self._ticker is not None:
            self._ticker.stop()
        fps = self.model.cfg.display.ssh_fps if self.ssh else self.model.cfg.display.fps
        self._ticker = self.set_interval(1.0 / max(0.1, fps), self.tick)

    def on_resize(self, event: events.Resize) -> None:
        self.update_layout()
        self.call_after_refresh(self.refresh_all, True)

    @property
    def is_mobile(self) -> bool:
        return self.size.width < MOBILE_WIDTH

    def update_layout(self) -> None:
        screen = self.main
        w = self.size.width
        mobile = w < MOBILE_WIDTH
        screen.set_class(mobile, "-mobile")
        screen.set_class(MOBILE_WIDTH <= w < NARROW_WIDTH, "-narrow")
        screen.set_class(self.model.beginner, "-beginner")
        screen.set_class(not self.model.beginner, "-advanced")
        screen.set_class(not self.model.info_panel, "-noinfo")

    # ------------------------------------------------------------------ refresh
    @property
    def current_pane(self) -> str:
        try:
            return self.main.query_one("#switcher", ContentSwitcher).current or "sky-pane"
        except Exception:
            return "sky-pane"

    def refresh_all(self, full: bool = False) -> None:
        if not self.main.is_mounted:
            return
        self.refresh_header()
        pane = self.current_pane
        try:
            widget = self.main.query_one(f"#{pane}")
        except Exception:
            return
        try:
            widget.refresh_content(full=full)  # type: ignore[attr-defined]
        except OutOfRangeError as exc:
            self.model.time.go_live()
            self.notify(str(exc), severity="error")
        self.refresh_footer()

    def refresh_header(self) -> None:
        model = self.model
        header = self.main.query_one(HeaderBar)
        t = model.theme
        header.palette = {
            "border": int_to_hex(t.border),
            "accent": int_to_hex(t.accent),
            "text": int_to_hex(t.text),
            "muted": int_to_hex(t.muted),
        }
        scene = model.scene()
        mobile = self.is_mobile
        place = model.location.name
        if mobile:
            from obloha.ui.formatting import hm

            state = (
                "● "
                + hm(model.now(), model.display_zone)
                + (" živě" if model.time.live else f" {model.time.status}")
            )
            if model.beginner:
                lines = [self._short_status(scene)]
            else:
                l1, _ = model.advanced_status(scene)
                score = model.score_now(scene)
                lines = [
                    f"☉ {scene.sun_alt:.0f}°  ☽ {model.moon_now().illumination * 100:.0f} %"
                    f"  ◆ {score}",
                    f"{model.location.coords_text()}",
                ]
                del l1
            header.set_content(place, state, [model.safe(x) for x in lines], compact=True)
            return
        if model.beginner:
            lines = [model.beginner_status(scene)]
        else:
            lines = list(model.advanced_status(scene))
        header.set_content(place, model.time_text(), lines, compact=False)

    def _short_status(self, scene: Any) -> str:
        from obloha.core.almanac import sky_phase

        phase = sky_phase(scene.sun_alt)
        sky = "Tma ✓" if phase == "astronomická noc" else "Den" if phase == "den" else "Šero"
        moon = scene.bodies["moon"]
        return f"{sky}  Měsíc {'nad obzorem' if moon.alt > 0 else 'pod obzorem'}"

    def context(self) -> str:
        pane = self.current_pane
        if pane == "sky-pane":
            return "sky-beginner" if self.model.beginner else "sky-advanced"
        if pane == "events-pane":
            return "events"
        return "global"

    def refresh_footer(self) -> None:
        km = self.keymap
        bar = self.main.query_one(KeyBar)
        ctx = self.context()
        if ctx == "sky-beginner":
            ids = [
                "turn_left",
                "look_up",
                "zoom_in",
                "identify",
                "lessons",
                "toggle_mode",
                "night",
                "place",
                "help",
            ]
            if self.compass_available():
                ids.insert(4, "compass")
        elif ctx == "sky-advanced":
            ids = [
                "help",
                "search",
                "time_pause",
                "time_forward",
                "time_faster",
                "toggle_view",
                "layer_constellations",
                "night",
                "quit",
            ]
        elif ctx == "events":
            ids = ["event_jump", "event_filter", "screen_sky", "screen_tonight", "help", "quit"]
        else:
            ids = [
                "screen_sky",
                "screen_tonight",
                "screen_satellites",
                "screen_events",
                "screen_settings",
                "help",
                "quit",
            ]
        items = km.footer(ctx, ids)
        if ctx == "sky-beginner":
            items = [("◀▶" if i[0] == "←" else "▲▼" if i[0] == "↑" else i[0], i[1]) for i in items]
        bar.show(items, int_to_hex(self.model.theme.accent))
        hint = self.main.query_one("#mobile-hint", Static)
        if self.is_mobile:
            first = (
                "klepnutí = výběr · tažení = posun · 2× zoom"
                if ctx.startswith("sky")
                else "tlačítko ≡ otevře menu"
            )
            if self.model.compass_on:
                first = "otoč telefon a mapa se natočí s tebou"
            hint.update(first)

    def tick(self) -> None:
        model = self.model
        if self.compass_reader is not None:
            c = self.compass_reader.compass
            model.win_az = c.heading
            model.win_bottom = max(-10.0, min(60.0, c.altitude - 20.0))
            warning = c.warning()
            if warning and warning != model.compass_warning:
                self.notify(warning, severity="warning")
            model.compass_warning = warning
        moving = not (model.time.paused and not model.time.live) or self.compass_reader
        if not moving:
            return
        self.refresh_header()
        pane = self.current_pane
        if pane == "sky-pane":
            sky = self.main.query_one(SkyPane)
            try:
                sky.map.redraw()
            except OutOfRangeError as exc:
                model.time.go_live()
                self.notify(str(exc), severity="error")
                return
            now = time.monotonic()
            if now - self._last_side > 5:
                self._last_side = now
                sky.refresh_content()

    # ------------------------------------------------------------------ data with workers
    def _compute(self, name: str, fn: Callable[[], Any]) -> Any:
        """Run ``fn`` synchronously (tests) or in a worker; returns None while pending."""
        if self.sync:
            return fn()
        if name in self._pending:
            return None
        self._pending.add(name)

        def job() -> None:
            try:
                fn()
            finally:
                self._pending.discard(name)
                self.call_from_thread(self.refresh_all, True)

        self.run_worker(job, thread=True, group=name, exclusive=True)
        return None

    def events_if_ready(self, days: int | None = None) -> list[Event] | None:
        model = self.model
        key_ok = model._events is not None and model._events_key is not None
        if key_ok and model._events_key[2] == model.location:  # type: ignore[index]
            from obloha.core.almanac import night_start

            if model._events_key[0] == night_start(model.now(), model.location).date():  # type: ignore[index]
                return model._events
        return self._compute("events", model.events)  # type: ignore[no-any-return]

    def passes_if_ready(self) -> list[SatPass] | None:
        model = self.model
        if not model.sats:
            return []
        start = model.now().replace(second=0, microsecond=0) - timedelta(minutes=10)
        if model._passes is not None and model._passes_key == (
            start.replace(minute=0),
            model.location,
            len(model.sats),
        ):
            return model._passes
        return self._compute("passes", model.passes)  # type: ignore[no-any-return]

    def next_visible_pass(self) -> SatPass | None:
        passes = self.passes_if_ready() or []
        now = self.model.now()
        return next((p for p in passes if p.visible and p.set.when > now), None)

    def rise_set_cached(self, ref: ObjectRef | None) -> RiseSet | None:
        if ref is None:
            return None
        hour = self.model.now().replace(minute=0, second=0, microsecond=0)
        key = (ref, hour, self.model.location)
        if key not in self._rs_cache:
            if len(self._rs_cache) > 200:
                self._rs_cache.clear()
            self._rs_cache[key] = self.model.rise_set_for(ref)
        return self._rs_cache[key]

    # ------------------------------------------------------------------ network
    @work(exclusive=True, group="network")
    async def network_refresh(self, force_tle: bool = False) -> None:
        model = self.model
        cfg = model.cfg
        if force_tle or model.sat_store.needs_refresh(cfg.satellites.refresh_hours):
            res = await refresh_tle(
                model.sat_store,
                cfg.satellites.groups,
                cfg.satellites.catnr,
                cfg.satellites.starlink,
                offline=model.offline,
                timeout=cfg.network.timeout,
            )
            if res.ok:
                model.reload_satellites()
            elif force_tle:
                self.notify(res.status, severity="warning")
        if cfg.network.weather:
            model.weather = await fetch_forecast(
                model.cache, model.location, offline=model.offline, timeout=cfg.network.timeout
            )
            model._tonight = None
        self.refresh_all(full=True)

    def refresh_satellites(self, force: bool = False) -> None:
        if self.model.offline:
            self.notify("Offline režim: dráhy se nestahují.", severity="warning")
            return
        self.notify("Stahuji dráhy satelitů z CelesTraku…")
        self.network_refresh(force_tle=force)

    # ------------------------------------------------------------------ keys
    def on_key(self, event: events.Key) -> None:
        if self.screen is not self.main:
            return
        focused = self.focused
        from textual.widgets import Input

        if isinstance(focused, Input):
            return
        action = self.keymap.action_for(event.key, self.context())
        if action is None:
            return
        event.stop()
        event.prevent_default()
        self.run_named_action(action)

    def on_header_bar_place_clicked(self, _: HeaderBar.PlaceClicked) -> None:
        self.run_named_action("place")

    def on_touch_bar_pressed(self, event: TouchBar.Pressed) -> None:
        self.run_named_action(event.action)

    def on_sky_map_picked(self, event: Any) -> None:
        model = self.model
        model.identify_point = (event.alt, event.az)
        if event.double:
            if model.beginner:
                model.win_az = event.az
            else:
                model.cursor = (event.alt, event.az)
            model.zoom(True)
        else:
            model.cursor = (event.alt, event.az)
            model.select(event.ref)
            if event.ref is None:
                model.selected = None
        self.refresh_all(full=True)

    def on_sky_map_dragged(self, event: Any) -> None:
        model = self.model
        sky = self.main.query_one(SkyPane)
        res = sky.last_result
        if res is None:
            return
        deg = res.projection.degrees_per_dot()
        if model.beginner or model.adv_view == "direction":
            model.rotate(-event.dx * deg * res.sub_x)
            model.look(event.dy * deg * res.sub_y)
            self.refresh_all()

    # ------------------------------------------------------------------ action dispatch
    def run_named_action(self, name: str) -> None:
        handler = getattr(self, f"do_{name}", None)
        if handler is None:
            self.notify(f"neznámá akce {name}", severity="warning")
            return
        try:
            result = handler()
        except OutOfRangeError as exc:
            self.notify(str(exc), severity="error")
            return
        if isinstance(result, str) and result:
            self.notify(result, timeout=3)
        self.update_layout()
        self.refresh_all(full=True)

    def show_pane(self, pane: str) -> None:
        self.main.query_one("#switcher", ContentSwitcher).current = pane

    def do_screen_sky(self) -> None:
        self.show_pane("sky-pane")

    def do_screen_tonight(self) -> None:
        self.show_pane("tonight-pane")

    def do_screen_satellites(self) -> None:
        self.show_pane("satellites-pane")

    def do_screen_events(self) -> None:
        self.show_pane("events-pane")
        self.call_after_refresh(lambda: self.main.query_one(EventsPane).table.focus())

    def do_screen_settings(self) -> None:
        self.show_pane("settings-pane")

    def do_toggle_mode(self) -> str:
        msg = self.model.toggle_mode()
        self.show_pane("sky-pane")
        return msg

    def do_lessons(self) -> str:
        self.show_pane("sky-pane")
        return self.model.start_lessons()

    def do_found(self) -> str:
        if not self.model.lesson_active:
            return ""
        return self.model.found()

    def do_hint(self) -> str:
        if not self.model.lesson_active:
            return ""
        level = self.model.hint()
        return "nápověda: oblast zúžena" if level == 1 else "nápověda: objekt zvýrazněn"

    def do_skip_lesson(self) -> str:
        lesson = self.model.lesson.skip(self.model.scene())
        self.model._apply_lesson_view(self.model.scene())
        return lesson.title if lesson else ""

    def do_help(self) -> None:
        self.push_screen(HelpScreen())

    def do_command_palette(self) -> None:
        self.action_command_palette()

    def do_menu(self) -> None:
        def chosen(action: str | None) -> None:
            if action:
                self.run_named_action(action)

        self.push_screen(MenuScreen(), chosen)

    def do_search(self) -> None:
        def chosen(ref: ObjectRef | None) -> None:
            if ref is None:
                return
            self.show_pane("sky-pane")
            _, msg = self.model.point_at(ref)
            if msg:
                self.notify(msg, timeout=6)
            self.refresh_all(full=True)

        self.push_screen(SearchScreen(), chosen)

    def do_night(self) -> None:
        self.model.toggle_night()
        self.apply_theme()

    def do_quit(self) -> None:
        if self.current_pane != "sky-pane":
            self.show_pane("sky-pane")
            return
        if self.model.lesson_active:
            self.model.lesson_active = False
            return
        self.stop_compass()
        self.exit()

    def do_place(self) -> None:
        def chosen(loc: Location | None) -> None:
            if loc is None:
                return
            self.model.set_location(loc)
            self._rs_cache.clear()
            self.notify(f"místo: {loc.name}" + (f", {loc.label}" if loc.label else ""))
            if self.network:
                self.network_refresh()
            self.refresh_all(full=True)

        self.push_screen(PlaceScreen(), chosen)

    def do_place_favorites(self) -> str:
        loc = self.model.next_favorite()
        if loc is None:
            return "žádná oblíbená ani poslední místa"
        self.model.set_location(loc, remember=False)
        return f"místo: {loc.name}"

    def do_compare(self) -> None:
        self.push_screen(CompareScreen())

    def compare_places(self) -> list[Location]:
        model = self.model
        places = [model.location]
        for p in model.st.compare:
            loc = p.to_location()
            if (loc.lat, loc.lon) != (model.location.lat, model.location.lon):
                places.append(loc)
        return places[:5]

    def add_compare(self, loc: Location) -> None:
        from obloha.config import Place

        model = self.model
        if len(model.st.compare) >= 4:
            model.st.compare.pop(0)
        if all((p.lat, p.lon) != (loc.lat, loc.lon) for p in model.st.compare):
            model.st.compare.append(Place.from_location(loc))
        model.save()
        self.notify(f"{loc.name} přidáno do porovnání ({len(model.st.compare) + 1}/5)")

    def do_toggle_info(self) -> None:
        self.model.info_panel = not self.model.info_panel
        self.model.cfg.display.info_panel = self.model.info_panel
        self.model.save()

    # time
    def do_time_pause(self) -> str:
        self.model.time.toggle_pause()
        return ""

    def do_time_forward(self) -> None:
        self.model.time.step_forward(1)

    def do_time_back(self) -> None:
        self.model.time.step_forward(-1)

    def do_time_faster(self) -> str:
        self.model.time.change_rate(True)
        return f"rychlost ×{self.model.time.rate}"

    def do_time_slower(self) -> str:
        self.model.time.change_rate(False)
        return f"rychlost ×{self.model.time.rate}"

    def do_time_now(self) -> str:
        self.model.time.go_live()
        return "živý čas"

    def do_time_step(self) -> str:
        self.model.time.cycle_step()
        step = self.model.time.step
        names = {60: "1 minuta", 600: "10 minut", 3600: "1 hodina", 86400: "1 den"}
        return f"krok času: {names.get(int(step.total_seconds()), str(step))}"

    def do_time_set(self) -> None:
        def chosen(when: datetime | None) -> None:
            if when is None:
                return
            try:
                self.model.time.set_time(when)
            except OutOfRangeError as exc:
                self.notify(str(exc), severity="error")
            self.refresh_all(full=True)

        self.push_screen(TimeScreen(), chosen)

    # sky
    def do_zoom_in(self) -> None:
        self.model.zoom(True)

    def do_zoom_out(self) -> None:
        self.model.zoom(False)

    def do_face_north(self) -> None:
        self.model.face(0.0)

    def do_face_south(self) -> None:
        self.model.face(180.0)

    def do_face_east(self) -> None:
        self.model.face(90.0)

    def do_face_west(self) -> None:
        self.model.face(270.0)

    def do_mag_down(self) -> str:
        return self.model.change_magnitude(-0.5)

    def do_mag_up(self) -> str:
        return self.model.change_magnitude(0.5)

    def do_select(self) -> None:
        model = self.model
        if model.beginner and model.selected is None:
            items = suggestions(model.scene(), user_limit=model.beg_limit)
            if items:
                model.select(items[0].ref)
        if not model.beginner:
            res = self.main.query_one(SkyPane).last_result
            if res is not None:
                alt, az = model.cursor
                x, y, ok = res.projection.forward(
                    __import__("numpy").array([alt]), __import__("numpy").array([az])
                )
                if ok[0]:
                    hit = res.nearest(int(x[0] // res.sub_x), int(y[0] // res.sub_y), 3.0)
                    if hit is not None:
                        model.select(hit.ref)
        if model.selected is not None:
            self.push_screen(DetailScreen(model.selected))

    def do_turn_left(self) -> None:
        self.model.rotate(-15.0)

    def do_turn_right(self) -> None:
        self.model.rotate(15.0)

    def do_look_up(self) -> None:
        self.model.look(10.0)

    def do_look_down(self) -> None:
        self.model.look(-10.0)

    def do_cursor_left(self) -> None:
        self.model.move_cursor(0, -self.model.cursor_step())

    def do_cursor_right(self) -> None:
        self.model.move_cursor(0, self.model.cursor_step())

    def do_cursor_up(self) -> None:
        self.model.move_cursor(self.model.cursor_step(), 0)

    def do_cursor_down(self) -> None:
        self.model.move_cursor(-self.model.cursor_step(), 0)

    def do_toggle_view(self) -> str:
        return self.model.toggle_view()

    def do_layer_constellations(self) -> str:
        return self.model.toggle_layer("constellation_lines")

    def do_layer_borders(self) -> str:
        return self.model.toggle_layer("constellation_borders")

    def do_layer_milky_way(self) -> str:
        return self.model.toggle_layer("milky_way")

    def do_layer_grid(self) -> str:
        return self.model.toggle_layer("grid")

    def do_layer_ecliptic(self) -> str:
        return self.model.toggle_layer("ecliptic")

    def do_layer_labels(self) -> str:
        return self.model.toggle_layer("labels")

    def do_layer_below(self) -> str:
        return self.model.toggle_layer("below_horizon")

    def do_identify(self) -> None:
        model = self.model
        if model.identify_point is not None:
            alt, az = model.identify_point
        elif model.selected is not None and model.scene().altaz_of(model.selected):
            alt, az = model.scene().altaz_of(model.selected)  # type: ignore[misc]
        else:
            items = suggestions(model.scene(), user_limit=model.beg_limit)
            if items:
                alt, az = items[0].alt, items[0].az
            else:
                alt, az = max(15.0, model.win_bottom + 30.0), model.win_az

        def chosen(ref: ObjectRef | None) -> None:
            if ref is not None:
                model.point_at(ref)
            self.refresh_all(full=True)

        self.push_screen(IdentifyScreen(alt, az), chosen)

    def do_compass(self) -> str:
        if not self.compass_available():
            return "Kompas funguje jen přímo v Termuxu s doplňkem Termux:API."
        if self.compass_reader is not None:
            self.stop_compass()
            return "kompas vypnut"
        from obloha.beginner.compass import TermuxSensor

        factory = self.compass_factory or TermuxSensor
        self.compass_reader = CompassReader(factory())
        self.compass_reader.start()
        self.model.compass_on = True
        return "kompas zapnut: mapa se natáčí podle telefonu"

    def stop_compass(self) -> None:
        if self.compass_reader is not None:
            self.compass_reader.stop()
            self.compass_reader = None
        self.model.compass_on = False

    # events
    def do_event_jump(self) -> str:
        if self.current_pane != "events-pane":
            return ""
        ev = self.main.query_one(EventsPane).current()
        if ev is None:
            return ""
        try:
            self.model.time.set_time(ev.when)
        except OutOfRangeError as exc:
            return str(exc)
        self.show_pane("sky-pane")
        if ev.bodies:
            self.model.point_at(ObjectRef.body(ev.bodies[-1]))
        return f"čas nastaven na úkaz: {ev.title}"

    def do_event_filter(self) -> None:
        self.main.query_one(EventsPane).cycle_filter()

    # ------------------------------------------------------------------ markup actions
    def action_pick_suggestion(self, index: int) -> None:
        model = self.model
        items = suggestions(model.scene(), user_limit=model.beg_limit)
        if 0 <= index < len(items):
            model.point_at(items[index].ref)
        self.refresh_all(full=True)

    def action_glossary(self, term: str) -> None:
        self.push_screen(GlossaryScreen(term))

    def action_event_kind(self, kind: str) -> None:
        self.main.query_one(EventsPane).toggle_kind(kind)

    def action_use_favorite(self, index: int) -> None:
        favs = self.model.cfg.favorites
        if 0 <= index < len(favs):
            self.model.set_location(favs[index].to_location())
            self.refresh_all(full=True)

    def action_remove_favorite(self, index: int) -> None:
        self.model.remove_favorite(index)
        self.refresh_all(full=True)


def now_utc() -> datetime:
    return datetime.now(UTC)
