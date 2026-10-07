"""Sky map widget: shows frames rendered by the core renderer, row by row."""

from __future__ import annotations

from collections.abc import Callable

from rich.color import Color
from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.geometry import Region
from textual.message import Message
from textual.strip import Strip
from textual.widget import Widget

from obloha.core.sky import ObjectRef
from obloha.render.canvas import BOLD, DIM, REVERSE, UNDERLINE, Frame
from obloha.render.sky import RenderResult

Renderer = Callable[[int, int], RenderResult]

_STYLE_CACHE: dict[tuple[int, int, int], Style] = {}


def style_for(fg: int, bg: int, flags: int) -> Style:
    key = (fg, bg, flags)
    st = _STYLE_CACHE.get(key)
    if st is None:
        st = Style(
            color=Color.from_rgb((fg >> 16) & 255, (fg >> 8) & 255, fg & 255),
            bgcolor=Color.from_rgb((bg >> 16) & 255, (bg >> 8) & 255, bg & 255),
            bold=bool(flags & BOLD),
            underline=bool(flags & UNDERLINE),
            dim=bool(flags & DIM),
            reverse=bool(flags & REVERSE),
        )
        _STYLE_CACHE[key] = st
    return st


def frame_strip(frame: Frame, row: int) -> Strip:
    segs = [Segment(s.text, style_for(s.fg, s.bg, s.flags)) for s in frame.row_segments(row)]
    return Strip(segs, frame.chars.shape[1])


class SkyMap(Widget):
    """Displays a :class:`RenderResult`; handles taps, drags and double taps."""

    DEFAULT_CSS = """
    SkyMap { width: 1fr; height: 1fr; }
    """
    can_focus = True

    class Picked(Message):
        """User tapped/clicked on the map (object may be None)."""

        def __init__(self, ref: ObjectRef | None, alt: float, az: float, double: bool) -> None:
            super().__init__()
            self.ref = ref
            self.alt = alt
            self.az = az
            self.double = double

    class Dragged(Message):
        """Map dragged by ``dx``/``dy`` cells."""

        def __init__(self, dx: int, dy: int) -> None:
            super().__init__()
            self.dx = dx
            self.dy = dy

    def __init__(self, renderer: Renderer, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.renderer = renderer
        self.result: RenderResult | None = None
        self._strips: list[Strip] = []
        self._keys: list[bytes] = []
        self._drag_from: tuple[int, int] | None = None
        self._dragged = False
        self.redraws = 0
        self.rows_repainted = 0

    def on_resize(self, event: events.Resize) -> None:
        self.redraw(full=True)

    def on_mount(self) -> None:
        self.redraw(full=True)

    def redraw(self, full: bool = False) -> None:
        w, h = self.size.width, self.size.height
        if w < 4 or h < 3:
            return
        self.result = self.renderer(w, h)
        frame = self.result.frame
        rows = frame.chars.shape[0]
        new_keys = [frame.row_key(r) for r in range(rows)]
        changed = [r for r in range(rows) if full or r >= len(self._keys)
                   or self._keys[r] != new_keys[r]]
        strips = self._strips if len(self._strips) == rows else [Strip.blank(w)] * rows
        strips = list(strips)
        for r in changed:
            strips[r] = frame_strip(frame, r)
        self._strips = strips
        self._keys = new_keys
        self.redraws += 1
        self.rows_repainted += len(changed)
        if full or len(changed) > rows // 2:
            self.refresh()
        else:
            for r in changed:
                self.refresh(Region(0, r, w, 1))

    def render_line(self, y: int) -> Strip:
        if 0 <= y < len(self._strips):
            return self._strips[y]
        return Strip.blank(self.size.width)

    # ------------------------------------------------------------------ mouse / touch
    def _pick(self, x: int, y: int, double: bool) -> None:
        if self.result is None:
            return
        hit = self.result.nearest(x, y)
        pos = self.result.cell_altaz(x, y)
        if pos is None and hit is None:
            return
        alt, az = pos if pos is not None else (0.0, 0.0)
        self.post_message(self.Picked(hit.ref if hit else None, alt, az, double))

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._drag_from = (event.x, event.y)
        self._dragged = False
        self.capture_mouse()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._drag_from is None or not event.button:
            return
        dx = event.x - self._drag_from[0]
        dy = event.y - self._drag_from[1]
        if abs(dx) >= 2 or abs(dy) >= 1:
            self._dragged = True
            self._drag_from = (event.x, event.y)
            self.post_message(self.Dragged(dx, dy))

    def on_mouse_up(self, event: events.MouseUp) -> None:
        self.release_mouse()
        self._drag_from = None

    def on_click(self, event: events.Click) -> None:
        if self._dragged:
            self._dragged = False
            return
        self.focus()
        self._pick(event.x, event.y, event.chain >= 2)
