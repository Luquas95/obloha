"""Modal dialogs: help, search, place picker, compare, time, identify, detail, glossary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, ClassVar

from rich.markup import escape
from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, OptionList, Static
from textual.widgets.option_list import Option

from obloha.beginner.describe import direction_name, fist_text
from obloha.beginner.glossary import explain
from obloha.beginner.identify import Identification, identify, parse_direction
from obloha.core.bodies import BODIES
from obloha.core.cities import City, city_db, parse_coordinates, timezone_at
from obloha.core.coords import format_dec, format_ra
from obloha.core.location import Location
from obloha.core.objects import object_info
from obloha.core.sky import ObjectRef
from obloha.core.textnorm import fold
from obloha.render.sky import compass_name
from obloha.ui.formatting import hm, num
from obloha.ui.panes.lists import glossary_markup

if TYPE_CHECKING:
    from obloha.ui.app import ObloApp

MODAL_CSS = """
ModalScreen { align: center middle; background: $ob-bg 60%; }
ModalScreen > .dialog { width: 76; max-width: 100%; height: auto; max-height: 90%;
    border: round $ob-accent; border-title-color: $ob-accent; border-title-style: bold;
    background: $ob-panel; padding: 0 1; }
ModalScreen .hint { color: $ob-muted; height: auto; }
ModalScreen Input { margin: 0 0 1 0; }
ModalScreen OptionList { height: auto; max-height: 14; }
ModalScreen Button { margin: 0 1 0 0; min-width: 8; }
ModalScreen .buttons { height: auto; margin-top: 1; }
"""


class BaseModal(ModalScreen[Any]):
    SCOPED_CSS = False
    DEFAULT_CSS = MODAL_CSS
    BINDINGS: ClassVar = [("escape", "dismiss_none", "Zavřít")]

    @property
    def oapp(self) -> ObloApp:
        return self.app  # type: ignore[return-value]

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------- help
class HelpScreen(BaseModal):
    def compose(self) -> ComposeResult:
        km = self.oapp.keymap
        rows = km.help_rows()
        with VerticalScroll(classes="dialog") as v:
            v.border_title = "NÁPOVĚDA · klávesové zkratky"
            current = None
            lines = []
            for ctx, keys, desc in rows:
                if ctx != current:
                    lines.append(f"\n[b]{escape(ctx)}[/b]")
                    current = ctx
                lines.append(f"  [b]{escape(keys):<12}[/b] {escape(desc)}")
            lines.append(
                "\n[b]Dotyk[/b]\n  klepnutí = výběr objektu · tažení = posun pohledu · "
                "dvojklepnutí = přiblížení\n\nZkratky jde přemapovat v config.toml v sekci [keys]."
                "\nEsc zavře toto okno."
            )
            yield Static("\n".join(lines).lstrip())

    def on_key(self, event: events.Key) -> None:
        if event.key in ("q", "question_mark", "H"):
            event.stop()
            self.dismiss(None)


# ---------------------------------------------------------------------- search
@dataclass(frozen=True)
class SearchHit:
    ref: ObjectRef
    label: str
    kind: str


def search_objects(app: ObloApp, query: str, limit: int = 12) -> list[SearchHit]:
    """Search stars, constellations, planets, Moon, Sun, deep sky and satellites."""
    q = fold(query)
    if not q:
        return []
    model = app.model
    cat = model.scene().cat
    hits: list[tuple[int, SearchHit]] = []
    en_names = {
        "sun": "sun",
        "moon": "moon",
        "mercury": "mercury",
        "venus": "venus",
        "mars": "mars",
        "jupiter": "jupiter",
        "saturn": "saturn",
        "uranus": "uranus",
        "neptune": "neptune",
    }
    for b in BODIES:
        names = {fold(b.name), en_names[b.id]}
        for n in names:
            if n.startswith(q):
                rank = 0 if n == q else 1
                kind = "Měsíc" if b.id == "moon" else "Slunce" if b.id == "sun" else "planeta"
                hits.append((rank, SearchHit(ObjectRef.body(b.id), b.name, kind)))
                break
    seen: set[ObjectRef] = set()
    for text, kind, idx in cat.search_index:
        if not (text.startswith(q) or f" {q}" in f" {text}"):
            continue
        rank = 2 if text.startswith(q) else 4
        if kind == "star":
            ref = ObjectRef.star(idx)
            label = cat.star_label(idx)
            kind_cs = "hvězda"
            rank += 0 if idx in cat.cs_star_names else 1
        elif kind == "constellation":
            ref = ObjectRef("constellation", str(idx))
            label = cat.constellations[idx].name_cs
            kind_cs = "souhvězdí"
        else:
            d = cat.deep_sky[idx]
            ref = ObjectRef("dso", d.id)
            label = d.name
            kind_cs = d.kind
        if ref in seen:
            continue
        seen.add(ref)
        hits.append((rank, SearchHit(ref, label, kind_cs)))
    for sat in model.sats[:500]:
        if fold(sat.name).startswith(q):
            hits.append((3, SearchHit(ObjectRef("sat", sat.name), sat.name, "družice")))
    hits.sort(key=lambda h: (h[0], h[1].label))
    out: list[SearchHit] = []
    labels: set[tuple[str, str]] = set()
    for _, h in hits:
        if (h.label, h.kind) in labels:
            continue
        labels.add((h.label, h.kind))
        out.append(h)
    return out[:limit]


class SearchScreen(BaseModal):
    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog") as v:
            v.border_title = "HLEDAT OBJEKT"
            yield Input(placeholder="např. vega, saturn, orion, plejady…", id="search-input")
            yield OptionList(id="search-results")
            yield Static("Enter vybrat · Esc zavřít · stačí psát bez diakritiky", classes="hint")

    def on_mount(self) -> None:
        self.hits: list[SearchHit] = []
        self.query_one(Input).focus()

    @on(Input.Changed, "#search-input")
    def _changed(self, event: Input.Changed) -> None:
        self.hits = search_objects(self.oapp, event.value)
        ol = self.query_one(OptionList)
        ol.clear_options()
        for h in self.hits:
            ol.add_option(Option(f"{h.label}  [dim]{h.kind}[/dim]"))
        if self.hits:
            ol.highlighted = 0

    @on(Input.Submitted, "#search-input")
    def _submitted(self) -> None:
        ol = self.query_one(OptionList)
        idx = ol.highlighted if ol.highlighted is not None else 0
        if self.hits:
            self.dismiss(self.hits[idx].ref)

    @on(OptionList.OptionSelected)
    def _selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self.hits[event.option_index].ref)

    def on_key(self, event: events.Key) -> None:
        ol = self.query_one(OptionList)
        if event.key in ("down", "up") and self.hits:
            event.stop()
            cur = ol.highlighted or 0
            ol.highlighted = max(
                0, min(len(self.hits) - 1, cur + (1 if event.key == "down" else -1))
            )


# ---------------------------------------------------------------------- places
class PlaceScreen(BaseModal):
    """City search with suggestions; Tab switches favourites / recent places."""

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog") as v:
            v.border_title = "VÝBĚR MÍSTA"
            yield Input(
                placeholder="město nebo souřadnice (50.08, 14.44 / 50°4'N 14°26'E)",
                id="place-input",
            )
            yield Static("", id="place-mode", classes="hint")
            yield OptionList(id="place-results")
            with Horizontal(classes="buttons"):
                yield Button("vybrat", id="place-ok", variant="primary")
                yield Button("★ oblíbené", id="place-fav")
                yield Button("+ porovnat", id="place-compare")
                yield Button("porovnání měst", id="place-show-compare")
            yield Static(
                "Tab oblíbená ↔ poslední · Enter vybrat · Ctrl+O přidat do porovnání",
                classes="hint",
            )

    def on_mount(self) -> None:
        self.mode = "search"
        self.results: list[Location] = []
        self.labels: list[str] = []
        self._show_list("favorites" if self.oapp.model.cfg.favorites else "recent")
        self.query_one(Input).focus()

    def _show_list(self, mode: str) -> None:
        model = self.oapp.model
        self.mode = mode
        places = model.cfg.favorites if mode == "favorites" else model.st.recent
        self.results = [p.to_location() for p in places]
        self.labels = [f"{p.name}" + (f", {p.label}" if p.label else "") for p in places]
        title = "★ oblíbená místa" if mode == "favorites" else "◷ naposledy použitá"
        if not self.results:
            title += " (zatím žádná)"
        self.query_one("#place-mode", Static).update(title)
        self._fill()

    def _fill(self) -> None:
        ol = self.query_one(OptionList)
        ol.clear_options()
        for label in self.labels:
            ol.add_option(Option(escape(label)))
        if self.labels:
            ol.highlighted = 0

    @on(Input.Changed, "#place-input")
    def _changed(self, event: Input.Changed) -> None:
        text = event.value.strip()
        if not text:
            self._show_list("favorites" if self.oapp.model.cfg.favorites else "recent")
            return
        self.mode = "search"
        self.results, self.labels = [], []
        if re.search(r"\d", text):
            try:
                lat, lon = parse_coordinates(text)
            except ValueError as exc:
                self.query_one("#place-mode", Static).update(f"souřadnice: {exc}")
            else:
                tz = timezone_at(lat, lon)
                near = city_db().nearest(lat, lon)
                loc = Location(
                    f"{num(lat, 3)}, {num(lon, 3)}", lat, lon, 0.0, tz, f"u obce {near.name}"
                )
                self.results.append(loc)
                self.labels.append(
                    f"souřadnice {num(lat, 4)}° {num(lon, 4)}° · {tz} (blízko {near.label})"
                )
                self.query_one("#place-mode", Static).update("ruční souřadnice")
        else:
            cities: list[City] = city_db().search(text, 10)
            self.results = [c.to_location() for c in cities]
            self.labels = [c.label for c in cities]
            self.query_one("#place-mode", Static).update(
                f"nalezeno {len(cities)}" if cities else "nic nenalezeno, zkus jiný zápis"
            )
        self._fill()

    def _current(self) -> Location | None:
        ol = self.query_one(OptionList)
        idx = ol.highlighted if ol.highlighted is not None else 0
        return self.results[idx] if 0 <= idx < len(self.results) else None

    @on(Input.Submitted, "#place-input")
    def _submitted(self) -> None:
        loc = self._current()
        if loc:
            self.dismiss(loc)

    @on(OptionList.OptionSelected)
    def _selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self.results[event.option_index])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        loc = self._current()
        if event.button.id == "place-ok" and loc:
            self.dismiss(loc)
        elif event.button.id == "place-fav" and loc:
            ok = self.oapp.model.add_favorite(loc)
            self.app.notify(f"{loc.name} přidáno k oblíbeným" if ok else "už je v oblíbených")
        elif event.button.id == "place-compare" and loc:
            self.oapp.add_compare(loc)
        elif event.button.id == "place-show-compare":
            self.dismiss(None)
            self.oapp.run_named_action("compare")

    def on_key(self, event: events.Key) -> None:
        ol = self.query_one(OptionList)
        if event.key == "tab":
            event.stop()
            event.prevent_default()
            self.query_one(Input).value = ""
            self._show_list("recent" if self.mode == "favorites" else "favorites")
        elif event.key == "ctrl+o":
            event.stop()
            loc = self._current()
            if loc:
                self.oapp.add_compare(loc)
        elif event.key in ("down", "up") and self.results:
            event.stop()
            cur = ol.highlighted or 0
            ol.highlighted = max(
                0, min(len(self.results) - 1, cur + (1 if event.key == "down" else -1))
            )


class CompareScreen(BaseModal):
    SCOPED_CSS = False
    """Table comparing 2–5 places for tonight (and the next eclipse)."""

    DEFAULT_CSS = (
        MODAL_CSS
        + """
    CompareScreen > .dialog { width: 110; }
    CompareScreen DataTable { height: auto; max-height: 20; }
    """
    )

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog") as v:
            v.border_title = "POROVNÁNÍ MĚST · dnešní noc"
            yield DataTable(id="compare-table", zebra_stripes=True)
            yield Static("", id="compare-note", classes="hint")
            with Horizontal(classes="buttons"):
                yield Button("vyprázdnit", id="compare-clear")
                yield Button("zavřít", id="compare-close")

    def on_mount(self) -> None:
        self._fill()

    def _fill(self) -> None:
        from obloha.ui.compare import compare_rows

        table = self.query_one(DataTable)
        table.clear(columns=True)
        places = self.oapp.compare_places()
        note = self.query_one("#compare-note", Static)
        if len(places) < 2:
            note.update(
                "Přidej aspoň dvě místa: v dialogu místa (L) tlačítkem „+ porovnat“. "
                "Aktuální místo je zahrnuté automaticky."
            )
        else:
            note.update("Časy v pásmu každého místa. Měsíc a ISS pro dnešní noc.")
        table.add_column("")
        for p in places:
            table.add_column(p.name[:16])
        for label, values in compare_rows(self.oapp.model, places):
            table.add_row(label, *values)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "compare-clear":
            self.oapp.model.st.compare = []
            self.oapp.model.save()
            self._fill()
        else:
            self.dismiss(None)


# ---------------------------------------------------------------------- time
def parse_time_input(text: str, now: datetime, zone: Any) -> datetime:
    """Parse ``2026-10-01 21:00``, ``1. 10. 2026 21:00``, ``21:00``, ``+2h``, ``-3d``,
    ``zítra 21:00``, ``teď``."""
    t = text.strip().lower()
    if t in ("", "ted", "teď", "now"):
        return now
    m = re.fullmatch(r"([+-])\s*(\d+(?:[.,]\d+)?)\s*(min|m|h|d|den|dny|dní|dni)", t)
    if m:
        value = float(m[2].replace(",", ".")) * (1 if m[1] == "+" else -1)
        unit = m[3]
        delta = (
            timedelta(minutes=value)
            if unit in ("min", "m")
            else (timedelta(hours=value) if unit == "h" else timedelta(days=value))
        )
        return now + delta
    local_now = now.astimezone(zone)
    base = local_now.date()
    if t.startswith(("zítra", "zitra")):
        base = base + timedelta(days=1)
        t = t.split(maxsplit=1)[1] if " " in t else "21:00"
    elif t.startswith(("dnes", "včera", "vcera")):
        if t.startswith(("včera", "vcera")):
            base = base - timedelta(days=1)
        t = t.split(maxsplit=1)[1] if " " in t else "21:00"
    patterns = [
        (r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ t](\d{1,2}):(\d{2}))?", "iso"),
        (r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})(?:\s+(\d{1,2}):(\d{2}))?", "cz"),
        (r"(\d{1,2}):(\d{2})", "time"),
    ]
    for pat, kind in patterns:
        m = re.fullmatch(pat, t)
        if not m:
            continue
        if kind == "iso":
            y, mo, d = int(m[1]), int(m[2]), int(m[3])
            h, mi = (int(m[4]), int(m[5])) if m[4] else (21, 0)
        elif kind == "cz":
            d, mo, y = int(m[1]), int(m[2]), int(m[3])
            h, mi = (int(m[4]), int(m[5])) if m[4] else (21, 0)
        else:
            y, mo, d = base.year, base.month, base.day
            h, mi = int(m[1]), int(m[2])
        return datetime(y, mo, d, h, mi, tzinfo=zone).astimezone(UTC)
    raise ValueError(
        "Nerozumím času. Zkus „2026-10-01 21:00“, „1. 10. 2026 21:00“, "
        "„21:00“, „zítra 5:30“ nebo „+2h“."
    )


class TimeScreen(BaseModal):
    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog") as v:
            v.border_title = "ZADAT DATUM A ČAS"
            yield Input(
                placeholder="2026-10-01 21:00 · 1. 10. 2026 21:00 · 21:00 · +2h · zítra 5:30",
                id="time-input",
            )
            yield Static(
                "Čas v pásmu zvoleného místa. Rozsah 1900–2049 (efemerida DE421). Prázdné = teď.",
                classes="hint",
                id="time-hint",
            )

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    @on(Input.Submitted)
    def _submit(self, event: Input.Submitted) -> None:
        model = self.oapp.model
        try:
            when = parse_time_input(event.value, model.now(), model.location.zone)
        except ValueError as exc:
            self.query_one("#time-hint", Static).update(f"[b]{escape(str(exc))}[/b]")
            return
        self.dismiss(when)


# ---------------------------------------------------------------------- identify
class IdentifyScreen(BaseModal):
    """ "Co je to za světlo?" for a pointed direction or a typed one."""

    def __init__(self, alt: float, az: float, moving: bool = False) -> None:
        super().__init__()
        self.alt = alt
        self.az = az
        self.moving = moving

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog") as v:
            v.border_title = "? CO JE TO ZA SVĚTLO"
            yield Static(id="identify-text")
            yield Input(
                placeholder="nebo napiš směr a výšku: „jihovýchod, 2 pěsti“", id="identify-input"
            )
            with Horizontal(classes="buttons"):
                yield Button("pohybuje se", id="identify-moving")
                yield Button("vybrat a ukázat", id="identify-select", variant="primary")
                yield Button("zavřít", id="identify-close")

    def on_mount(self) -> None:
        self.result: Identification | None = None
        self._update()

    def _update(self) -> None:
        model = self.oapp.model
        scene = model.scene()
        self.result = identify(
            scene, self.alt, self.az, moving=self.moving, user_limit=model.beg_limit + 0.5
        )
        t = model.theme
        lines = [
            f"[#{t.muted:06x}]Ukazuješ na {direction_name(self.az)}, {fist_text(self.alt)} "
            "nad obzor.[/]",
            "",
        ]
        if not self.result.candidates:
            lines.append("Tam teď nic jasného není. Zkus ukázat přesněji nebo napiš směr.")
        for k, c in enumerate(self.result.candidates):
            pct = f"jistota {c.probability * 100:.0f} %"
            if k == 0:
                sym = "●" if c.kind == "planeta" else "✦" if c.kind == "hvězda" else "▲"
                lines.append(
                    f"[b]{sym}  {escape(c.name)}[/b]  {escape(c.kind)}  [#{t.muted:06x}]{pct}[/]"
                )
                lines.append(escape(c.explanation))
                lines.append("")
            else:
                lines.append(f"[#{t.muted:06x}]nebo {escape(c.name)} ({escape(c.kind)}, {pct})[/]")
        for alt_text in self.result.alternatives:
            lines.append(f"[#{t.accent2:06x}]{escape(alt_text)}[/]")
        self.query_one("#identify-text", Static).update("\n".join(lines))

    @on(Input.Submitted, "#identify-input")
    def _typed(self, event: Input.Submitted) -> None:
        try:
            self.alt, self.az = parse_direction(event.value)
        except ValueError as exc:
            self.app.notify(str(exc), severity="warning")
            return
        self._update()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "identify-moving":
            self.moving = not self.moving
            event.button.label = "stojí na místě" if self.moving else "pohybuje se"
            self._update()
        elif event.button.id == "identify-select":
            best = self.result.best if self.result else None
            self.dismiss(best.ref if best else None)
        else:
            self.dismiss(None)


# ---------------------------------------------------------------------- detail & glossary
class DetailScreen(BaseModal):
    """Numbers (for advanced users) with glossary terms underlined."""

    def __init__(self, ref: ObjectRef) -> None:
        super().__init__()
        self.ref = ref

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog") as v:
            v.border_title = "PODROBNOSTI"
            yield Static(id="detail-text")
            yield Static("klepni na podtržený pojem pro vysvětlení · Esc zavřít", classes="hint")

    def on_mount(self) -> None:
        model = self.oapp.model
        scene = model.scene()
        info = object_info(scene, self.ref)
        t = model.theme
        col = f"#{t.accent:06x}"
        if info is None:
            self.query_one("#detail-text", Static).update("Objekt nenalezen.")
            return
        from obloha.beginner.describe import color_word, position_sentence

        lines = [f"[b]{escape(info.name)}[/b] · {escape(info.kind_cs)}"]
        if info.constellation:
            lines[0] += " · " + glossary_markup(f"souhvězdí {info.constellation}", col)
        lines.append("")
        lines.append(escape(position_sentence(info.alt, info.az)))
        if info.kind in ("star", "planet"):
            what = "planeta, nebliká" if info.is_planet else "hvězda, bliká"
            lines.append(escape(f"Barva: {color_word(info.bv, gender='f')}; {what}."))
        lines.append("")
        rows = []
        if info.mag is not None:
            rows.append(f"magnituda {num(info.mag)}")
        rows.append(f"výška {info.alt:.1f}°".replace(".", ","))
        rows.append(f"azimut {info.az:.1f}° ({compass_name(info.az)})".replace(".", ","))
        rows.append(f"rektascenze {format_ra(info.ra)}, deklinace {format_dec(info.dec)}")
        if info.distance_au is not None:
            rows.append(f"vzdálenost {num(info.distance_au, 3)} au")
        if info.illumination is not None and info.kind != "sun":
            rows.append(f"osvětlení {info.illumination * 100:.0f} %")
        for r in rows:
            lines.append(glossary_markup(r, col))
        rs = self.oapp.rise_set_cached(self.ref)
        zone = model.display_zone
        if rs is not None and not (rs.always_up or rs.never_up):
            lines.append(
                glossary_markup(
                    f"východ {hm(rs.rise, zone)} · kulminace {hm(rs.transit, zone)} · "
                    f"západ {hm(rs.set, zone)}",
                    col,
                )
            )
        elif rs is not None and rs.always_up:
            lines.append("Nikdy nezapadá (cirkumpolární).")
        if info.text:
            lines += ["", escape(info.text)]
        self.query_one("#detail-text", Static).update("\n".join(lines))


class GlossaryScreen(BaseModal):
    def __init__(self, term: str) -> None:
        super().__init__()
        self.term = term

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog") as v:
            v.border_title = f"SLOVNÍČEK · {self.term}"
            yield Static(escape(explain(self.term) or "Pojem není ve slovníčku."))
            yield Static("Esc zavřít", classes="hint")

    def on_click(self) -> None:
        self.dismiss(None)
