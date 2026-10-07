"""Screen 1: the sky (beginner window view or advanced map) with side panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Static

from obloha.beginner.describe import direction_arrow, direction_name
from obloha.beginner.lessons import LESSON_BY_ID
from obloha.beginner.whatsup import suggestions
from obloha.core.coords import format_dec, format_ra
from obloha.core.objects import object_info
from obloha.core.sky import ObjectRef
from obloha.render.sky import RenderResult, compass_name, render_sky
from obloha.ui.formatting import hm, num
from obloha.ui.widgets.skymap import SkyMap

if TYPE_CHECKING:
    from obloha.ui.app import ObloApp


class SkyPane(Vertical):
    """Map + side panel + lesson box."""

    SCOPED_CSS = False
    DEFAULT_CSS = """
    SkyPane { height: 1fr; }
    SkyPane #sky-body { height: 1fr; }
    SkyPane #map-box { width: 1fr; height: 1fr; border: round $ob-border;
        border-title-color: $ob-accent; border-title-style: bold; padding: 0; }
    SkyPane #side { width: 36; height: 1fr; border: round $ob-border;
        border-title-color: $ob-accent; border-title-style: bold; padding: 0 1; }
    SkyPane #lesson-box { height: auto; max-height: 8; border: round $ob-border;
        border-title-color: $ob-accent2; border-title-style: bold; padding: 0 1; }
    SkyPane #lesson-buttons { height: 1; }
    SkyPane #lesson-buttons Button { height: 1; min-width: 10; border: none; margin: 0 1 0 0;
        background: $ob-selection; color: $ob-text; }
    SkyPane #lesson-buttons Button:hover { background: $ob-accent; color: $ob-bg; }
    .-narrow SkyPane #side { width: 30; }
    .-mobile SkyPane #sky-body { layout: vertical; }
    .-mobile SkyPane #map-box { height: 1fr; min-height: 12; }
    .-mobile SkyPane #side { width: 1fr; height: auto; max-height: 11; }
    .-noinfo SkyPane #side { display: none; }
    .-mobile SkyPane #lesson-box { max-height: 9; }
    """

    def __init__(self) -> None:
        super().__init__(id="sky-pane")
        self.map = SkyMap(self.render_map, id="skymap")
        self.side = Static(id="side-content")
        self.lesson_text = Static(id="lesson-text")
        self.last_result: RenderResult | None = None

    @property
    def oapp(self) -> ObloApp:
        return self.app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        with Horizontal(id="sky-body"):
            with Vertical(id="map-box"):
                yield self.map
            with VerticalScroll(id="side"):
                yield self.side
        with Vertical(id="lesson-box"):
            yield self.lesson_text
            with Horizontal(id="lesson-buttons"):
                yield Button("✓ našel jsem", id="lesson-found")
                yield Button("nápověda", id="lesson-hint")
                yield Button("další úkol", id="lesson-skip")

    def render_map(self, cols: int, rows: int) -> RenderResult:
        model = self.oapp.model
        scene = model.scene()
        opts = model.view_options(scene)
        result = render_sky(scene, opts, cols, rows)
        result.frame = result.frame.converted(night=model.night, colors256=model.colors256)
        self.last_result = result
        return result

    def refresh_content(self, full: bool = False) -> None:
        model = self.oapp.model
        self.map.redraw(full=full)
        box = self.query_one("#map-box")
        side_box = self.query_one("#side")
        if model.beginner:
            arrow = direction_arrow(model.win_az)
            what = "MÍŘÍŠ NA" if model.compass_on else "díváš se na"
            title = f"POHLED Z OKNA · {what} {direction_name(model.win_az).upper()} {arrow}"
            if self.oapp.is_mobile:
                title = f"{what.upper()} {direction_name(model.win_az).upper()} {arrow}"
            if model.compass_on:
                title += " · ◎ kompas zap."
            box.border_title = title
            box.border_subtitle = "◀ ▶ otočit · ▲ ▼ výš/níž" if not self.oapp.is_mobile else ""
            side_box.border_title = "CO TEĎ UVIDÍŠ"
            self.side.update(self._beginner_side())
        else:
            if model.adv_view == "full":
                box.border_title = "OBLOHA · celá obloha"
                box.border_subtitle = "zenit uprostřed · S nahoře"
            else:
                box.border_title = (
                    f"OBLOHA · pohled na {compass_name(model.dir_az)} · "
                    f"zorné pole {model.dir_fov:.0f}°"
                )
                box.border_subtitle = f"výška středu {model.dir_alt:.0f}°"
            side_box.border_title = "VYBRÁNO"
            self.side.update(self._advanced_side())
        self._update_lesson()

    # ------------------------------------------------------------------ beginner
    def _beginner_side(self) -> str:
        model = self.oapp.model
        scene = model.scene()
        items = suggestions(
            scene, limit=5 if not self.oapp.is_mobile else 3, user_limit=model.beg_limit
        )
        t = model.theme
        if not items:
            return (
                "[b]Teď není moc co vidět.[/b]\n\nJe den nebo světlá obloha. "
                "Zkus to po setmění, nebo posuň čas klávesou [b].[/b]"
            )
        lines = []
        for k, s in enumerate(items):
            sel = model.selected == s.ref
            marker = "▸ " if sel else ""
            lines.append(
                f"[@click=app.pick_suggestion({k})][b #{t.text:06x}]{marker}{s.symbol} "
                f"{escape(s.title)}[/][/]  [#{t.muted:06x}]{escape(s.kind)}[/]"
            )
            for sentence in s.sentences:
                lines.append(f"  {escape(sentence)}")
            lines.append("")
        if model.message:
            lines.append(f"[#{t.highlight:06x}]{escape(model.message)}[/]")
        lines.append(f"[#{t.muted:06x}]↵ podrobnosti · ? co je to · u úkoly[/]")
        return "\n".join(lines)

    # ------------------------------------------------------------------ advanced
    def _advanced_side(self) -> str:
        model = self.oapp.model
        scene = model.scene()
        t = model.theme
        mute = f"#{t.muted:06x}"
        lines: list[str] = []
        ref = model.selected
        info = object_info(scene, ref) if ref else None
        if info is not None:
            sym = scene.bodies[ref.key].info.symbol if ref and ref.kind == "body" else "✦"
            lines.append(f"[b]{sym} {escape(info.name)}[/b]")
            sub = info.kind_cs
            if info.constellation:
                sub += f" · souhvězdí {info.constellation}"
            lines.append(f"[{mute}]{escape(sub)}[/]")
            lines.append("")
            if info.mag is not None:
                lines.append(f"magnituda    {num(info.mag)}")
            lines.append(f"výška        {info.alt:.0f}°")
            lines.append(f"azimut       {info.az:.0f}° ({compass_name(info.az)})")
            if model.cfg.display.units == "hm":
                lines.append(f"RA / Dec     {format_ra(info.ra)} / {format_dec(info.dec)}")
            else:
                lines.append(f"RA / Dec     {num(info.ra)}° / {num(info.dec)}°")
            if info.distance_au is not None:
                if ref and ref.key == "moon":
                    lines.append(
                        f"vzdálenost   {info.distance_au * 149_597_870:,.0f} km".replace(",", " ")
                    )
                else:
                    lines.append(f"vzdálenost   ≈ {num(info.distance_au)} au")
            rs = self.oapp.rise_set_cached(ref) if ref else None
            zone = model.display_zone
            if rs is not None:
                if rs.always_up:
                    lines.append("nezapadá (cirkumpolární)")
                elif rs.never_up:
                    lines.append("dnes nevychází")
                else:
                    lines.append(f"vychází      {hm(rs.rise, zone)}")
                    if rs.transit:
                        lines.append(
                            f"kulminuje    {hm(rs.transit, zone)} · {(rs.transit_alt or 0):.0f}°"
                        )
                    lines.append(f"zapadá       {hm(rs.set, zone)}")
            if info.text:
                lines.append("")
                lines.append(escape(info.text))
            lines.append("")
        else:
            lines.append(f"[{mute}]Vyber objekt kurzorem (šipky) a Enter, nebo klepni.[/]")
            lines.append("")
        lines.append(f"[b #{t.accent:06x}]NEJJASNĚJŠÍ NAD OBZOREM[/]")
        for name, mag, alt, sym in self._brightest(scene):
            lines.append(f"{sym} {escape(name)[:13]:<13} {num(mag):>5} {alt:>5.0f}°")
        lines.append("")
        moon = scene.bodies["moon"]
        if moon.alt <= 0:
            mrs = self.oapp.rise_set_cached(ObjectRef.body("moon"))
            if mrs and mrs.rise:
                lines.append(f"☽ vychází v {hm(mrs.rise, model.display_zone)}")
        nxt = self.oapp.next_visible_pass()
        if nxt is not None:
            pass_mag = f" ({num(nxt.mag)} mag)" if nxt.mag is not None else ""
            lines.append(
                f"▲ {escape(nxt.name)} přelet {hm(nxt.peak.when, model.display_zone)}{pass_mag}"
            )
        if model.message:
            lines.append("")
            lines.append(f"[#{t.highlight:06x}]{escape(model.message)}[/]")
        return "\n".join(lines)

    def _brightest(self, scene) -> list[tuple[str, float, float, str]]:  # type: ignore[no-untyped-def]
        cat = scene.cat
        out = []
        for b in scene.bodies.values():
            if b.alt > 0 and b.id != "sun" and b.mag < 6:
                out.append((b.name, b.mag, b.alt, b.info.symbol))
        for i in cat.named_stars[:60]:
            if scene.star_alt[i] > 0 and i in cat.cs_star_names:
                out.append((cat.cs_star_names[i], float(cat.mag[i]), float(scene.star_alt[i]), "✦"))
        out.sort(key=lambda r: r[1])
        return out[:8]

    # ------------------------------------------------------------------ lessons
    def _update_lesson(self) -> None:
        model = self.oapp.model
        box = self.query_one("#lesson-box")
        scene = model.scene()
        lv = model.lesson_view(scene)
        if lv is None or not model.lesson.current:
            box.display = False
            return
        box.display = True
        n, total = model.lesson.position(scene)
        title = LESSON_BY_ID[model.lesson.current].title
        box.border_title = f"ÚKOL {n} / {total} · {title}"
        text = "\n".join(escape(s) for s in lv.steps)
        nxt = model.lesson.next_title(scene)
        if nxt and not self.oapp.is_mobile:
            text += f"\n[#{model.theme.muted:06x}]další úkol: {escape(nxt)}[/]"
        self.lesson_text.update(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        actions = {"lesson-found": "found", "lesson-hint": "hint", "lesson-skip": "skip_lesson"}
        action = actions.get(event.button.id or "")
        if action:
            self.oapp.run_named_action(action)
