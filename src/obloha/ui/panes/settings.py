"""Screen 5: settings (places, display, layers, satellites, network)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Input, Label, Select, Static, Switch

if TYPE_CHECKING:
    from obloha.ui.app import ObloApp

LAYER_LABELS = {
    "constellation_lines": "čáry souhvězdí",
    "constellation_borders": "hranice souhvězdí",
    "labels": "popisky",
    "milky_way": "Mléčná dráha",
    "ecliptic": "ekliptika",
    "planets": "planety",
    "moon": "Měsíc",
    "sun": "Slunce",
    "satellites": "satelity",
    "below_horizon": "obloha pod obzorem",
}


class SettingsPane(VerticalScroll):
    DEFAULT_CSS = """
    SettingsPane { height: 1fr; padding: 0 1; }
    SettingsPane .section { border: round $ob-border; border-title-color: $ob-accent;
        height: auto; padding: 0 1; margin-bottom: 1; }
    SettingsPane .row { height: auto; margin: 0 0 0 0; }
    SettingsPane .row Label { width: 26; padding: 1 1 0 0; }
    SettingsPane .row Select { width: 30; }
    SettingsPane .row Input { width: 14; }
    SettingsPane Button { margin: 0 1 0 0; min-width: 8; }
    SettingsPane Checkbox { width: auto; }
    SettingsPane #layers { layout: grid; grid-size: 2; height: auto; }
    .-mobile SettingsPane #layers { grid-size: 1; }
    .-mobile SettingsPane .row Label { width: 1fr; }
    """

    def __init__(self) -> None:
        super().__init__(id="settings-pane")
        self.places = Static(id="places-list")
        self._loading = False

    @property
    def oapp(self) -> ObloApp:
        return self.app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        model = self.oapp.model
        cfg = model.cfg
        with Vertical(classes="section", id="sec-places") as v:
            v.border_title = "MÍSTA"
            yield self.places
            with Horizontal(classes="row"):
                yield Button("vybrat město (L)", id="set-pick")
                yield Button("přidat aktuální k oblíbeným", id="set-fav-add")
                yield Button("nastavit jako výchozí", id="set-default")
        with Vertical(classes="section") as v:
            v.border_title = "ZOBRAZENÍ"
            with Horizontal(classes="row"):
                yield Label("téma")
                yield Select([("tmavé", "dark"), ("světlé", "light")], value=cfg.display.theme,
                             allow_blank=False, id="set-theme")
            with Horizontal(classes="row"):
                yield Label("noční vidění (n)")
                yield Switch(value=model.night, id="set-night")
            with Horizontal(classes="row"):
                yield Label("kde pozoruješ (mez. magnituda)")
                yield Select([("město (3,5)", "město"), ("předměstí (4,8)", "předměstí"),
                              ("venkov (6,0)", "venkov")], value=cfg.display.sky_quality,
                             allow_blank=False, id="set-quality")
            with Horizontal(classes="row"):
                yield Label("mezní magnituda mapy")
                yield Input(str(cfg.display.limiting_mag), id="set-limit", type="number")
            with Horizontal(classes="row"):
                yield Label("jednotky RA/Dec")
                yield Select([("stupně (°)", "deg"), ("hodiny a minuty (h:m)", "hm")],
                             value=cfg.display.units, allow_blank=False, id="set-units")
            with Horizontal(classes="row"):
                yield Label("čas v záhlaví")
                yield Select([("pásmo zvoleného místa", "place"), ("můj čas (pozorovatel)",
                              "observer")], value=cfg.display.time_zone, allow_blank=False,
                             id="set-tz")
            with Horizontal(classes="row"):
                yield Label("bezpečný režim znaků")
                yield Switch(value=model.ascii, id="set-ascii")
            with Horizontal(classes="row"):
                yield Label("překreslení za sekundu")
                yield Input(str(cfg.display.fps), id="set-fps", type="number")
        with Vertical(classes="section") as v:
            v.border_title = "VRSTVY MAPY (pokročilý režim)"
            with Vertical(id="layers"):
                for key, label in LAYER_LABELS.items():
                    yield Checkbox(label, value=bool(getattr(model.layers, key)),
                                   id=f"layer-{key}")
        with Vertical(classes="section") as v:
            v.border_title = "SATELITY"
            with Horizontal(classes="row"):
                yield Label("skupiny Starlink")
                yield Switch(value=cfg.satellites.starlink, id="set-starlink")
            with Horizontal(classes="row"):
                yield Label("obnova drah (hodiny)")
                yield Input(str(cfg.satellites.refresh_hours), id="set-refresh", type="number")
            with Horizontal(classes="row"):
                yield Button("aktualizovat dráhy teď", id="set-tle")
        with Vertical(classes="section") as v:
            v.border_title = "SÍŤ"
            with Horizontal(classes="row"):
                yield Label("offline režim")
                yield Switch(value=model.offline, id="set-offline")
            with Horizontal(classes="row"):
                yield Label("předpověď počasí")
                yield Switch(value=cfg.network.weather, id="set-weather")
        yield Static("Nastavení se ukládá hned do ~/.config/obloha/config.toml.", id="set-note")

    def refresh_content(self, full: bool = False) -> None:
        model = self.oapp.model
        t = model.theme
        loc = model.location
        lines = [f"[b]aktuální:[/b] {escape(loc.name)}"
                 + (f", {escape(loc.label)}" if loc.label else "")
                 + f"  [#{t.muted:06x}]{loc.coords_text()} · {loc.tz}[/]",
                 f"[#{t.muted:06x}]výchozí: {escape(model.cfg.location.name)}[/]", ""]
        if model.cfg.favorites:
            lines.append("[b]oblíbená:[/b]")
            for i, p in enumerate(model.cfg.favorites):
                lines.append(
                    f"  [@click=app.use_favorite({i})]{escape(p.name)}[/]"
                    + (f" [#{t.muted:06x}]{escape(p.label)}[/]" if p.label else "")
                    + f"  [@click=app.remove_favorite({i})][#{t.bad:06x}]✕ odebrat[/][/]"
                )
        else:
            lines.append(f"[#{t.muted:06x}]Žádná oblíbená místa. Přidej aktuální tlačítkem níže.[/]")
        self.places.update("\n".join(lines))

    # ------------------------------------------------------------------ events
    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        bid = event.button.id
        app = self.oapp
        model = app.model
        if bid == "set-pick":
            app.run_named_action("place")
        elif bid == "set-fav-add":
            ok = model.add_favorite(model.location)
            app.notify("přidáno k oblíbeným" if ok else "už je mezi oblíbenými")
        elif bid == "set-default":
            from obloha.config import Place

            model.cfg.location = Place.from_location(model.location)
            model.save()
            app.notify(f"výchozí místo: {model.location.name}")
        elif bid == "set-tle":
            app.refresh_satellites(force=True)
        self.refresh_content()

    def on_select_changed(self, event: Select.Changed) -> None:
        model = self.oapp.model
        value = event.value
        if not isinstance(value, str):
            return
        if event.select.id == "set-theme":
            model.cfg.display.theme = value  # type: ignore[assignment]
        elif event.select.id == "set-quality":
            model.cfg.display.sky_quality = value  # type: ignore[assignment]
            model.cfg.display.beginner_limiting_mag = None
            model.beg_limit = model.cfg.beginner_limit()
        elif event.select.id == "set-units":
            model.cfg.display.units = value  # type: ignore[assignment]
        elif event.select.id == "set-tz":
            model.cfg.display.time_zone = value  # type: ignore[assignment]
        model.save()
        self.oapp.apply_theme()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        model = self.oapp.model
        sid = event.switch.id
        if sid == "set-night":
            if model.night != event.value:
                model.toggle_night()
        elif sid == "set-ascii":
            model.ascii = event.value
            model.cfg.display.ascii = event.value
        elif sid == "set-starlink":
            model.cfg.satellites.starlink = event.value
        elif sid == "set-offline":
            model.offline = event.value
            model.cfg.network.offline = event.value
        elif sid == "set-weather":
            model.cfg.network.weather = event.value
        model.save()
        self.oapp.apply_theme()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        model = self.oapp.model
        key = (event.checkbox.id or "").removeprefix("layer-")
        if key in LAYER_LABELS:
            setattr(model.layers, key, event.value)
            setattr(model.cfg.layers, key, event.value)
            model.save()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._apply_input(event.input)

    def on_input_changed(self, event: Input.Changed) -> None:
        self._apply_input(event.input)

    def _apply_input(self, widget: Input) -> None:
        model = self.oapp.model
        try:
            value = float(widget.value.replace(",", "."))
        except ValueError:
            return
        if widget.id == "set-limit" and 1 <= value <= 7.5:
            model.adv_limit = value
            model.cfg.display.limiting_mag = value
        elif widget.id == "set-fps" and 0.1 <= value <= 10:
            model.cfg.display.fps = value
            self.oapp.restart_ticker()
        elif widget.id == "set-refresh" and value > 0:
            model.cfg.satellites.refresh_hours = value
        else:
            return
        model.save()
