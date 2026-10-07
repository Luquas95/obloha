"""UI-independent application state and actions (testable without Textual)."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import tomlkit

from obloha.beginner.lessons import LESSON_BY_ID, LessonProgress, LessonView
from obloha.config import Config, Place, State, cache_dir, save_config, save_state
from obloha.core.almanac import (
    MoonInfo,
    PlanetNight,
    RiseSet,
    TwilightTimes,
    moon_info,
    night_start,
    planets_tonight,
    rise_transit_set,
    sky_phase,
    twilight,
)
from obloha.core.bodies import BODY_BY_ID
from obloha.core.ephem import OutOfRangeError
from obloha.core.events import Event, compute_events
from obloha.core.location import Location
from obloha.core.satellites import SatelliteStore, SatPass, current_positions, passes_for_all
from obloha.core.sky import ObjectRef, SkyScene, build_scene
from obloha.core.timectl import TimeController
from obloha.core.weather import (
    HourScore,
    WeatherResult,
    best_window,
    night_scores,
    score_word,
)
from obloha.render.sky import Layers, ViewOptions
from obloha.render.theme import DARK, LIGHT, NIGHT, Theme
from obloha.ui.formatting import hm, num

WINDOW_FOV_RANGE = (90.0, 200.0)
DIRECTION_FOV_RANGE = (30.0, 180.0)


@dataclass
class TonightData:
    """Everything shown on the "Dnes v noci" screen (one night, one place)."""

    start: datetime
    twilight: TwilightTimes
    moon: MoonInfo
    moon_rs: RiseSet
    planets: list[PlanetNight]
    scores: list[HourScore]
    window: tuple[datetime, datetime] | None
    weather_status: str
    events: list[Event] = field(default_factory=list)
    passes: list[SatPass] = field(default_factory=list)

    @property
    def best_score(self) -> int:
        return max((s.score for s in self.scores), default=0)


class AppModel:
    """Holds the whole application state; the Textual app only renders it."""

    def __init__(
        self,
        config: Config,
        doc: tomlkit.TOMLDocument,
        state: State,
        *,
        location: Location | None = None,
        fixed_time: datetime | None = None,
        offline: bool | None = None,
        ascii_mode: bool | None = None,
        colors256: bool = False,
        clock: Any = time.time,
        persist: bool = True,
        cache: Path | None = None,
    ) -> None:
        self.cfg = config
        self.doc = doc
        self.st = state
        self.persist = persist
        self.location = location or config.location.to_location()
        self.time = TimeController.fixed(fixed_time, clock) if fixed_time else TimeController(
            clock=clock
        )
        self.mode = config.display.mode
        self.night = config.display.night
        self.ascii = config.display.ascii if ascii_mode is None else ascii_mode
        self.colors256 = colors256 or config.display.colors == "256"
        self.offline = config.network.offline if offline is None else offline
        lc = config.layers
        self.layers = Layers(
            constellation_lines=lc.constellation_lines,
            constellation_borders=lc.constellation_borders,
            labels=lc.labels,
            milky_way=lc.milky_way,
            grid=None if lc.grid == "none" else lc.grid,
            ecliptic=lc.ecliptic,
            planets=lc.planets,
            moon=lc.moon,
            sun=lc.sun,
            satellites=lc.satellites,
            below_horizon=lc.below_horizon,
        )
        self.adv_view = "full"
        self.dir_az = 180.0
        self.dir_alt = 35.0
        self.dir_fov = config.display.view_fov
        self.win_az = 180.0
        self.win_bottom = -6.0
        self.win_fov = config.display.window_fov
        self.adv_limit = config.display.limiting_mag
        self.beg_limit = config.beginner_limit()
        self.selected: ObjectRef | None = None
        self.cursor: tuple[float, float] = (45.0, 180.0)
        self.identify_point: tuple[float, float] | None = None
        self.lesson = LessonProgress(done=list(state.lessons_done))
        self.lesson_active = False
        self.compass_on = False
        self.compass_warning: str | None = None
        self.info_panel = config.display.info_panel
        self.message = ""
        self.cache = cache or cache_dir()
        self.sat_store = SatelliteStore(self.cache)
        self.sats = self.sat_store.load()
        self.sat_status = self.sat_store.age_text()
        self.weather: WeatherResult | None = None
        self._scene: SkyScene | None = None
        self._scene_key: tuple[Any, ...] | None = None
        self._tonight: TonightData | None = None
        self._tonight_key: tuple[Any, ...] | None = None
        self._events: list[Event] | None = None
        self._events_key: tuple[Any, ...] | None = None
        self._passes: list[SatPass] | None = None
        self._passes_key: tuple[Any, ...] | None = None

    # ------------------------------------------------------------------ time & scene
    def now(self) -> datetime:
        return self.time.now()

    def scene(self, now: datetime | None = None) -> SkyScene:
        when = (now or self.now()).replace(microsecond=0)
        key = (when, self.location, len(self.sats))
        if self._scene is None or self._scene_key != key:
            sats = current_positions(self.sats, when, self.location) if self.sats else []
            self._scene = build_scene(when, self.location, sats)
            self._scene_key = key
        return self._scene

    @property
    def theme(self) -> Theme:
        if self.night:
            return NIGHT
        return LIGHT if self.cfg.display.theme == "light" else DARK

    @property
    def beginner(self) -> bool:
        return self.mode == "beginner"

    def lesson_view(self, scene: SkyScene) -> LessonView | None:
        if not (self.beginner and self.lesson_active and self.lesson.current):
            return None
        lesson = LESSON_BY_ID[self.lesson.current]
        if not lesson.available(scene):
            return None
        return lesson.build(scene, self.lesson.hint)

    def view_options(self, scene: SkyScene) -> ViewOptions:
        theme = self.theme
        if self.beginner:
            lv = self.lesson_view(scene)
            layers = Layers(
                constellation_lines=False, labels=True, milky_way=self.layers.milky_way,
                asterisms=True, satellites=self.layers.satellites, deep_sky=True,
            )
            return ViewOptions(
                kind="window", center_az=self.win_az, fov=self.win_fov,
                bottom_alt=self.win_bottom, limiting_mag=self.beg_limit, theme=theme,
                half=self.ascii, ascii_symbols=self.ascii, beginner=True, max_labels=6,
                selected=self.selected,
                highlights=list(lv.highlights) if lv else [],
                guides=list(lv.guides) if lv else [],
                hint_circle=lv.hint_circle if lv else None,
                always_label=set(lv.labels) if lv else set(),
                light_pollution={"město": 0.8, "předměstí": 0.5, "venkov": 0.15}[
                    self.cfg.display.sky_quality
                ],
                layers=layers,
            )
        return ViewOptions(
            kind="full" if self.adv_view == "full" else "direction",
            center_az=self.dir_az, center_alt=self.dir_alt, fov=self.dir_fov,
            limiting_mag=self.adv_limit, theme=theme, half=self.ascii,
            ascii_symbols=self.ascii, beginner=False, selected=self.selected,
            cursor=self.cursor,
            light_pollution={"město": 0.6, "předměstí": 0.4, "venkov": 0.1}[
                self.cfg.display.sky_quality
            ],
            layers=self.layers,
        )

    # ------------------------------------------------------------------ actions
    def toggle_mode(self) -> str:
        self.mode = "advanced" if self.beginner else "beginner"
        self.cfg.display.mode = self.mode
        self.save()
        return "pokročilý režim (mapa)" if self.mode == "advanced" else "začátečnický režim"

    def toggle_night(self) -> None:
        self.night = not self.night
        self.cfg.display.night = self.night
        self.save()

    def rotate(self, degrees: float) -> None:
        if self.beginner:
            self.win_az = (self.win_az + degrees) % 360.0
        else:
            self.dir_az = (self.dir_az + degrees) % 360.0

    def look(self, degrees: float) -> None:
        if self.beginner:
            self.win_bottom = max(-10.0, min(60.0, self.win_bottom + degrees))
        else:
            self.dir_alt = max(-20.0, min(90.0, self.dir_alt + degrees))

    def zoom(self, zoom_in: bool) -> None:
        factor = 0.8 if zoom_in else 1.25
        if self.beginner:
            lo, hi = WINDOW_FOV_RANGE
            self.win_fov = max(lo, min(hi, self.win_fov * factor))
        else:
            if self.adv_view == "full":
                self.adv_view = "direction"
                self.dir_az, self.dir_alt = self.cursor[1], max(10.0, self.cursor[0])
                return
            lo, hi = DIRECTION_FOV_RANGE
            new = self.dir_fov * factor
            if not zoom_in and new > hi:
                self.adv_view = "full"
                return
            self.dir_fov = max(lo, min(hi, new))

    def face(self, az: float) -> None:
        if self.beginner:
            self.win_az = az
        else:
            self.adv_view = "direction"
            self.dir_az = az
            self.dir_alt = 30.0

    def toggle_view(self) -> str:
        self.adv_view = "direction" if self.adv_view == "full" else "full"
        return "celá obloha" if self.adv_view == "full" else "pohled jedním směrem"

    def toggle_layer(self, name: str) -> str:
        names = {
            "constellation_lines": "čáry souhvězdí",
            "constellation_borders": "hranice souhvězdí",
            "milky_way": "Mléčná dráha",
            "ecliptic": "ekliptika",
            "labels": "popisky",
            "below_horizon": "obloha pod obzorem",
        }
        if name == "grid":
            order: list[str | None] = [None, "altaz", "eq"]
            self.layers.grid = order[(order.index(self.layers.grid) + 1) % 3]
            self.cfg.layers.grid = self.layers.grid or "none"  # type: ignore[assignment]
            self.save()
            return {None: "síť vypnuta", "altaz": "síť: výška/azimut",
                    "eq": "síť: rektascenze/deklinace"}[self.layers.grid]
        value = not getattr(self.layers, name)
        setattr(self.layers, name, value)
        setattr(self.cfg.layers, name, value)
        self.save()
        return f"{names.get(name, name)}: {'zapnuto' if value else 'vypnuto'}"

    def change_magnitude(self, delta: float) -> str:
        if self.beginner:
            self.beg_limit = max(1.0, min(6.5, self.beg_limit + delta))
            self.cfg.display.beginner_limiting_mag = round(self.beg_limit, 1)
            value = self.beg_limit
        else:
            self.adv_limit = max(1.0, min(7.5, self.adv_limit + delta))
            self.cfg.display.limiting_mag = round(self.adv_limit, 1)
            value = self.adv_limit
        self.save()
        return f"mezní magnituda {num(value)}"

    def move_cursor(self, d_alt: float, d_az: float) -> None:
        alt, az = self.cursor
        alt = max(-10.0, min(90.0, alt + d_alt))
        az = (az + d_az / max(0.2, math.cos(math.radians(alt)))) % 360
        self.cursor = (alt, az)
        if self.adv_view == "direction":
            half = self.dir_fov / 2.5
            daz = (az - self.dir_az + 180) % 360 - 180
            if abs(daz) > half:
                self.dir_az = (self.dir_az + d_az) % 360
            if abs(alt - self.dir_alt) > half * 0.6:
                self.dir_alt = max(-20.0, min(90.0, self.dir_alt + d_alt))

    def cursor_step(self) -> float:
        return 2.0 if self.adv_view == "full" else max(0.5, self.dir_fov / 40.0)

    def select(self, ref: ObjectRef | None) -> None:
        self.selected = ref
        if ref is not None:
            pos = self.scene().altaz_of(ref)
            if pos is not None:
                self.cursor = pos

    def point_at(self, ref: ObjectRef) -> tuple[bool, str]:
        """Turn the view towards ``ref``. Returns (visible, Czech message)."""
        scene = self.scene()
        pos = scene.altaz_of(ref)
        self.select(ref)
        if pos is None:
            return False, "objekt nenalezen"
        alt, az = pos
        if self.beginner:
            self.win_az = az
            self.win_bottom = max(-6.0, min(50.0, alt - 25.0))
        else:
            if self.adv_view == "direction":
                self.dir_az, self.dir_alt = az, max(0.0, alt)
        if alt > 0:
            return True, ""
        # when does it rise?
        info = self.rise_set_for(ref)
        if info and info.rise:
            return False, f"Teď je pod obzorem, vyjde v {hm(info.rise, self.location.zone)}."
        return False, "Teď je pod obzorem a dnes nevyjde."

    def rise_set_for(self, ref: ObjectRef) -> RiseSet | None:
        scene = self.scene()
        try:
            if ref.kind == "body":
                return rise_transit_set(BODY_BY_ID[ref.key], self.now(), self.location)
            if ref.kind in ("star", "dso", "constellation", "asterism"):
                from obloha.core.objects import object_info

                info = object_info(scene, ref)
                if info is None:
                    return None
                return rise_transit_set((info.ra, info.dec), self.now(), self.location)
        except OutOfRangeError:
            return None
        return None

    def set_location(self, loc: Location, remember: bool = True) -> None:
        self.location = loc
        self._scene = None
        self._tonight = None
        self._events = None
        self._passes = None
        self.weather = None
        if remember:
            place = Place.from_location(loc)
            self.cfg.location = place
            self.st.add_recent(place)
            self.save()

    def add_favorite(self, loc: Location) -> bool:
        place = Place.from_location(loc)
        if any((p.lat, p.lon) == (place.lat, place.lon) for p in self.cfg.favorites):
            return False
        self.cfg.favorites.append(place)
        self.save()
        return True

    def remove_favorite(self, index: int) -> None:
        if 0 <= index < len(self.cfg.favorites):
            del self.cfg.favorites[index]
            self.save()

    def next_favorite(self) -> Location | None:
        places = self.cfg.favorites or self.st.recent
        if not places:
            return None
        coords = [(p.lat, p.lon) for p in places]
        cur = (self.location.lat, self.location.lon)
        idx = (coords.index(cur) + 1) % len(places) if cur in coords else 0
        return places[idx].to_location()

    def found(self) -> str:
        scene = self.scene()
        nxt = self.lesson.found(scene)
        self.st.lessons_done = list(self.lesson.done)
        self.save()
        if nxt is None:
            self.lesson_active = False
            return "Výborně! Další úkoly budou, až bude vidět víc objektů."
        self._apply_lesson_view(scene)
        return f"Výborně! Další úkol: {nxt.title}"

    def start_lessons(self) -> str:
        scene = self.scene()
        self.lesson_active = not self.lesson_active
        if not self.lesson_active:
            return "úkoly skryty"
        lesson = self.lesson.start(scene)
        if lesson is None:
            self.lesson_active = False
            return "Teď není nic vidět (je den nebo zataženo). Zkus to večer."
        if not self.beginner:
            self.mode = "beginner"
        self._apply_lesson_view(scene)
        return lesson.title

    def _apply_lesson_view(self, scene: SkyScene) -> None:
        lv = self.lesson_view(scene)
        if lv is None:
            return
        self.win_az = lv.look_az
        top = lv.look_alt
        if top > 40:
            self.win_bottom = max(-6.0, min(45.0, top - 30.0))
        else:
            self.win_bottom = -6.0

    def hint(self) -> int:
        level = self.lesson.next_hint()
        self._apply_lesson_view(self.scene())
        return level

    # ------------------------------------------------------------------ texts
    def time_text(self) -> str:
        from obloha.ui.formatting import date_long, hms, tz_abbr

        now = self.now()
        zone = self.display_zone
        state = "● živě" if self.time.live else f"◼ {self.time.status}"
        return f"{state} · {date_long(now, zone)} · {hms(now, zone)} {tz_abbr(now, zone)}"

    @property
    def display_zone(self) -> Any:
        if self.cfg.display.time_zone == "observer":
            return datetime.now().astimezone().tzinfo
        return self.location.zone

    def beginner_status(self, scene: SkyScene) -> str:
        sun = scene.sun_alt
        phase = sky_phase(sun)
        if phase == "astronomická noc":
            sky = "Je tma (astronomická noc)."
        elif phase == "den":
            sky = "Je den, hvězdy nejsou vidět."
        else:
            sky = f"Šero ({phase}), objevují se první hvězdy." if sun < -3 else (
                f"Šero ({phase})."
            )
        moon = scene.bodies["moon"]
        mi = self.moon_now()
        if moon.alt > 0:
            disturb = "hodně přisvítí" if mi.illumination > 0.7 else (
                "trochu přisvítí" if mi.illumination > 0.3 else "neruší")
            moon_txt = f"Měsíc je nad obzorem a {disturb}."
        else:
            rs = rise_transit_set(BODY_BY_ID["moon"], self.now(), self.location, hours=14)
            if rs.rise:
                disturb = "a trochu přisvítí" if mi.illumination > 0.3 else ""
                moon_txt = f"Měsíc vyjde v {hm(rs.rise, self.location.zone)} {disturb}".strip() + "."
            else:
                moon_txt = "Měsíc dnes v noci nevyjde."
        cond = self.conditions_text(scene)
        return f"{sky}  {moon_txt}  {cond}"

    def conditions_text(self, scene: SkyScene) -> str:
        score = self.score_now(scene)
        if score is None:
            return "Počasí: neznámé"
        word = score_word(score)
        mark = "✓" if score >= 55 else "✗" if score < 30 else "~"
        return f"Podmínky: {word} {mark}"

    def score_now(self, scene: SkyScene) -> int | None:
        from obloha.core.weather import cloud_factor, darkness_factor, moon_factor

        d = darkness_factor(scene.sun_alt)
        mi = self.moon_now()
        mf = moon_factor(mi.illumination, scene.bodies["moon"].alt)
        cf = 1.0
        if self.weather and self.weather.forecast:
            hw = self.weather.forecast.at(scene.when)
            if hw:
                cf = cloud_factor(hw)
        return round(100 * d * mf * cf)

    def moon_now(self) -> MoonInfo:
        key = self.now().replace(minute=0, second=0, microsecond=0)
        cached = getattr(self, "_moon_cache", None)
        if cached and cached[0] == key:
            return cached[1]  # type: ignore[no-any-return]
        mi = moon_info(self.now())
        self._moon_cache = (key, mi)
        return mi

    def advanced_status(self, scene: SkyScene) -> tuple[str, str]:
        from obloha.core.bodies import moon_symbol

        sun = scene.bodies["sun"]
        mi = self.moon_now()
        trend = "přibývá" if mi.waxing else "ubývá"
        line1 = (
            f"☉ {num(sun.alt, 0)}° {sky_phase(sun.alt)}   "
            f"☽ {moon_symbol(scene.moon_phase, self.ascii)} {mi.illumination * 100:.0f} % {trend}"
        )
        highlight = self.highlight_text(scene)
        if highlight:
            line1 += f"   {highlight}"
        line1 += f"   mez. mag. {num(self.adv_limit)}"
        score = self.score_now(scene)
        cloud = ""
        if self.weather and self.weather.forecast:
            hw = self.weather.forecast.at(scene.when)
            if hw:
                cloud = f"  oblačnost {hw.cloud:.0f} %"
        else:
            cloud = "  počasí nedostupné"
        bar_txt = ""
        if score is not None:
            from obloha.ui.formatting import bar

            bar_txt = f"pozorovatelnost {bar(score / 100)} {score}"
        line2 = f"{self.location.coords_text()}   {bar_txt}{cloud}"
        return line1, line2

    def highlight_text(self, scene: SkyScene) -> str:
        """The most interesting thing right now (e.g. ``♄ Saturn u opozice``)."""
        best = None
        for b in scene.bodies.values():
            if b.info.kind != "planet" or b.alt < 0:
                continue
            if b.elongation > 165:
                text = f"{b.info.symbol} {b.name} u opozice"
            else:
                text = f"{b.info.symbol} {b.name} nad obzorem"
            key = (b.elongation > 165, -b.mag)
            if best is None or key > best[0]:
                best = (key, text)
        return best[1] if best else ""

    # ------------------------------------------------------------------ heavy data
    def tonight(self) -> TonightData:
        start = night_start(self.now(), self.location)
        key = (start, self.location, self.weather is not None)
        if self._tonight is not None and self._tonight_key == key:
            return self._tonight
        tw = twilight(start, self.location)
        mi = moon_info(start + timedelta(hours=10))
        mrs = rise_transit_set(BODY_BY_ID["moon"], start, self.location)
        planets = planets_tonight(start, self.location)
        begin = tw.sunset or start + timedelta(hours=6)
        end = tw.sunrise or start + timedelta(hours=18)
        forecast = self.weather.forecast if self.weather else None
        scores = night_scores(begin, end, self.location, forecast, mi.illumination)
        status = self.weather.status if self.weather else "počasí není k dispozici"
        data = TonightData(start, tw, mi, mrs, planets, scores, best_window(scores), status)
        self._tonight = data
        self._tonight_key = key
        return data

    def events(self, days: int | None = None) -> list[Event]:
        start = night_start(self.now(), self.location)
        months = self.cfg.events.months
        end = start + timedelta(days=days or round(30.5 * months))
        key = (start.date(), end.date(), self.location)
        if self._events is not None and self._events_key == key:
            return self._events
        self._events = compute_events(
            start, end, self.location,
            moon_limit=self.cfg.events.moon_conjunction_deg,
            planet_limit=self.cfg.events.planet_conjunction_deg,
        )
        self._events_key = key
        return self._events

    def passes(self) -> list[SatPass]:
        start = self.now().replace(second=0, microsecond=0) - timedelta(minutes=10)
        key = (start.replace(minute=0), self.location, len(self.sats))
        if self._passes is not None and self._passes_key == key:
            return self._passes
        self._passes = passes_for_all(
            self.sats[:20], start, self.location, days=7,
            min_alt=self.cfg.satellites.min_altitude,
        ) if self.sats else []
        self._passes_key = key
        return self._passes

    def reload_satellites(self) -> None:
        self.sats = self.sat_store.load()
        self.sat_status = self.sat_store.age_text()
        self._passes = None
        self._scene = None

    def sat_age_warning(self) -> str | None:
        if not self.sats:
            return "Nejsou stažené dráhy satelitů. Připoj se k internetu (aktualizace proběhne sama)."
        if self.sat_store.is_stale(datetime.now(UTC)):
            return "Pozor: dráhy jsou starší než 7 dní, časy přeletů mohou být nepřesné."
        return None

    # ------------------------------------------------------------------ persistence
    def save(self) -> None:
        if not self.persist:
            return
        try:
            save_config(self.cfg, self.doc)
            save_state(self.st)
        except OSError:  # pragma: no cover - read-only config dir
            self.message = "Konfiguraci se nepodařilo uložit."
