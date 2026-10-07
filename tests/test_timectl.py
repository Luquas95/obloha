from datetime import UTC, datetime, timedelta

import pytest

from obloha.core.ephem import MAX_DATE, OutOfRangeError
from obloha.core.timectl import TimeController


class Clock:
    def __init__(self, t: float = 1_790_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def test_live_follows_clock():
    c = Clock()
    tc = TimeController(clock=c)
    assert tc.live and tc.status == "živě"
    c.t += 10
    assert tc.now() == datetime.fromtimestamp(c.t, UTC)


def test_pause_run_and_rates():
    c = Clock()
    tc = TimeController(clock=c)
    tc.toggle_pause()
    start = tc.now()
    assert not tc.live and tc.paused and tc.status == "zastaveno"
    c.t += 5
    assert tc.now() == start
    tc.toggle_pause()  # run at 1×
    assert tc.status == "běží"
    c.t += 5
    assert tc.now() == start + timedelta(seconds=5)
    tc.toggle_pause()
    assert tc.paused
    tc.change_rate(True)
    assert tc.rate == 10 and not tc.paused and tc.status == "×10"
    c.t += 2
    assert tc.now() == start + timedelta(seconds=25)
    for _ in range(10):
        tc.change_rate(False)
    assert tc.rate == -1000
    tc.go_live()
    assert tc.live and tc.rate == 1


def test_rate_from_live_and_steps():
    c = Clock()
    tc = TimeController(clock=c)
    tc.change_rate(True)
    assert not tc.live and tc.rate == 10
    tc.step_forward()
    tc.cycle_step()
    assert tc.step == timedelta(days=1)
    tc.cycle_step()
    assert tc.step == timedelta(minutes=1)


def test_fixed_and_range():
    when = datetime(2026, 10, 1, 19, tzinfo=UTC)
    tc = TimeController.fixed(when)
    assert tc.now() == when
    tc.shift(timedelta(hours=2))
    assert tc.now() == when + timedelta(hours=2)
    with pytest.raises(OutOfRangeError):
        tc.set_time(datetime(2051, 1, 1, tzinfo=UTC))
    with pytest.raises(OutOfRangeError):
        TimeController.fixed(datetime(1800, 1, 1, tzinfo=UTC))


def test_running_off_the_end_stops():
    c = Clock()
    tc = TimeController(clock=c)
    tc.set_time(MAX_DATE - timedelta(days=2))
    tc.change_rate(True)
    for _ in range(3):
        tc.change_rate(True)
    c.t += 10 * 86400
    t = tc.now()
    assert t < MAX_DATE and tc.paused
