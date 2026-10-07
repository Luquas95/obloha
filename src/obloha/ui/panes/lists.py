"""Screens 3 and 4: satellite passes and the events calendar."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from rich.markup import escape
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Static

from obloha.beginner.glossary import mark_terms
from obloha.core.events import EVENT_KINDS, Event
from obloha.core.satellites import SatPass
from obloha.render.canvas import Canvas
from obloha.render.sky import compass_name
from obloha.ui.formatting import date_short, hm, num
from obloha.ui.widgets.skymap import frame_strip

if TYPE_CHECKING:
    from obloha.ui.app import ObloApp


def glossary_markup(text: str, color: str) -> str:
    """Escape ``text`` and turn glossary terms into underlined clickable links."""
    out = []
    for part in mark_terms(text):
        if part.term:
            out.append(f"[u {color}][@click=app.glossary('{part.term}')]{escape(part.text)}[/][/]")
        else:
            out.append(escape(part.text))
    return "".join(out)


class SatellitesPane(Vertical):
    SCOPED_CSS = False
    DEFAULT_CSS = """
    SatellitesPane { height: 1fr; }
    SatellitesPane #sat-body { height: 1fr; }
    SatellitesPane #sat-table { width: 1fr; height: 1fr; border: round $ob-border;
        border-title-color: $ob-accent; }
    SatellitesPane #sat-detail { width: 40; height: 1fr; border: round $ob-border;
        border-title-color: $ob-accent; padding: 0 1; }
    SatellitesPane #sat-status { height: auto; padding: 0 1; color: $ob-muted; }
    .-mobile SatellitesPane #sat-body { layout: vertical; }
    .-mobile SatellitesPane #sat-detail { width: 1fr; height: auto; }
    """

    def __init__(self) -> None:
        super().__init__(id="satellites-pane")
        self.table: DataTable[str] = DataTable(
            id="sat-table", cursor_type="row", zebra_stripes=True
        )
        self.detail = Static(id="sat-detail")
        self.status = Static(id="sat-status")
        self.passes: list[SatPass] = []

    @property
    def oapp(self) -> ObloApp:
        return self.app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        yield self.status
        with Horizontal(id="sat-body"):
            yield self.table
            yield self.detail

    def refresh_content(self, full: bool = False) -> None:
        model = self.oapp.model
        zone = model.display_zone
        t = model.theme
        warn = model.sat_age_warning()
        status = f"Dráhy z CelesTraku · {model.sat_status}"
        if warn:
            status += f"  [#{t.bad:06x}]{escape(warn)}[/]"
        self.status.update(status)
        passes = self.oapp.passes_if_ready()
        self.table.border_title = "PŘELETY · příštích 7 dní"
        if passes is None:
            self.detail.update("počítám přelety…")
            return
        if passes == self.passes and not full and self.table.row_count:
            return
        self.passes = passes
        self.table.clear(columns=True)
        compact = self.oapp.is_mobile
        if compact:
            self.table.add_columns("datum", "nejvýš", "vid.", "mag")
        else:
            self.table.add_columns(
                "satelit", "datum", "začátek", "nejvýš", "konec", "viditelný", "jasnost"
            )
        for p in passes:
            vis = "ano" if p.visible else "ne"
            mag = num(p.mag) if p.mag is not None else "—"
            if compact:
                self.table.add_row(
                    f"{date_short(p.rise.when, zone)} {p.name[:6]}",
                    f"{hm(p.peak.when, zone)} {p.peak.alt:.0f}°",
                    vis,
                    mag,
                )
            else:
                self.table.add_row(
                    p.name[:14],
                    date_short(p.rise.when, zone),
                    f"{hm(p.rise.when, zone)} {compass_name(p.rise.az)}",
                    f"{hm(p.peak.when, zone)} {p.peak.alt:.0f}°",
                    f"{hm(p.set.when, zone)} {compass_name(p.set.az)}",
                    vis,
                    mag,
                )
        if not passes:
            self.detail.update("Žádné přelety. Zkontroluj, že jsou stažené dráhy (Nastavení).")
        else:
            self.show_detail(0)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table is self.table:
            self.show_detail(event.cursor_row)

    def show_detail(self, index: int) -> None:
        if not 0 <= index < len(self.passes):
            return
        p = self.passes[index]
        model = self.oapp.model
        zone = model.display_zone
        t = model.theme
        self.detail.border_title = f"▲ {p.name}"
        text = Text()
        text.append(f"{date_short(p.rise.when, zone)} {p.rise.when.astimezone(zone).year}\n")
        text.append(
            f"začátek  {hm(p.rise.when, zone)}  {compass_name(p.rise.az):<3} {p.rise.alt:.0f}°\n"
        )
        text.append(
            f"nejvýš   {hm(p.peak.when, zone)}  {compass_name(p.peak.az):<3} {p.peak.alt:.0f}°\n"
        )
        text.append(
            f"konec    {hm(p.set.when, zone)}  {compass_name(p.set.az):<3} {p.set.alt:.0f}°\n"
        )
        if p.visible and p.visible_from and p.visible_to:
            text.append(
                f"\nviditelný {hm(p.visible_from, zone)}–{hm(p.visible_to, zone)}"
                " (osvětlený Sluncem, u tebe tma)\n",
                f"#{t.good:06x}",
            )
            if p.mag is not None:
                text.append(f"nejvyšší jasnost {num(p.mag)} mag\n")
        else:
            text.append(
                "\nneviditelný: družice je ve stínu Země nebo je u tebe světlo\n", f"#{t.muted:06x}"
            )
        # mini sky map with the track
        c = Canvas(18, 8, half=model.ascii, bg=t.panel)
        from obloha.core.projection import FullSky

        proj = FullSky(c.width, c.height, margin=1)
        az = np.linspace(0, 360, 200)
        x, y, ok = proj.forward(np.zeros_like(az), az)
        c.dots(x[ok], y[ok], t.horizon)
        alt = np.array([pt.alt for pt in p.track])
        azs = np.array([pt.az for pt in p.track])
        tx, ty, tok = proj.forward(alt, azs)
        c.polyline(tx, ty, tok, t.satellite)
        frame = c.frame()
        text.append("\n")
        for r in range(frame.chars.shape[0]):
            for seg in frame_strip(frame, r):
                text.append(seg.text, seg.style)
            text.append("\n")
        text.append("S nahoře, V vlevo (jako při pohledu vzhůru)", f"#{t.muted:06x}")
        self.detail.update(text)


class EventsPane(Vertical):
    SCOPED_CSS = False
    DEFAULT_CSS = """
    EventsPane { height: 1fr; }
    EventsPane #ev-filter { height: auto; padding: 0 1; }
    EventsPane #ev-body { height: 1fr; }
    EventsPane #ev-table { width: 1fr; height: 1fr; border: round $ob-border;
        border-title-color: $ob-accent; }
    EventsPane #ev-detail { width: 46; height: 1fr; border: round $ob-border;
        border-title-color: $ob-accent; padding: 0 1; }
    .-narrow EventsPane #ev-detail { width: 34; }
    .-mobile EventsPane #ev-body { layout: vertical; }
    .-mobile EventsPane #ev-detail { width: 1fr; height: auto; max-height: 14; }
    """

    def __init__(self) -> None:
        super().__init__(id="events-pane")
        self.filter = Static(id="ev-filter")
        self.table: DataTable[str] = DataTable(id="ev-table", cursor_type="row", zebra_stripes=True)
        self.detail = Static(id="ev-detail")
        self.kinds: set[str] = set(EVENT_KINDS)
        self.shown: list[Event] = []

    @property
    def oapp(self) -> ObloApp:
        return self.app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        yield self.filter
        with Horizontal(id="ev-body"):
            yield self.table
            yield self.detail

    def toggle_kind(self, kind: str) -> None:
        if kind == "all":
            self.kinds = set(EVENT_KINDS) if len(self.kinds) < len(EVENT_KINDS) else set()
        elif kind in self.kinds:
            self.kinds.discard(kind)
        else:
            self.kinds.add(kind)
        self.refresh_content(full=True)

    def cycle_filter(self) -> None:
        keys = list(EVENT_KINDS)
        if len(self.kinds) == len(keys):
            self.kinds = {keys[0]}
        elif len(self.kinds) == 1:
            k = next(iter(self.kinds))
            idx = keys.index(k) + 1
            self.kinds = {keys[idx]} if idx < len(keys) else set(keys)
        else:
            self.kinds = set(keys)
        self.refresh_content(full=True)

    def refresh_content(self, full: bool = False) -> None:
        model = self.oapp.model
        t = model.theme
        parts = ["[@click=app.event_kind('all')][b]filtr:[/b][/] "]
        for key, label in EVENT_KINDS.items():
            on = key in self.kinds
            color = f"#{t.accent:06x}" if on else f"#{t.suppressed:06x}"
            mark = "■" if on else "□"
            parts.append(f"[@click=app.event_kind('{key}')][{color}]{mark} {label}[/][/]  ")
        self.filter.update("".join(parts))
        events = self.oapp.events_if_ready()
        months = model.cfg.events.months
        self.table.border_title = f"ÚKAZY · příští {months} " + (
            "měsíce" if 2 <= months <= 4 else "měsíc" if months == 1 else "měsíců"
        )
        if events is None:
            self.detail.update("počítám úkazy…")
            return
        shown = [e for e in events if e.kind in self.kinds]
        if shown == self.shown and not full and self.table.row_count:
            return
        self.shown = shown
        zone = model.display_zone
        self.table.clear(columns=True)
        if self.oapp.is_mobile:
            self.table.add_columns("datum", "úkaz")
        else:
            self.table.add_columns("datum", "čas", "úkaz", "výška")
        for e in shown:
            title = f"{e.symbol} {e.title}"
            if self.oapp.is_mobile:
                self.table.add_row(date_short(e.when, zone), title)
            else:
                alt = f"{e.altitude:.0f}°" if e.altitude is not None else ""
                self.table.add_row(date_short(e.when, zone), hm(e.when, zone), title, alt)
        if shown:
            self.show_detail(0)
        else:
            self.detail.update("Žádné úkazy pro zvolený filtr.")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table is self.table:
            self.show_detail(event.cursor_row)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table is self.table:
            self.show_detail(event.cursor_row)
            self.detail.focus()

    def current(self) -> Event | None:
        row = self.table.cursor_row
        if 0 <= row < len(self.shown):
            return self.shown[row]
        return None

    def show_detail(self, index: int) -> None:
        if not 0 <= index < len(self.shown):
            return
        e = self.shown[index]
        model = self.oapp.model
        zone = model.display_zone
        t = model.theme
        self.detail.border_title = f"{e.symbol} {EVENT_KINDS.get(e.kind, e.kind)}"
        when = e.when.astimezone(zone)
        lines = [
            f"[b]{escape(e.title)}[/b]",
            f"{when:%-d. %-m. %Y %H:%M} ({e.when:%H:%M} UTC)",
            "",
            glossary_markup(e.detail, f"#{t.accent:06x}"),
        ]
        if e.altitude is not None and e.kind not in ("eclipse",):
            lines += ["", f"Výška nad obzorem v tu chvíli: {e.altitude:.0f}°"]
        lines += [
            "",
            f"[#{t.muted:06x}]j skočit na čas úkazu · podtržené pojmy vysvětlí klepnutí[/]",
        ]
        self.detail.update("\n".join(lines))
