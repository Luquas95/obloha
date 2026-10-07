#!/usr/bin/env python3
"""Convert Textual SVG screenshots to PNG (cairosvg, monospace font with braille)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import cairosvg

FONT = "DejaVu Sans Mono"
BRAILLE_FONT = "FreeMono"
BRAILLE = re.compile("[\u2800-\u28ff]")


def convert(src: Path, dst: Path, scale: float = 1.5) -> None:
    svg = src.read_text(encoding="utf-8")
    # use a locally installed font with braille glyphs instead of the web font
    svg = re.sub(r"font-family:\s*[^;\"]+", f"font-family: {FONT}", svg)
    svg = re.sub(r"@font-face\s*\{[^}]*\}", "", svg)

    # cairo has no per-glyph font fallback: braille runs need a font that has them
    def braille_font(m: re.Match[str]) -> str:
        if BRAILLE.search(m.group(2)):
            return (
                m.group(1).replace("<text ", f'<text style="font-family: {BRAILLE_FONT}" ', 1)
                + m.group(2)
                + "</text>"
            )
        return m.group(0)

    svg = re.sub(r"(<text [^>]*>)(.*?)</text>", braille_font, svg, flags=re.S)
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(dst), scale=scale)


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        p = Path(arg)
        convert(p, p.with_suffix(".png"))
        print(p.with_suffix(".png"))
