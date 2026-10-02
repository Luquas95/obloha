"""Shared fixtures. Tests never touch the network or the user's config."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from obloha.core.location import PRAGUE, Location

#: Fixed moment used by deterministic tests: 1. 10. 2026 21:00 SELČ.
FIXED_UTC = datetime(2026, 10, 1, 19, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolate_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    for var in ("OBLOHA_LAT", "OBLOHA_LON", "OBLOHA_PLACE", "SSH_CONNECTION", "TERMUX_VERSION"):
        monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture
def prague() -> Location:
    return PRAGUE


@pytest.fixture
def fixed_utc() -> datetime:
    return FIXED_UTC
