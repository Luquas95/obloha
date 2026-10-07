#!/usr/bin/env python3
"""Generate deterministic screenshots of the main screens into docs/screenshots.

Fixed time 1. 10. 2026 21:00 SELČ, Prague (Brno for the mobile view), offline,
satellite passes from the bundled test TLE are not used (no network data).

Run: ``uv run python scripts/screenshots.py [out_dir]``
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXED = datetime(2026, 10, 1, 19, 0, tzinfo=UTC)

SHOTS: list[tuple[str, tuple[int, int], list[str], dict[str, object]]] = [
    ("01-zacatecnik-pohled-z-okna", (120, 40), [], {}),
    ("02-zacatecnik-ukol", (120, 40), ["u", "x"], {}),
    ("03-pokrocily-obloha", (120, 40), ["m"], {}),
    ("04-pokrocily-pohled-jih", (120, 40), ["m", "S"], {}),
    ("05-dnes-v-noci", (120, 40), ["2"], {}),
    ("06-ukazy", (120, 40), ["4"], {}),
    ("07-nocni-videni", (120, 40), ["m", "n"], {}),
    ("08-mobil-zacatecnik", (46, 44), [], {"place": "Brno"}),
    ("09-mobil-pokrocily", (46, 44), ["m"], {"place": "Brno"}),
    ("10-tablet-80x24", (80, 24), [], {}),
    ("11-ascii-rezim", (100, 32), ["m"], {"ascii": True}),
    ("12-nastaveni", (120, 40), ["5"], {}),
    ("13-satelity", (120, 40), ["3"], {}),
    ("14-co-je-to", (120, 40), ["question_mark"], {}),
]


async def shoot(
    name: str, size: tuple[int, int], keys: list[str], opts: dict[str, object], out: Path
) -> Path:
    from obloha.config import State, load_config
    from obloha.core.cities import city_db
    from obloha.ui.app import ObloApp
    from obloha.ui.model import AppModel

    cfg, doc = load_config()
    loc = None
    if "place" in opts:
        loc = city_db().search(str(opts["place"]), 1)[0].to_location()
    model = AppModel(
        cfg,
        doc,
        State(),
        location=loc,
        fixed_time=FIXED,
        offline=True,
        persist=False,
        ascii_mode=bool(opts.get("ascii", False)),
    )
    app = ObloApp(model, sync=True, network=False, compass_available=lambda: False)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        for k in keys:
            await pilot.press(k)
            await pilot.pause()
        await pilot.pause(0.3)
        path = out / f"{name}.svg"
        app.save_screenshot(path.name, path=str(out))
    return path


async def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
            os.environ[var] = tmp
        sys.path.insert(0, str(ROOT / "scripts"))
        from svg2png import convert

        only = os.environ.get("ONLY")
        for name, size, keys, opts in SHOTS:
            if only and only not in name:
                continue
            svg = await shoot(name, size, keys, opts, out)
            convert(svg, svg.with_suffix(".png"))
            print(svg.with_suffix(".png"))


if __name__ == "__main__":
    asyncio.run(main())
