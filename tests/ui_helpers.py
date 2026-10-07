"""Helpers for deterministic UI tests (fixed time and place, offline)."""

from __future__ import annotations

from datetime import UTC, datetime

from obloha.config import State, load_config
from obloha.core.location import Location
from obloha.ui.app import ObloApp
from obloha.ui.model import AppModel

FIXED = datetime(2026, 10, 1, 19, 0, tzinfo=UTC)


def make_app(
    location: Location | None = None,
    ascii_mode: bool = False,
    colors256: bool = False,
    mode: str | None = None,
    compass: bool = False,
    compass_factory=None,  # type: ignore[no-untyped-def]
    persist: bool = False,
) -> ObloApp:
    cfg, doc = load_config()
    if mode:
        cfg.display.mode = mode  # type: ignore[assignment]
    model = AppModel(
        cfg,
        doc,
        State(),
        location=location,
        fixed_time=FIXED,
        offline=True,
        persist=persist,
        ascii_mode=ascii_mode,
        colors256=colors256,
    )
    return ObloApp(
        model,
        sync=True,
        network=False,
        compass_available=lambda: compass,
        compass_factory=compass_factory,
    )
