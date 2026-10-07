#!/usr/bin/env python3
"""Print a rendered sky frame to the terminal (truecolor ANSI) for quick checks.

Usage: uv run python scripts/preview.py [full|direction|window] [cols] [rows] [--plain]
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from obloha.core.location import PRAGUE
from obloha.core.sky import build_scene
from obloha.render.canvas import BOLD
from obloha.render.sky import Layers, ViewOptions, render_sky


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    kind = args[0] if args else "full"
    cols = int(args[1]) if len(args) > 1 else 82
    rows = int(args[2]) if len(args) > 2 else 34
    plain = "--plain" in sys.argv
    scene = build_scene(datetime(2026, 10, 1, 19, 0, tzinfo=UTC), PRAGUE)
    beginner = kind == "window"
    opts = ViewOptions(
        kind=kind,  # type: ignore[arg-type]
        center_az=180.0,
        fov=150.0 if beginner else 90.0,
        limiting_mag=3.5 if beginner else 5.5,
        beginner=beginner,
        max_labels=6 if beginner else None,
        half="--half" in sys.argv,
        ascii_symbols="--half" in sys.argv,
        layers=Layers(asterisms=beginner),
    )
    res = render_sky(scene, opts, cols, rows)
    f = res.frame
    for r in range(f.chars.shape[0]):
        if plain:
            print(f.row_text(r))
            continue
        out = []
        for seg in f.row_segments(r):
            fr, fgc, fb = (seg.fg >> 16) & 255, (seg.fg >> 8) & 255, seg.fg & 255
            br, bgc, bb = (seg.bg >> 16) & 255, (seg.bg >> 8) & 255, seg.bg & 255
            bold = "\x1b[1m" if seg.flags & BOLD else ""
            out.append(f"\x1b[38;2;{fr};{fgc};{fb};48;2;{br};{bgc};{bb}m{bold}{seg.text}\x1b[0m")
        print("".join(out))


if __name__ == "__main__":
    main()
