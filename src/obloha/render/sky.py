"""Render a :class:`~obloha.core.sky.SkyScene` into a terminal frame."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from obloha.core.bodies import BODY_BY_ID, moon_symbol
from obloha.core.catalog import Catalog
from obloha.core.projection import FullSky, Panorama, Projection, Stereographic, wrap180
from obloha.core.sky import ObjectRef, SkyScene, limiting_magnitude_for_sun
from obloha.render.canvas import BOLD, DIM, REVERSE, UNDERLINE, Canvas, Frame
from obloha.render.color import blend, blend_array
from obloha.render.theme import DARK, Theme, star_colors

FloatArray = NDArray[np.float64]
ViewKind = Literal["full", "direction", "window"]

COMPASS = (
    (0.0, "S"),
    (45.0, "SV"),
    (90.0, "V"),
    (135.0, "JV"),
    (180.0, "J"),
    (225.0, "JZ"),
    (270.0, "Z"),
    (315.0, "SZ"),
)


def compass_name(az: float) -> str:
    """Czech 8-point compass abbreviation."""
    return COMPASS[int(((az % 360.0) + 22.5) // 45.0) % 8][1]


@dataclass
class Layers:
    """Toggleable map layers."""

    constellation_lines: bool = True
    constellation_borders: bool = False
    labels: bool = True
    milky_way: bool = True
    grid: str | None = None  # None, "altaz", "eq"
    ecliptic: bool = False
    horizon: bool = True
    planets: bool = True
    moon: bool = True
    sun: bool = True
    satellites: bool = True
    below_horizon: bool = False
    asterisms: bool = False
    deep_sky: bool = True


@dataclass
class ViewOptions:
    """How to draw the sky."""

    kind: ViewKind = "full"
    center_az: float = 180.0
    center_alt: float = 30.0
    fov: float = 120.0
    bottom_alt: float = -6.0
    limiting_mag: float = 5.5
    theme: Theme = DARK
    half: bool = False
    ascii_symbols: bool = False
    beginner: bool = False
    max_labels: int | None = None
    selected: ObjectRef | None = None
    cursor: tuple[float, float] | None = None  # (alt, az)
    highlights: list[ObjectRef] = field(default_factory=list)
    guides: list[tuple[ObjectRef, ObjectRef]] = field(default_factory=list)
    hint_circle: tuple[float, float, float] | None = None  # alt, az, radius°
    always_label: set[ObjectRef] = field(default_factory=set)
    light_pollution: float = 0.5  # 0 (dark site) .. 1 (city centre)
    layers: Layers = field(default_factory=Layers)


@dataclass(frozen=True)
class Hit:
    """An object drawn on the map (for picking with mouse or cursor)."""

    ref: ObjectRef
    x: float
    y: float
    col: int
    row: int
    mag: float
    label: str


@dataclass
class RenderResult:
    frame: Frame
    hits: list[Hit]
    projection: Projection
    canvas_cols: int
    canvas_rows: int
    sub_x: int
    sub_y: int

    def cell_to_dot(self, col: int, row: int) -> tuple[float, float]:
        return col * self.sub_x + (self.sub_x - 1) / 2.0, row * self.sub_y + (self.sub_y - 1) / 2.0

    def cell_altaz(self, col: int, row: int) -> tuple[float, float] | None:
        x, y = self.cell_to_dot(col, row)
        alt, az, ok = self.projection.inverse(np.array([x]), np.array([y]))
        if not bool(ok[0]):
            return None
        return float(alt[0]), float(az[0])

    def nearest(self, col: int, row: int, max_cells: float = 2.5) -> Hit | None:
        """Most prominent object near a cell (brightness weighted)."""
        best: tuple[float, Hit] | None = None
        x, y = self.cell_to_dot(col, row)
        for h in self.hits:
            d = math.hypot((h.x - x) / self.sub_x, (h.y - y) / self.sub_y * 2)
            if d <= max_cells:
                score = d - 0.3 * max(0.0, 3.0 - h.mag)
                if best is None or score < best[0]:
                    best = (score, h)
        return best[1] if best else None


def make_projection(opts: ViewOptions, width: int, height: int) -> Projection:
    if opts.kind == "full":
        return FullSky(width, height, min_alt=-10.0 if opts.layers.below_horizon else 0.0)
    if opts.kind == "direction":
        return Stereographic(width, height, opts.center_az, opts.center_alt, opts.fov)
    return Panorama(width, height, opts.center_az, opts.fov, opts.bottom_alt)


class SkyRenderer:
    """Draws one frame. Create a new instance per frame."""

    def __init__(self, scene: SkyScene, opts: ViewOptions, cols: int, rows: int) -> None:
        self.scene = scene
        self.opts = opts
        self.theme = opts.theme
        self.cols = cols
        self.rows = rows
        self.window = opts.kind == "window"
        # window view keeps the last row for compass labels
        draw_rows = rows - 1 if self.window else rows
        self.canvas = Canvas(cols, max(1, draw_rows), half=opts.half, bg=self.theme.sky)
        self.proj = make_projection(opts, self.canvas.width, self.canvas.height)
        self.hits: list[Hit] = []
        self.labels: list[tuple[float, str, float, float, int, int, int]] = []
        self.sky_bg = self.theme.sky
        self.min_alt = -90.0 if opts.layers.below_horizon else 0.0
        self.lim = limiting_magnitude_for_sun(scene.sun_alt, opts.limiting_mag)
        fov = 180.0 if opts.kind == "full" else opts.fov
        self.label_mag = 2.0 + max(0.0, (130.0 - fov) / 30.0)

    # ---------------------------------------------------------------- helpers
    def project(
        self, alt: FloatArray, az: FloatArray
    ) -> tuple[FloatArray, FloatArray, NDArray[np.bool_]]:
        x, y, ok = self.proj.forward(np.asarray(alt), np.asarray(az))
        return x, y, ok

    def project1(self, alt: float, az: float) -> tuple[float, float] | None:
        x, y, ok = self.project(np.array([alt]), np.array([az]))
        if not ok[0]:
            return None
        return float(x[0]), float(y[0])

    def add_label(
        self, prio: float, text: str, x: float, y: float, fg: int, flags: int = 0, gap: int = 1
    ) -> None:
        self.labels.append((prio, text, x, y, fg, flags, gap))

    # ---------------------------------------------------------------- layers
    def draw_background(self) -> None:
        c = self.canvas
        cols = np.arange(c.cols)
        rows = np.arange(c.rows)
        cc, rr = np.meshgrid(cols, rows)
        x = cc * c.sub_x + (c.sub_x - 1) / 2.0
        y = rr * c.sub_y + (c.sub_y - 1) / 2.0
        alt, _, ok = self.proj.inverse(x.astype(np.float64), y.astype(np.float64))
        t = self.theme
        sun = self.scene.sun_alt
        day = float(np.clip((sun + 12.0) / 12.0, 0.0, 1.0)) ** 1.5
        base = blend(t.sky, t.sky_day, day)
        self.sky_bg = base
        bg = np.full(alt.shape, base, dtype=np.uint32)
        # light pollution glow towards the horizon
        strength = self.opts.light_pollution * (1.0 - day) * (0.9 if self.window else 0.45)
        if strength > 0:
            glow = np.exp(-np.clip(alt, 0, 90) / 14.0) * strength
            bg = blend_array(bg, t.sky_glow, glow)
        # milky way
        if self.opts.layers.milky_way and sun < -10.0:
            mw_alt, mw_az = self.scene.mw
            mx, my, mok = self.project(mw_alt, mw_az)
            mok &= mw_alt > 0
            if mok.any():
                level = np.zeros(alt.shape, dtype=np.float64)
                rr_i = (np.rint(my[mok]).astype(int) // c.sub_y).clip(0, c.rows - 1)
                cc_i = (np.rint(mx[mok]).astype(int) // c.sub_x).clip(0, c.cols - 1)
                np.maximum.at(level, (rr_i, cc_i), self.scene.cat.mw_level[mok].astype(float))
                # fill small gaps between sample points
                level = np.maximum(level, _dilate(level) * 0.8)
                dark = float(np.clip((-sun - 10.0) / 8.0, 0.0, 1.0))
                mw_strength = (1.0 - 0.6 * self.opts.light_pollution) * dark
                bg = blend_array(bg, blend(t.milky_way, 0x3A4A78, 0.4), level / 5.0 * mw_strength)
        below = alt < 0
        if self.window:
            bg[below] = t.ground
        elif self.opts.kind == "full":
            bg[~ok | (alt < self.proj_min_alt())] = t.background
        else:
            bg[below] = blend(base, t.ground, 0.7)
        c.fill_bg(bg)

    def proj_min_alt(self) -> float:
        return float(getattr(self.proj, "min_alt", -90.0))

    def draw_grid(self) -> None:
        t = self.theme
        layer = self.opts.layers.grid
        if self.opts.kind == "full" and self.opts.layers.horizon:
            for a in (30.0, 60.0):
                az = np.linspace(0.0, 360.0, 721)
                x, y, ok = self.project(np.full_like(az, a), az)
                keep = np.arange(len(az)) % 6 == 0
                self.canvas.dots(x[ok & keep], y[ok & keep], t.grid, -50)
        if layer == "altaz":
            for a in (15.0, 30.0, 45.0, 60.0, 75.0):
                az = np.linspace(0.0, 360.0, 721)
                x, y, ok = self.project(np.full_like(az, a), az)
                self.canvas.polyline(x, y, ok, t.grid, -60, dash=2)
            for z in range(0, 360, 45):
                alt = np.linspace(0.0, 89.0, 180)
                x, y, ok = self.project(alt, np.full_like(alt, float(z)))
                self.canvas.polyline(x, y, ok, t.grid, -60, dash=2)
        elif layer == "eq":
            for alt, az in self.scene.eq_grid:
                x, y, ok = self.project(alt, az)
                ok &= alt > self.min_alt
                self.canvas.polyline(x, y, ok, t.grid, -60, dash=2)

    def draw_constellations(self) -> None:
        sc, cat, t = self.scene, self.scene.cat, self.theme
        if self.opts.layers.constellation_borders:
            alt, az = sc.borders
            x, y, ok = self.project(alt, az)
            ok &= alt > self.min_alt
            off = cat.border_off
            for i in range(len(off) - 1):
                s = slice(off[i], off[i + 1])
                self.canvas.polyline(x[s], y[s], ok[s], t.const_borders, -45, dash=1)
        if self.opts.layers.constellation_lines and not self.opts.beginner:
            x, y, ok = self.project(sc.star_alt, sc.star_az)
            vis = ok & (sc.star_alt > self.min_alt)
            a, b = cat.line_a, cat.line_b
            m = vis[a] & vis[b]
            dx = np.abs(x[a] - x[b]) + np.abs(y[a] - y[b])
            m &= dx < (self.canvas.width + self.canvas.height) / 3
            color = (
                t.const_lines if self.scene.sun_alt < -6 else blend(t.const_lines, self.sky_bg, 0.5)
            )
            self.canvas.segments(x[a][m], y[a][m], x[b][m], y[b][m], color, -40)
        if self.opts.layers.labels and not self.opts.beginner:
            for con in cat.constellations:
                if con.abbr in ("Ser2",) or con.rank > 2:
                    continue
                c_alt, c_az = sc.radec_altaz(con.ra, con.dec)
                if c_alt < 8:
                    continue
                p = self.project1(c_alt, c_az)
                if p is None:
                    continue
                name = cat.constellation_cs(con.abbr[:3]).upper()
                self.add_label(
                    20 + con.rank, name, p[0], p[1], t.const_names, 0, gap=-len(name) // 2
                )

    def draw_ecliptic(self) -> None:
        if not self.opts.layers.ecliptic:
            return
        alt, az = self.scene.ecliptic
        x, y, ok = self.project(alt, az)
        ok &= alt > self.min_alt
        self.canvas.polyline(x, y, ok, self.theme.ecliptic, -55, dash=3)

    def draw_horizon(self) -> None:
        if not self.opts.layers.horizon:
            return
        t, c = self.theme, self.canvas
        if self.opts.kind == "full":
            az = np.linspace(0.0, 360.0, 1441)
            x, y, ok = self.project(np.zeros_like(az), az)
            keep = np.arange(len(az)) % 2 == 0
            c.dots(x[ok & keep], y[ok & keep], t.horizon, -10)
            fs = self.proj
            assert isinstance(fs, FullSky)
            r_cells_x = fs._r(np.array([0.0]))[0]
            for az_c, name in COMPASS:
                ang = math.radians(az_c)
                rx = fs.cx - (r_cells_x + 2.5 * c.sub_x) * math.sin(ang)
                ry = fs.cy - (r_cells_x + 1.6 * c.sub_y) * math.cos(ang)
                col, row = c.cell_of(rx, ry)
                col -= len(name) // 2
                col = max(0, min(c.cols - len(name), col))
                row = max(0, min(c.rows - 1, row))
                c.text(
                    col,
                    row,
                    name,
                    t.text if len(name) == 1 else t.muted,
                    BOLD if len(name) == 1 else 0,
                )
            return
        az = np.linspace(0.0, 360.0, 2881)
        x, y, ok = self.project(np.zeros_like(az), az)
        if self.window:
            return  # drawn by draw_window_ground
        c.dots(x[ok], y[ok], t.horizon, -10)
        for az_c, name in COMPASS:
            p = self.project1(0.0, az_c)
            if p is None:
                continue
            col, row = c.cell_of(*p)
            c.text(col - len(name) // 2, min(c.rows - 1, row + 1), name, t.text, BOLD)

    def draw_window_ground(self) -> None:
        """Horizon line, roof silhouettes and the compass row of the window view."""
        t, c = self.theme, self.canvas
        proj = self.proj
        assert isinstance(proj, Panorama)
        y_h = proj.y_of_alt(0.0)
        if not self.opts.layers.horizon:
            return
        xs = np.arange(c.width, dtype=np.float64)
        _, az, _ = proj.inverse(xs, np.zeros_like(xs))
        heights = _roof_heights(az) / proj.degrees_per_dot()  # in dots
        # ground below the horizon is solid, labels must not go there
        row_h = int(y_h // c.sub_y)
        for r in range(max(row_h + 1, 0), c.rows):
            c.bg[r, :] = t.ground
            c.occupied[r, :] = True
        # horizon line where there is no roof
        no_roof = heights <= 0.5
        c.dots(xs[no_roof], np.full(int(no_roof.sum()), y_h), t.horizon, 50)
        # roofs: columns of dots from the roof top down to the horizon row
        roof_color = t.roofs
        for xi, h in zip(xs.astype(int), heights, strict=False):
            if h <= 0.5:
                continue
            top = round(y_h - h)
            bottom = (row_h + 1) * c.sub_y
            ys = np.arange(max(top, 0), min(bottom, c.height), dtype=np.float64)
            c.dots(np.full_like(ys, xi), ys, roof_color, 60)
        if 0 <= row_h < c.rows:
            c.occupied[row_h, :] |= c.bits[row_h, :] == 0xFF
        # fist scale on the left edge
        for fist in range(1, 10):
            yy = proj.y_of_alt(fist * 10.0)
            row = int(yy // c.sub_y)
            if 0 <= row < row_h:
                c.text(0, row, f"{fist}┤", t.muted)
        # compass labels in the extra bottom row are produced in finish()

    def compass_row(self) -> list[tuple[int, str, bool]]:
        proj = self.proj
        assert isinstance(proj, Panorama)
        out: list[tuple[int, str, bool]] = []
        for step in range(0, 360, 15):
            x = proj.x_of_az(float(step))
            if 0 <= x < self.canvas.width:
                col = int(x // self.canvas.sub_x)
                name = next((n for a, n in COMPASS if a == step), None)
                out.append((col, name or "·", name is not None))
        return out

    def star_visibility(self) -> NDArray[np.bool_]:
        sc = self.scene
        mag = sc.cat.mag
        return (mag <= self.lim) & (sc.star_alt > self.min_alt)

    def draw_stars(self) -> None:
        sc, c = self.scene, self.canvas
        vis = self.star_visibility()
        x, y, ok = self.project(sc.star_alt, sc.star_az)
        m = vis & ok
        if not m.any():
            return
        idx = np.flatnonzero(m)
        mag = sc.cat.mag[idx].astype(np.float64)
        colors = catalog_star_colors(sc.cat)[idx]
        f = np.clip((self.lim + 1.0 - mag) / (self.lim + 2.0), 0.3, 1.0)
        f = np.where(sc.star_alt[idx] < 0, f * 0.35, f)
        colors = blend_array(colors, self.sky_bg, 1.0 - f)
        xs, ys = x[idx], y[idx]
        prio = -mag
        c.dots(xs, ys, colors, prio)
        bright = mag < 2.0
        if bright.any():
            c.dots(xs[bright] + 1, ys[bright], colors[bright], prio[bright])
        brighter = mag < 0.8
        if brighter.any():
            for dx, dy in ((0, 1), (1, 1), (0, -1), (1, -1)) if not c.half else ((0, 1),):
                c.dots(xs[brighter] + dx, ys[brighter] + dy, colors[brighter], prio[brighter])
        cat = sc.cat
        for k, i in enumerate(idx):
            col, row = c.cell_of(xs[k], ys[k])
            name = cat.cs_star_names.get(int(i))
            ref = ObjectRef.star(int(i))
            if name is not None or mag[k] < 3.5:
                self.hits.append(
                    Hit(
                        ref,
                        float(xs[k]),
                        float(ys[k]),
                        col,
                        row,
                        float(mag[k]),
                        cat.star_label(int(i)),
                    )
                )
            forced = ref in self.opts.always_label or ref == self.opts.selected
            if not (self.opts.layers.labels and sc.star_alt[i] > 0):
                continue
            if forced:
                self.add_label(200.0, cat.star_label(int(i)), xs[k], ys[k], self.theme.text)
            elif name and mag[k] <= self.label_mag:
                p = 50.0 - mag[k] * 5 if not self.opts.beginner else 40.0 - mag[k] * 5
                self.add_label(p, name, xs[k], ys[k], self.theme.text)

    def draw_deep_sky(self) -> None:
        if not self.opts.layers.deep_sky:
            return
        sc, c, t = self.scene, self.canvas, self.theme
        for d in sc.cat.deep_sky:
            ref = ObjectRef("dso", d.id)
            important = ref in self.opts.always_label or ref in self.opts.highlights
            if self.opts.beginner and not important:
                continue
            if d.mag > self.lim + 1.0 and not important:
                continue
            alt, az = sc.radec_altaz(d.ra, d.dec)
            if alt < self.min_alt or alt < 0:
                continue
            p = self.project1(alt, az)
            if p is None:
                continue
            ang = np.linspace(0, 2 * np.pi, 12, endpoint=False)
            c.dots(p[0] + 1.6 * np.cos(ang), p[1] + 1.6 * np.sin(ang), t.accent2, 5)
            col, row = c.cell_of(*p)
            self.hits.append(Hit(ref, p[0], p[1], col, row, d.mag, d.name))
            if self.opts.layers.labels:
                self.add_label(150.0 if important else 15.0, d.name, p[0], p[1], t.accent2, gap=2)

    def body_symbol(self, body_id: str) -> str:
        info = BODY_BY_ID[body_id]
        if body_id == "moon":
            return moon_symbol(self.scene.moon_phase, self.opts.ascii_symbols)
        return info.ascii if self.opts.ascii_symbols else info.symbol

    def draw_bodies(self) -> None:
        sc, c, t, layers = self.scene, self.canvas, self.theme, self.opts.layers
        order = [
            "neptune",
            "uranus",
            "mercury",
            "mars",
            "saturn",
            "jupiter",
            "venus",
            "moon",
            "sun",
        ]
        for bid in order:
            b = sc.bodies[bid]
            if bid == "sun" and not layers.sun:
                continue
            if bid == "moon" and not layers.moon:
                continue
            if b.info.kind == "planet" and not layers.planets:
                continue
            if b.alt < self.min_alt:
                continue
            if b.info.kind == "planet" and b.mag > self.lim and bid not in ("uranus", "neptune"):
                continue
            if bid in ("uranus", "neptune") and (self.opts.beginner or b.mag > self.lim):
                ref = ObjectRef.body(bid)
                if ref not in self.opts.always_label and ref != self.opts.selected:
                    continue
            p = self.project1(b.alt, b.az)
            if p is None:
                continue
            ref = ObjectRef.body(bid)
            sym = self.body_symbol(bid)
            col, row = c.cell_of(*p)
            color = t.sun if bid == "sun" else t.moon if bid == "moon" else b.info.color_int
            if b.alt < 0:
                color = blend(self.sky_bg, color, 0.45)
            selected = ref == self.opts.selected
            if selected:
                sym = f"[{sym}]"
                col -= 1
            c.text(col, row, sym, color, BOLD)
            self.hits.append(Hit(ref, p[0], p[1], col + (1 if selected else 0), row, b.mag, b.name))
            if layers.labels:
                prio = 120.0 - b.mag
                if ref in self.opts.always_label or selected:
                    prio = 220.0
                self.add_label(
                    prio, b.name, (col + len(sym)) * c.sub_x - 1, p[1], color, BOLD, gap=1
                )

    def draw_satellites(self) -> None:
        if not self.opts.layers.satellites:
            return
        c, t = self.canvas, self.theme
        for s in self.scene.satellites:
            if s.alt < 0:
                continue
            p = self.project1(s.alt, s.az)
            if p is None:
                continue
            col, row = c.cell_of(*p)
            c.text(
                col,
                row,
                "^" if self.opts.ascii_symbols else "▲",
                t.satellite if s.sunlit else t.muted,
                BOLD,
            )
            ref = ObjectRef("sat", s.name)
            self.hits.append(
                Hit(ref, p[0], p[1], col, row, s.mag if s.mag is not None else 3.0, s.name)
            )
            if self.opts.layers.labels:
                self.add_label(130.0, s.name, p[0] + c.sub_x, p[1], t.satellite)

    def draw_asterisms(self) -> None:
        if not self.opts.layers.asterisms:
            return
        sc, c, t = self.scene, self.canvas, self.theme
        cat = sc.cat
        for a in cat.asterisms:
            alts = sc.star_alt[list(a.stars)]
            if alts.min() < 3.0:
                continue
            x, y, ok = self.project(sc.star_alt[list(a.stars)], sc.star_az[list(a.stars)])
            if not ok.all():
                continue
            ref = ObjectRef("asterism", a.id)
            color = t.guide if ref in self.opts.highlights else blend(t.guide, self.sky_bg, 0.45)
            for i, j in a.lines:
                c.line(x[i], y[i], x[j], y[j], color, -20, dash=2)
            cx, cy = float(x.mean()), float(y.mean())
            col, row = c.cell_of(cx, cy)
            self.hits.append(Hit(ref, cx, cy, col, row, 2.0, a.name))
            if self.opts.layers.labels:
                prio = 160.0 if ref in self.opts.highlights else 60.0
                self.add_label(prio, a.name, cx, cy, color, 0, gap=-len(a.name) // 2)

    def draw_highlights(self) -> None:
        sc, c, t = self.scene, self.canvas, self.theme
        for ref in self.opts.highlights:
            if ref.kind == "asterism":
                continue
            pos = sc.altaz_of(ref)
            if pos is None:
                continue
            p = self.project1(*pos)
            if p is None:
                continue
            ang = np.linspace(0, 2 * np.pi, 24, endpoint=False)
            r = 4.0
            c.dots(p[0] + r * 1.3 * np.cos(ang), p[1] + r * np.sin(ang), t.highlight, 80)
        for a, b in self.opts.guides:
            pa, pb = sc.altaz_of(a), sc.altaz_of(b)
            if pa is None or pb is None:
                continue
            qa, qb = self.project1(*pa), self.project1(*pb)
            if qa is None or qb is None:
                continue
            c.line(qa[0], qa[1], qb[0], qb[1], t.guide, 70, dash=3)
            # arrow head at b
            head = math.atan2(qb[1] - qa[1], qb[0] - qa[0])
            for spread in (-0.5, 0.5):
                c.line(
                    qb[0],
                    qb[1],
                    qb[0] - 5 * math.cos(head + spread),
                    qb[1] - 5 * math.sin(head + spread),
                    t.guide,
                    70,
                )
        if self.opts.hint_circle:
            alt, az, radius = self.opts.hint_circle
            ang = np.linspace(0, 360, 90, endpoint=False)
            # small-circle of given radius around (alt, az)
            from obloha.core.coords import altaz_to_nev, nev_to_altaz

            center = altaz_to_nev(alt, az)
            ref_v = np.array([0.0, 0.0, 1.0]) if abs(alt) < 80 else np.array([1.0, 0.0, 0.0])
            u = np.cross(center, ref_v)
            u /= np.linalg.norm(u)
            v = np.cross(center, u)
            rr = math.radians(radius)
            pts = math.cos(rr) * center[None, :] + math.sin(rr) * (
                np.cos(np.radians(ang))[:, None] * u + np.sin(np.radians(ang))[:, None] * v
            )
            calt, caz = nev_to_altaz(pts)
            x, y, ok = self.project(calt, caz)
            c.dots(x[ok], y[ok], t.highlight, 75)

    def place_labels(self) -> None:
        c = self.canvas
        limit = self.opts.max_labels
        placed = 0
        for prio, text, x, y, fg, flags, gap in sorted(self.labels, key=lambda lab: -lab[0]):
            if limit is not None and placed >= limit and prio < 150:
                continue
            col, row = c.cell_of(x, y)
            if gap < 0:  # centred label
                options = [(col + gap, row), (col + gap, row - 1), (col + gap, row + 1)]
            else:
                options = [
                    (col + gap, row),
                    (col - len(text) - 1, row),
                    (col - len(text) // 2, row - 1),
                    (col - len(text) // 2, row + 1),
                ]
            for oc, orow in options:
                pad_l = 1 if oc > 0 else 0
                pad_r = 1 if oc + len(text) < c.cols else 0
                if c.free(oc - pad_l, orow, len(text) + pad_l + pad_r):
                    c.text(oc, orow, text, fg, flags, clear_dots=True)
                    placed += 1
                    break

    def draw_cursor(self) -> None:
        if self.opts.cursor is None:
            return
        p = self.project1(*self.opts.cursor)
        if p is None:
            return
        col, row = self.canvas.cell_of(*p)
        if 0 <= col < self.canvas.cols and 0 <= row < self.canvas.rows:
            if self.canvas.chars[row, col] == 0 and self.canvas.bits[row, col] == 0:
                self.canvas.text(col, row, "+", self.theme.accent, BOLD)
            self.canvas.flags[row, col] |= REVERSE

    # ---------------------------------------------------------------- main
    def render(self) -> RenderResult:
        self.draw_background()
        self.draw_grid()
        self.draw_constellations()
        self.draw_ecliptic()
        if self.window:
            self.draw_window_ground()
        self.draw_stars()
        self.draw_asterisms()
        self.draw_deep_sky()
        self.draw_highlights()
        self.draw_horizon()
        self.draw_bodies()
        self.draw_satellites()
        self.place_labels()
        self.draw_cursor()
        frame = self.canvas.frame()
        if self.window:
            frame = self._append_compass(frame)
        return RenderResult(
            frame,
            self.hits,
            self.proj,
            self.canvas.cols,
            self.canvas.rows,
            self.canvas.sub_x,
            self.canvas.sub_y,
        )

    def _append_compass(self, frame: Frame) -> Frame:
        t = self.theme
        cols = frame.chars.shape[1]
        chars = np.full((1, cols), ord(" "), dtype=np.uint32)
        fg = np.full((1, cols), t.muted, dtype=np.uint32)
        bg = np.full((1, cols), t.ground, dtype=np.uint32)
        flags = np.zeros((1, cols), dtype=np.uint8)
        taken = np.zeros(cols, dtype=bool)
        for col, name, major in sorted(self.compass_row(), key=lambda e: not e[2]):
            start = max(0, min(cols - len(name), col - len(name) // 2))
            if taken[start : start + len(name)].any():
                continue
            for i, ch in enumerate(name):
                chars[0, start + i] = ord(ch)
                fg[0, start + i] = t.text if major else t.suppressed
                flags[0, start + i] = BOLD if major else 0
            taken[max(0, start - 1) : start + len(name) + 1] = True
        return Frame(
            np.vstack([frame.chars, chars]),
            np.vstack([frame.fg, fg]),
            np.vstack([frame.bg, bg]),
            np.vstack([frame.flags, flags]),
        )


@lru_cache(maxsize=2)
def catalog_star_colors(cat: Catalog) -> NDArray[np.uint32]:
    """B−V colours of all catalog stars (cached)."""
    return star_colors(cat.bv)


def _dilate(a: NDArray[np.float64]) -> NDArray[np.float64]:
    out = a.copy()
    out[1:, :] = np.maximum(out[1:, :], a[:-1, :])
    out[:-1, :] = np.maximum(out[:-1, :], a[1:, :])
    out[:, 1:] = np.maximum(out[:, 1:], a[:, :-1])
    out[:, :-1] = np.maximum(out[:, :-1], a[:, 1:])
    return out


def _roof_heights(az: FloatArray) -> FloatArray:
    """Deterministic skyline (degrees above the horizon) as a function of azimuth.

    Buildings are 4–8° wide blocks with flat roofs, a few chimneys and gaps.
    """
    az = np.asarray(az, dtype=np.float64) % 360.0
    block = np.floor(az / 6.0).astype(np.int64)
    h = ((block * 2654435761) % 1000) / 1000.0  # pseudo random 0..1
    height = np.where(h < 0.15, 0.0, 1.2 + 3.8 * h)
    within = (az % 6.0) / 6.0
    chimney = ((block * 40503) % 7 == 0) & (within > 0.6) & (within < 0.7)
    height = np.where(chimney, height + 1.0, height)
    return np.asarray(height)


def render_sky(scene: SkyScene, opts: ViewOptions, cols: int, rows: int) -> RenderResult:
    """Render the sky scene into ``cols × rows`` terminal cells."""
    return SkyRenderer(scene, opts, cols, rows).render()


__all__ = [
    "BOLD",
    "COMPASS",
    "DIM",
    "UNDERLINE",
    "Hit",
    "Layers",
    "RenderResult",
    "SkyRenderer",
    "ViewOptions",
    "compass_name",
    "render_sky",
    "wrap180",
]
