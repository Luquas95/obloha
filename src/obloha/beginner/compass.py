"""Phone compass via Termux:API (``termux-sensor``), behind a testable abstraction."""

from __future__ import annotations

import contextlib
import json
import math
import os
import shutil
import subprocess
import threading
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

Vector = tuple[float, float, float]


@dataclass(frozen=True)
class SensorSample:
    accel: Vector
    magnet: Vector


class SensorSource(Protocol):
    """Anything that yields accelerometer + magnetometer samples."""

    def samples(self) -> Iterator[SensorSample]: ...

    def close(self) -> None: ...


def termux_available(env: dict[str, str] | None = None) -> bool:
    """True only when running directly in Termux (not over SSH) with Termux:API."""
    e = os.environ if env is None else env
    in_termux = "TERMUX_VERSION" in e or "com.termux" in e.get("PREFIX", "")
    over_ssh = "SSH_CONNECTION" in e or "SSH_TTY" in e
    return in_termux and not over_ssh and shutil.which("termux-sensor") is not None


def heading_and_pitch(sample: SensorSample) -> tuple[float, float]:
    """Tilt-compensated heading of the phone's back camera and its elevation.

    The phone is held upright (portrait, screen towards you); the direction it
    "looks" is the back of the device (−z). Returns (azimuth°, altitude°).
    """
    ax, ay, az = sample.accel
    mx, my, mz = sample.magnet
    g = math.sqrt(ax * ax + ay * ay + az * az) or 1.0
    # gravity points "down" in device coordinates; up vector is the accel vector
    up = (ax / g, ay / g, az / g)
    # east = magnet × up, north = up × east  (Android getRotationMatrix)
    ex, ey, ez = my * up[2] - mz * up[1], mz * up[0] - mx * up[2], mx * up[1] - my * up[0]
    en = math.sqrt(ex * ex + ey * ey + ez * ez) or 1.0
    east = (ex / en, ey / en, ez / en)
    north = (
        up[1] * east[2] - up[2] * east[1],
        up[2] * east[0] - up[0] * east[2],
        up[0] * east[1] - up[1] * east[0],
    )
    look = (0.0, 0.0, -1.0)  # out of the back of the phone
    e = sum(a * b for a, b in zip(look, east, strict=True))
    n = sum(a * b for a, b in zip(look, north, strict=True))
    u = sum(a * b for a, b in zip(look, up, strict=True))
    azimuth = math.degrees(math.atan2(e, n)) % 360.0
    altitude = math.degrees(math.asin(max(-1.0, min(1.0, u))))
    return azimuth, altitude


class Compass:
    """Smooths headings and detects unstable readings."""

    def __init__(self, alpha: float = 0.25, window: int = 12, unstable_deg: float = 20.0):
        self.alpha = alpha
        self.unstable_deg = unstable_deg
        self._x: float | None = None
        self._y = 0.0
        self._alt: float | None = None
        self._recent: deque[float] = deque(maxlen=window)

    def update(self, sample: SensorSample) -> tuple[float, float]:
        az, alt = heading_and_pitch(sample)
        self._recent.append(az)
        cx, cy = math.cos(math.radians(az)), math.sin(math.radians(az))
        if self._x is None or self._alt is None:
            self._x, self._y, self._alt = cx, cy, alt
        else:
            self._x += self.alpha * (cx - self._x)
            self._y += self.alpha * (cy - self._y)
            self._alt += self.alpha * (alt - self._alt)
        return self.heading, self.altitude

    @property
    def heading(self) -> float:
        if self._x is None:
            return 0.0
        return math.degrees(math.atan2(self._y, self._x)) % 360.0

    @property
    def altitude(self) -> float:
        return self._alt or 0.0

    @property
    def spread(self) -> float:
        """Circular standard deviation of the recent raw headings (degrees)."""
        if len(self._recent) < 3:
            return 0.0
        xs = [math.cos(math.radians(a)) for a in self._recent]
        ys = [math.sin(math.radians(a)) for a in self._recent]
        r = math.hypot(sum(xs) / len(xs), sum(ys) / len(ys))
        return math.degrees(math.sqrt(max(0.0, -2.0 * math.log(max(r, 1e-9)))))

    @property
    def unstable(self) -> bool:
        return self.spread > self.unstable_deg

    def warning(self) -> str | None:
        if self.unstable:
            return (
                "Kompas je nestabilní: zkalibruj ho opisováním osmičky telefonem a vzdal "
                "se od kovových předmětů."
            )
        return None


class FakeSensor:
    """Replays fixed samples (tests, demos)."""

    def __init__(self, samples: list[SensorSample]) -> None:
        self._samples = samples

    def samples(self) -> Iterator[SensorSample]:
        yield from self._samples

    def close(self) -> None:
        return None


class TermuxSensor:
    """Streams ``termux-sensor`` JSON output (requires the Termux:API add-on)."""

    def __init__(self, delay_ms: int = 200) -> None:
        self.proc = subprocess.Popen(
            ["termux-sensor", "-s", "accelerometer,magnetic", "-d", str(delay_ms)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )

    def samples(self) -> Iterator[SensorSample]:
        assert self.proc.stdout is not None
        buf = ""
        accel: Vector | None = None
        magnet: Vector | None = None
        for line in self.proc.stdout:
            buf += line
            if line.strip() != "}":
                continue
            try:
                data = json.loads(buf)
            except ValueError:
                continue
            finally:
                buf = ""
            for key, value in data.items():
                vals = value.get("values", [])
                if len(vals) < 3:
                    continue
                vec = (float(vals[0]), float(vals[1]), float(vals[2]))
                if "acc" in key.lower():
                    accel = vec
                elif "mag" in key.lower():
                    magnet = vec
            if accel and magnet:
                yield SensorSample(accel, magnet)

    def close(self) -> None:
        self.proc.terminate()
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(["termux-sensor", "-c"], check=False, timeout=2, capture_output=True)


class CompassReader:
    """Background thread feeding a :class:`Compass` from a :class:`SensorSource`."""

    def __init__(self, source: SensorSource, compass: Compass | None = None) -> None:
        self.source = source
        self.compass = compass or Compass()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop = threading.Event()

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        for sample in self.source.samples():
            if self._stop.is_set():
                break
            self.compass.update(sample)

    def stop(self) -> None:
        self._stop.set()
        self.source.close()
