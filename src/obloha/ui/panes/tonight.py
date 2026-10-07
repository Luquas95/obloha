"""Screen 2: tonight (timeline, Sun & Moon, planets, events, ISS passes, score)."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from rich.markup import escape
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static

from obloha.core.bodies import BODY_BY_ID
from obloha.render.night import moon_disc, night_timeline, now_column
from obloha.ui.formatting import bar, date_short, duration, hm, num
from obloha.ui.widgets.skymap import frame_strip

if TYPE_CHECKING:
    from obloha.ui.app import ObloApp


class TonightPane(VerticalScroll):
    DEFAULT_CSS = """
    TonightPane { height: 1fr; }
    TonightPane .box { border: round $ob-border; border-title-color: $ob-accent;
        border-title-style: bold; padding: 0 1; height: auto; }
    TonightPane #tonight-row1, TonightPane #tonight-row2 { height: auto; }
    TonightPane #sunmoon { width: 42; }
    TonightPane #planets { width: 1fr; }
    TonightPane #events30 { width: 1fr; }
    TonightPane #passes { width: 1fr; }
    .-mobile TonightPane #tonight-row1, .-mobile TonightPane #tonight-row2 { layout: vertical; }
    .-mobile TonightPane #sunmoon { width: 1fr; }
    """

    def __init__(self) -> None:
        super().__init__(id="tonight-pane")
        self.timeline = Static(classes="box", id="timeline")
        self.sunmoon = Static(classes="box", id="sunmoon")
        self.planets = Static(classes="box", id="planets")
        self.events30 = Static(classes="box", id="events30")
        self.passes = Static(classes="box", id="passes")

    @property
    def oapp(self) -> ObloApp:
        return self.app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        yield self.timeline
        with Horizontal(id="tonight-row1"):
            yield self.sunmoon
            yield self.planets
        with Horizontal(id="tonight-row2"):
            yield self.events30
            yield self.passes

    def refresh_content(self, full: bool = False) -> None:
        model = self.oapp.model
        data = model.tonight()
        zone = model.display_zone
        t = model.theme
        tw = data.twilight
        start = tw.sunset or data.start + timedelta(hours=6)
        end = tw.sunrise or data.start + timedelta(hours=18)
        nxt = start + timedelta(days=1)
        self.timeline.border_title = (
            f"DNES V NOCI · {date_short(start, zone)}–{date_short(nxt, zone)} "
            f"{start.astimezone(zone).year}"
        )
        self.timeline.border_subtitle = model.location.name
        # ---------------------------------------------------------------- timeline
        width = max(20, (self.size.width or 100) - 18)
        bodies = [BODY_BY_ID["moon"]] + [p.info for p in data.planets if p.observable][:4]
        scores = [(s.when, s.score) for s in data.scores]
        tl = night_timeline(start - timedelta(minutes=30), end + timedelta(minutes=30),
                            model.location, width, bodies, scores)
        text = Text(no_wrap=True, overflow="crop")
        axis = [" "] * tl.columns
        nowc = now_column(tl, model.now())
        for col, label in tl.hour_marks:
            for k, ch in enumerate(label):
                if col + k < tl.columns:
                    axis[col + k] = ch
        if nowc is not None:
            axis[nowc] = "▾"
        text.append(" " * 12 + "".join(axis) + "\n", Style(color=f"#{t.muted:06x}"))
        for row in tl.rows:
            text.append(f"{row.label[:10]:<12}", Style(color=f"#{t.text:06x}"))
            color = f"#{row.color:06x}" if not model.night else f"#{t.accent:06x}"
            text.append(row.cells + "\n", Style(color=color))
        if data.window:
            a, b = data.window
            text.append(f"nejlepší okno: {hm(a, zone)}–{hm(b, zone)} · skóre až "
                        f"{data.best_score} · ", Style(color=f"#{t.good:06x}"))
        else:
            text.append("dnes v noci žádné dobré okno · ", Style(color=f"#{t.bad:06x}"))
        text.append(data.weather_status, Style(color=f"#{t.muted:06x}"))
        self.timeline.update(text)
        # ---------------------------------------------------------------- sun & moon
        self.sunmoon.border_title = "☉ SLUNCE  ·  ☽ MĚSÍC"
        sm = Text(no_wrap=True, overflow="crop")
        rows = [
            ("západ Slunce", hm(tw.sunset, zone)),
            ("konec občanského soumraku", hm(tw.civil_end, zone)),
            ("konec nautického soumraku", hm(tw.nautical_end, zone)),
            ("konec astronomického", hm(tw.astro_end, zone)),
            ("astronomická noc", duration(tw.astro_night) if tw.astro_night else "není"),
            ("východ Slunce", hm(tw.sunrise, zone)),
        ]
        for label, value in rows:
            sm.append(f"{label:<28}{value:>9}\n")
        sm.append("\n")
        mi = data.moon
        disc = moon_disc(mi.illumination, mi.waxing, 9, 4, lit=t.moon, dark=t.suppressed,
                         bg=t.panel, half=model.ascii)
        if model.night:
            disc = disc.converted(night=True)
        info = [
            mi.phase_name,
            f"osvětleno {mi.illumination * 100:.0f} %, stáří {mi.age_days:.0f} d",
            f"vychází {hm(data.moon_rs.rise, zone)}, zapadá {hm(data.moon_rs.set, zone)}",
            f"nov {date_short(mi.next_new, zone)} · úplněk {date_short(mi.next_full, zone)}",
        ]
        for r in range(disc.chars.shape[0]):
            for seg in frame_strip(disc, r):
                sm.append(seg.text, seg.style)
            sm.append("  " + (info[r] if r < len(info) else "") + "\n")
        self.sunmoon.update(sm)
        # ---------------------------------------------------------------- planets
        narrow = self.oapp.is_mobile or (self.planets.size.width or 80) < 60
        self.planets.border_title = "PLANETY"
        self.planets.border_subtitle = "seřazeno podle pozorovatelnosti"
        pt = Text(no_wrap=True, overflow="crop")
        if narrow:
            pt.append(f"{'planeta':<11}{'mag':>5}  {'nejvýš':<11}hodn.\n",
                      Style(color=f"#{t.muted:06x}"))
        else:
            pt.append(f"{'planeta':<12}{'mag':>5}   {'souhvězdí':<14}{'nad obzorem (tma)':<19}"
                      f"{'nejvýš':<12}hodnocení\n", Style(color=f"#{t.muted:06x}"))
        best = max((p.score for p in data.planets), default=1) or 1
        for p in data.planets:
            stars = bar(p.score / best, 5)
            if p.observable and p.up_from and p.up_to:
                window = f"{hm(p.up_from, zone)} – {hm(p.up_to, zone)}"
                top = f"{hm(p.best_time, zone)} {p.best_alt:.0f}°"
            else:
                window, top = "pod obzorem", "u Slunce" if p.best_alt < 5 else "nevhodně"
            con = model.scene().cat.constellation_cs(p.constellation)
            if narrow:
                pt.append(f"{p.info.symbol} {p.info.name:<9}{num(p.mag):>5}  {top:<11}{stars}\n")
            else:
                pt.append(f"{p.info.symbol} {p.info.name:<10}{num(p.mag):>5}   {con[:13]:<14}"
                          f"{window:<19}{top:<12}{stars}\n")
        tip = self._planet_tip()
        if tip:
            pt.append("\n" + tip, Style(color=f"#{t.accent2:06x}"))
        self.planets.update(pt)
        # ---------------------------------------------------------------- events & passes
        self.events30.border_title = "ÚKAZY · PŘÍŠTÍCH 30 DNÍ"
        et = Text(no_wrap=True, overflow="crop")
        events = self.oapp.events_if_ready(30)
        if events is None:
            et.append("počítám…", Style(color=f"#{t.muted:06x}"))
        else:
            limit = model.now() + timedelta(days=30)
            shown = [e for e in events if e.when <= limit and e.kind != "perigee"][:9]
            for e in shown:
                et.append(f"{date_short(e.when, zone):<8}{e.symbol} {escape(e.title)}\n")
            et.append("\n↵ detail · j skočit na čas úkazu (obrazovka 4)",
                      Style(color=f"#{t.muted:06x}"))
        self.events30.update(et)
        self.passes.border_title = "▲ PŘELETY ISS · viditelné"
        ps = Text(no_wrap=True, overflow="crop")
        passes = [p for p in self.oapp.passes_if_ready() or [] if p.visible][:6]
        if passes:
            ps.append(f"{'datum':<9}{'začátek':<10}{'nejvýš':<14}{'konec':<12}jasnost\n",
                      Style(color=f"#{t.muted:06x}"))
            from obloha.render.sky import compass_name

            for p in passes:
                mag = num(p.mag) if p.mag is not None else "—"
                ps.append(
                    f"{date_short(p.rise.when, zone):<9}"
                    f"{hm(p.rise.when, zone)} {compass_name(p.rise.az):<4}"
                    f"{hm(p.peak.when, zone)} {p.peak.alt:>3.0f}°    "
                    f"{hm(p.set.when, zone)} {compass_name(p.set.az):<5}{mag:>6}\n"
                )
        else:
            ps.append("žádné viditelné přelety v příštích 7 dnech\n" if model.sats else
                      "dráhy satelitů nejsou k dispozici\n", Style(color=f"#{t.muted:06x}"))
        ps.append(f"\ndráhy z CelesTraku · {model.sat_status}", Style(color=f"#{t.muted:06x}"))
        warn = model.sat_age_warning()
        if warn:
            ps.append("\n" + warn, Style(color=f"#{t.bad:06x}"))
        self.passes.update(ps)

    def _planet_tip(self) -> str:
        events = self.oapp.events_if_ready(30)
        if not events:
            return ""
        for e in events:
            if e.kind == "opposition" and "opozici" in e.title:
                zone = self.oapp.model.display_zone
                return f"Tip: {e.title} {date_short(e.when, zone)}, celou noc nad obzorem."
        return ""
