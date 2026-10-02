"""Application clock: live, paused, stepped and accelerated time."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from obloha.core.ephem import MAX_DATE, MIN_DATE, OutOfRangeError

RATES: tuple[int, ...] = (-1000, -100, -10, -1, 1, 10, 100, 1000)
STEPS: tuple[timedelta, ...] = (
    timedelta(minutes=1),
    timedelta(minutes=10),
    timedelta(hours=1),
    timedelta(days=1),
)


def _clamp(when: datetime) -> datetime:
    if when < MIN_DATE or when >= MAX_DATE:
        raise OutOfRangeError(f"Čas {when:%Y-%m-%d} je mimo rozsah efemeridy DE421 (1900–2049).")
    return when


@dataclass
class TimeController:
    """Keeps the simulated time.

    In *live* mode the time follows the wall clock. Any manual change switches
    to *set* mode where the time either stands still (``paused``) or runs at
    ``rate`` times real speed.
    """

    clock: Callable[[], float] = time.time
    live: bool = True
    paused: bool = False
    rate: int = 1
    step_index: int = 2
    _anchor_sim: datetime = field(default_factory=lambda: datetime.now(UTC))
    _anchor_real: float = 0.0

    def __post_init__(self) -> None:
        self._anchor_real = self.clock()
        if self.live:
            self._anchor_sim = datetime.fromtimestamp(self._anchor_real, UTC)

    @classmethod
    def fixed(cls, when: datetime, clock: Callable[[], float] = time.time) -> TimeController:
        """Create a paused controller at ``when``."""
        tc = cls(clock=clock, live=False, paused=True)
        tc._anchor_sim = _clamp(when.astimezone(UTC))
        return tc

    def now(self) -> datetime:
        """Return the current simulated time (aware, UTC)."""
        real = self.clock()
        if self.live:
            return datetime.fromtimestamp(real, UTC)
        if self.paused:
            return self._anchor_sim
        elapsed = (real - self._anchor_real) * self.rate
        try:
            return _clamp(self._anchor_sim + timedelta(seconds=elapsed))
        except (OutOfRangeError, OverflowError):
            self._anchor_sim = MIN_DATE if self.rate < 0 else MAX_DATE - timedelta(days=1)
            self.paused = True
            return self._anchor_sim

    def _rebase(self) -> None:
        self._anchor_sim = self.now()
        self._anchor_real = self.clock()

    @property
    def step(self) -> timedelta:
        return STEPS[self.step_index]

    @property
    def status(self) -> str:
        """Short Czech status for the header."""
        if self.live:
            return "živě"
        if self.paused:
            return "zastaveno"
        return f"×{self.rate}" if self.rate != 1 else "běží"

    def go_live(self) -> None:
        self.live = True
        self.paused = False
        self.rate = 1

    def toggle_pause(self) -> None:
        """Space: live -> paused, paused -> running, running -> paused."""
        if self.live:
            self._rebase()
            self.live = False
            self.paused = True
        elif self.paused:
            self._anchor_real = self.clock()
            self.paused = False
        else:
            self._rebase()
            self.paused = True

    def set_time(self, when: datetime) -> None:
        """Jump to ``when`` (keeps running/paused state, leaves live mode)."""
        target = _clamp(when.astimezone(UTC))
        was_live = self.live
        self.live = False
        if was_live:
            self.paused = True
        self._anchor_sim = target
        self._anchor_real = self.clock()

    def shift(self, delta: timedelta) -> None:
        self.set_time(self.now() + delta)

    def step_forward(self, n: int = 1) -> None:
        self.shift(self.step * n)

    def cycle_step(self) -> None:
        self.step_index = (self.step_index + 1) % len(STEPS)

    def change_rate(self, faster: bool) -> None:
        """``>``/``<``: move along the rate ladder (also into negative)."""
        if self.live:
            self._rebase()
            self.live = False
        else:
            self._rebase()
        idx = RATES.index(self.rate) if self.rate in RATES else RATES.index(1)
        idx = min(idx + 1, len(RATES) - 1) if faster else max(idx - 1, 0)
        self.rate = RATES[idx]
        self.paused = False
