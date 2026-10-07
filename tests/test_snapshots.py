"""Snapshot tests of the main screens (pytest-textual-snapshot).

Fixed time 1. 10. 2026 21:00 SELČ and fixed place: fully deterministic.
Update with ``pytest --snapshot-update``.
"""

import pytest

from obloha.core.cities import city_db
from tests.ui_helpers import make_app

pytestmark = pytest.mark.ui

SIZES = {"mobil": (46, 44), "80x24": (80, 24), "120x40": (120, 40), "160x48": (160, 48)}


@pytest.mark.parametrize("size", list(SIZES))
def test_beginner_window(snap_compare, size):
    assert snap_compare(make_app(), terminal_size=SIZES[size])


@pytest.mark.parametrize("size", list(SIZES))
def test_advanced_sky(snap_compare, size):
    assert snap_compare(make_app(mode="advanced"), terminal_size=SIZES[size])


@pytest.mark.parametrize("size", ["mobil", "120x40"])
def test_tonight(snap_compare, size):
    assert snap_compare(make_app(), terminal_size=SIZES[size], press=["2"])


def test_events(snap_compare):
    assert snap_compare(make_app(), terminal_size=(120, 40), press=["4"])


def test_mobile_brno(snap_compare):
    brno = city_db().find("Brno", "CZ").to_location()
    assert snap_compare(make_app(location=brno, mode="advanced"), terminal_size=(46, 44))


def test_ascii_mode(snap_compare):
    assert snap_compare(make_app(ascii_mode=True, mode="advanced"), terminal_size=(100, 32))


def test_256_colors(snap_compare):
    assert snap_compare(make_app(colors256=True, mode="advanced"), terminal_size=(100, 32))


def test_night_vision(snap_compare):
    assert snap_compare(make_app(mode="advanced"), terminal_size=(120, 40), press=["n"])


def test_lesson(snap_compare):
    assert snap_compare(make_app(), terminal_size=(120, 40), press=["u", "x"])
