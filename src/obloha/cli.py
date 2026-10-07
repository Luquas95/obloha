"""Command line entry point."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from obloha import __version__


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="obloha",
        description="Terminálové planetárium: co je právě teď na obloze nad tebou.",
        epilog="Proměnné prostředí: OBLOHA_LAT, OBLOHA_LON, OBLOHA_PLACE (město).",
    )
    p.add_argument("--version", action="version", version=f"obloha {__version__}")
    p.add_argument("--lat", type=str, help="zeměpisná šířka (desetinně nebo 50°4'N)")
    p.add_argument("--lon", type=str, help="zeměpisná délka (desetinně nebo 14°26'E)")
    p.add_argument("--elevation", type=float, default=None, help="nadmořská výška v m")
    p.add_argument("--place", help="místo podle názvu města, např. „Brno“")
    p.add_argument("--time", help="pevný čas, např. „2026-10-01 21:00“ (v pásmu místa)")
    p.add_argument("--ascii", action="store_true", help="bezpečný režim znaků (půlbloky)")
    p.add_argument(
        "--colors",
        choices=["auto", "truecolor", "256"],
        default=None,
        help="barevný režim (výchozí podle COLORTERM/TERM)",
    )
    p.add_argument("--offline", action="store_true", help="nestahovat nic ze sítě")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--advanced", action="store_true", help="spustit v pokročilém režimu")
    mode.add_argument("--beginner", action="store_true", help="spustit v začátečnickém režimu")
    p.add_argument("--night", action="store_true", help="noční vidění (červené barvy)")
    p.add_argument("--config", help="cesta ke config.toml")
    p.add_argument("--web", action="store_true", help="spustit v prohlížeči (textual-serve)")
    p.add_argument(
        "--host",
        default="127.0.0.1",
        help="adresa pro --web (výchozí jen 127.0.0.1; rozhraní nemá přihlášení!)",
    )
    p.add_argument("--port", type=int, default=8000, help="port pro --web")
    return p


def resolve_location(args: argparse.Namespace, env: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    """Location from --lat/--lon, --place or OBLOHA_* variables (None = config)."""
    from obloha.core.cities import city_db, parse_coordinates, timezone_at
    from obloha.core.location import Location

    e = os.environ if env is None else env
    lat = args.lat or e.get("OBLOHA_LAT")
    lon = args.lon or e.get("OBLOHA_LON")
    place = args.place or e.get("OBLOHA_PLACE")
    if lat or lon:
        if not (lat and lon):
            raise SystemExit("Zadej obě souřadnice: --lat i --lon.")
        try:
            la, lo = float(lat.replace(",", ".")), float(lon.replace(",", "."))
        except ValueError:
            try:
                la, lo = parse_coordinates(f"{lat} {lon}")
            except ValueError as exc:
                raise SystemExit(f"Nerozumím souřadnicím: {exc}") from exc
        if not (-90 <= la <= 90 and -180 <= lo <= 180):
            raise SystemExit("Souřadnice jsou mimo rozsah.")
        near = city_db().nearest(la, lo)
        return Location(
            f"{la:.3f}, {lo:.3f}".replace(".", ","),
            la,
            lo,
            args.elevation or 0.0,
            timezone_at(la, lo),
            f"u obce {near.name}",
        )
    if place:
        found = city_db().search(place, 1)
        if not found:
            raise SystemExit(f"Místo „{place}“ jsem nenašel.")
        return found[0].to_location()
    return None


def parse_time_arg(text: str, zone) -> datetime:  # type: ignore[no-untyped-def]
    from obloha.ui.modals import parse_time_input

    return parse_time_input(text, datetime.now(UTC), zone)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.web:
        from obloha.web import serve

        forwarded = [a for a in (argv if argv is not None else sys.argv[1:]) if a not in ("--web",)]
        return serve(args.host, args.port, forwarded)
    return run_app(args)


def run_app(args: argparse.Namespace) -> int:  # pragma: no cover - interactive
    from pathlib import Path

    from obloha import terminal
    from obloha.config import ConfigError, load_config, load_state
    from obloha.keymap import Keymap, KeymapError
    from obloha.ui.app import ObloApp
    from obloha.ui.model import AppModel

    cfg_path = Path(args.config) if args.config else None
    try:
        cfg, doc = load_config(cfg_path)
        keymap = Keymap(overrides=cfg.keys)
    except (ConfigError, KeymapError) as exc:
        print(f"obloha: {exc}", file=sys.stderr)
        return 2
    if args.advanced:
        cfg.display.mode = "advanced"
    if args.beginner:
        cfg.display.mode = "beginner"
    if args.night:
        cfg.display.night = True
    state = load_state()
    location = resolve_location(args)
    zone = (location or cfg.location.to_location()).zone
    fixed = parse_time_arg(args.time, zone) if args.time else None
    colors = args.colors or cfg.display.colors
    if colors == "auto":
        colors = terminal.color_mode()
    os.environ.setdefault("TEXTUAL_COLOR_SYSTEM", "truecolor" if colors == "truecolor" else "256")
    notice = None
    problem = terminal.char_problem(tmux=terminal.tmux_version(terminal.in_tmux()))
    if problem and not (args.ascii or cfg.display.ascii) and not state.ascii_offered:
        notice = (
            f"Možný problém se znaky ({problem}). Pokud se mapa rozpadá, spusť "
            "obloha --ascii nebo zapni bezpečný režim v Nastavení (5)."
        )
        state.ascii_offered = True
    model = AppModel(
        cfg,
        doc,
        state,
        location=location,
        fixed_time=fixed,
        offline=True if args.offline else None,
        ascii_mode=True if args.ascii else None,
        colors256=colors == "256",
    )
    if location is not None:
        model.persist_location = False  # type: ignore[attr-defined]
    app = ObloApp(model, keymap, ssh=terminal.is_ssh(), startup_notice=notice)
    app.run()
    return 0
