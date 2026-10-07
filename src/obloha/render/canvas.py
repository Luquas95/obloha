"""Sub-pixel canvas rendered into terminal cells (braille or half blocks).

The canvas is pure numpy; the UI only turns finished rows into styled text.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

from obloha.render.color import quantize_256, to_night_array

FloatArray = NDArray[np.float64]

#: Braille dot bit for (dot row 0..3, dot column 0..1) inside a cell.
BRAILLE_BITS = np.array([[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]], dtype=np.uint8)
HALF_GLYPHS = {1: "▀", 2: "▄", 3: "█"}

BOLD = 1
UNDERLINE = 2
DIM = 4
REVERSE = 8


class Segment(NamedTuple):
    """A run of cells with the same style."""

    text: str
    fg: int
    bg: int
    flags: int


@dataclass
class Frame:
    """Finished cell grid."""

    chars: NDArray[np.uint32]  # codepoints
    fg: NDArray[np.uint32]
    bg: NDArray[np.uint32]
    flags: NDArray[np.uint8]

    @property
    def size(self) -> tuple[int, int]:
        rows, cols = self.chars.shape
        return cols, rows

    def row_segments(self, row: int) -> list[Segment]:
        chars, fg, bg, fl = self.chars[row], self.fg[row], self.bg[row], self.flags[row]
        out: list[Segment] = []
        start = 0
        n = len(chars)
        for i in range(1, n + 1):
            if i == n or fg[i] != fg[start] or bg[i] != bg[start] or fl[i] != fl[start]:
                text = "".join(map(chr, chars[start:i]))
                out.append(Segment(text, int(fg[start]), int(bg[start]), int(fl[start])))
                start = i
        return out

    def row_text(self, row: int) -> str:
        return "".join(map(chr, self.chars[row]))

    def text(self) -> str:
        return "\n".join(self.row_text(r) for r in range(self.chars.shape[0]))

    def row_key(self, row: int) -> bytes:
        """Hash of a row, used to repaint only rows that changed."""
        h = hashlib.blake2b(digest_size=12)
        for arr in (self.chars, self.fg, self.bg, self.flags):
            h.update(arr[row].tobytes())
        return h.digest()

    def converted(self, night: bool = False, colors256: bool = False) -> Frame:
        fg, bg = self.fg, self.bg
        if night:
            fg, bg = to_night_array(fg), to_night_array(bg)
        if colors256:
            fg, bg = quantize_256(fg), quantize_256(bg)
        return Frame(self.chars, fg, bg, self.flags)


class Canvas:
    """Drawing surface with ``cols × rows`` cells."""

    def __init__(self, cols: int, rows: int, half: bool = False, bg: int = 0) -> None:
        self.cols = max(1, cols)
        self.rows = max(1, rows)
        self.half = half
        self.sub_x = 1 if half else 2
        self.sub_y = 2 if half else 4
        self.width = self.cols * self.sub_x
        self.height = self.rows * self.sub_y
        shape = (self.rows, self.cols)
        self.bits = np.zeros(shape, dtype=np.uint8)
        self.dot_fg = np.zeros(shape, dtype=np.uint32)
        self.dot_prio = np.full(shape, -np.inf, dtype=np.float64)
        self.bg = np.full(shape, bg, dtype=np.uint32)
        self.chars = np.zeros(shape, dtype=np.uint32)
        self.fg = np.zeros(shape, dtype=np.uint32)
        self.flags = np.zeros(shape, dtype=np.uint8)
        self.text_bg = np.zeros(shape, dtype=np.uint32)
        self.has_text_bg = np.zeros(shape, dtype=bool)
        self.occupied = np.zeros(shape, dtype=bool)
        #: plain ASCII glyphs instead of half blocks (". + * # _" by dot priority)
        self.ascii_glyphs = False

    # ------------------------------------------------------------------ dots
    def dots(
        self,
        x: FloatArray,
        y: FloatArray,
        color: NDArray[np.uint32] | int,
        prio: FloatArray | float = 0.0,
    ) -> None:
        """Plot dots (vectorised). Higher ``prio`` wins the cell's colour."""
        xi = np.rint(np.asarray(x, dtype=np.float64)).astype(np.int64)
        yi = np.rint(np.asarray(y, dtype=np.float64)).astype(np.int64)
        ok = (xi >= 0) & (xi < self.width) & (yi >= 0) & (yi < self.height)
        if not ok.any():
            return
        xi, yi = xi[ok], yi[ok]
        col_arr = np.broadcast_to(np.asarray(color, dtype=np.uint32), ok.shape)[ok]
        pr = np.broadcast_to(np.asarray(prio, dtype=np.float64), ok.shape)[ok]
        r, c = yi // self.sub_y, xi // self.sub_x
        if self.half:
            bit = np.where(yi % 2 == 0, 1, 2).astype(np.uint8)
        else:
            bit = BRAILLE_BITS[yi % 4, xi % 2]
        np.bitwise_or.at(self.bits, (r, c), bit)
        order = np.argsort(pr, kind="stable")
        r, c, pr, col_arr = r[order], c[order], pr[order], col_arr[order]
        np.maximum.at(self.dot_prio, (r, c), pr)
        win = pr >= self.dot_prio[r, c]
        self.dot_fg[r[win], c[win]] = col_arr[win]

    def line(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        color: int,
        prio: float = 0.0,
        dash: int = 0,
    ) -> None:
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        if n > 4 * (self.width + self.height):
            return
        t = np.linspace(0.0, 1.0, n + 1)
        xs = x0 + (x1 - x0) * t
        ys = y0 + (y1 - y0) * t
        if dash:
            keep = (np.arange(len(t)) // dash) % 2 == 0
            xs, ys = xs[keep], ys[keep]
        self.dots(xs, ys, color, prio)

    def polyline(
        self,
        x: FloatArray,
        y: FloatArray,
        mask: NDArray[np.bool_],
        color: int,
        prio: float = 0.0,
        dash: int = 0,
        max_jump: float | None = None,
    ) -> None:
        """Draw consecutive segments where both ends are in ``mask``."""
        limit = max_jump if max_jump is not None else (self.width + self.height) / 3
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        if len(x) < 2:
            return
        m = np.asarray(mask[:-1] & mask[1:], dtype=bool)
        m &= (np.abs(x[1:] - x[:-1]) + np.abs(y[1:] - y[:-1])) <= limit
        self.segments(x[:-1][m], y[:-1][m], x[1:][m], y[1:][m], color, prio, dash)

    def segments(
        self,
        x0: FloatArray,
        y0: FloatArray,
        x1: FloatArray,
        y1: FloatArray,
        color: int,
        prio: float = 0.0,
        dash: int = 0,
    ) -> None:
        """Draw many independent segments at once (vectorised)."""
        if len(x0) == 0:
            return
        lengths = np.maximum(np.abs(x1 - x0), np.abs(y1 - y0)).astype(np.int64) + 1
        lengths = np.minimum(lengths, 2 * (self.width + self.height))
        total = int(lengths.sum())
        seg = np.repeat(np.arange(len(x0)), lengths)
        starts = np.repeat(np.cumsum(lengths) - lengths, lengths)
        k = np.arange(total) - starts
        t = k / np.maximum(lengths[seg] - 1, 1)
        xs = x0[seg] + (x1[seg] - x0[seg]) * t
        ys = y0[seg] + (y1[seg] - y0[seg]) * t
        if dash:
            keep = (k // dash) % 2 == 0
            xs, ys = xs[keep], ys[keep]
        self.dots(xs, ys, color, prio)

    # ------------------------------------------------------------------ text
    def cell_of(self, x: float, y: float) -> tuple[int, int]:
        return round(x) // self.sub_x, round(y) // self.sub_y

    def free(self, col: int, row: int, length: int) -> bool:
        if row < 0 or row >= self.rows or col < 0 or col + length > self.cols:
            return False
        return not bool(self.occupied[row, col : col + length].any())

    def text(
        self,
        col: int,
        row: int,
        text: str,
        fg: int,
        flags: int = 0,
        bg: int | None = None,
        force: bool = True,
        clear_dots: bool = True,
    ) -> bool:
        """Write ``text`` at a cell; returns False when it does not fit."""
        if row < 0 or row >= self.rows:
            return False
        if col < 0:
            text = text[-col:]
            col = 0
        text = text[: max(0, self.cols - col)]
        if not text:
            return False
        if not force and not self.free(col, row, len(text)):
            return False
        for i, ch in enumerate(text):
            self.chars[row, col + i] = ord(ch)
            self.fg[row, col + i] = fg
            self.flags[row, col + i] = flags
            if bg is not None:
                self.text_bg[row, col + i] = bg
                self.has_text_bg[row, col + i] = True
            if clear_dots:
                self.bits[row, col + i] = 0
        self.occupied[row, col : col + len(text)] = True
        return True

    def reserve(self, col: int, row: int, length: int = 1) -> None:
        if 0 <= row < self.rows:
            self.occupied[row, max(0, col) : max(0, col + length)] = True

    def fill_bg(self, color: NDArray[np.uint32] | int) -> None:
        self.bg[:] = color

    # ------------------------------------------------------------------ output
    def frame(self) -> Frame:
        chars = self.chars.copy()
        fg = self.fg.copy()
        no_text = chars == 0
        if self.half and self.ascii_glyphs:
            p = self.dot_prio
            glyph = np.full_like(chars, ord("."))
            glyph[p >= -2.5] = ord("+")
            glyph[p >= -1.0] = ord("*")
            glyph[(p >= 45) & (p < 55)] = ord("_")
            glyph[p >= 55] = ord("#")
        elif self.half:
            glyph = np.zeros_like(chars)
            for bits, ch in HALF_GLYPHS.items():
                glyph[self.bits == bits] = ord(ch)
        else:
            glyph = (0x2800 + self.bits.astype(np.uint32)).astype(np.uint32)
        has_dots = self.bits > 0
        use_dots = no_text & has_dots
        chars[use_dots] = glyph[use_dots]
        fg[use_dots] = self.dot_fg[use_dots]
        chars[no_text & ~has_dots] = ord(" ")
        bg = np.where(self.has_text_bg, self.text_bg, self.bg).astype(np.uint32)
        fg[chars == ord(" ")] = bg[chars == ord(" ")]
        return Frame(chars, fg, bg, self.flags.copy())
