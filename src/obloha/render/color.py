"""Colour helpers: blending, night-vision (red) transform and 256-colour mapping."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from numpy.typing import NDArray

UIntArray = NDArray[np.uint32]


def hex_to_int(value: str) -> int:
    return int(value.lstrip("#"), 16)


def int_to_hex(value: int) -> str:
    return f"#{int(value) & 0xFFFFFF:06x}"


def rgb(value: int) -> tuple[int, int, int]:
    return (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF


def from_rgb(r: float, g: float, b: float) -> int:
    def c(x: float) -> int:
        return max(0, min(255, round(x)))

    return (c(r) << 16) | (c(g) << 8) | c(b)


def blend(a: int, b: int, t: float) -> int:
    """Linear blend from ``a`` (t=0) to ``b`` (t=1)."""
    t = max(0.0, min(1.0, t))
    ra, ga, ba = rgb(a)
    rb, gb, bb = rgb(b)
    return from_rgb(ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t)


def blend_array(a: UIntArray, b: int, t: NDArray[np.float64]) -> UIntArray:
    """Vectorised :func:`blend` of an array of colours towards one colour."""
    t = np.clip(t, 0.0, 1.0)
    out = np.zeros_like(a, dtype=np.uint32)
    for shift in (16, 8, 0):
        ca = ((a >> shift) & 0xFF).astype(np.float64)
        cb = float((b >> shift) & 0xFF)
        out |= (np.rint(ca + (cb - ca) * t).astype(np.uint32) & 0xFF) << shift
    return out


def to_night(value: int) -> int:
    """Map any colour to a red-only shade with the same luminance (night vision)."""
    r, g, b = rgb(value)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    k = lum / 255.0
    return from_rgb(10 + lum * (245 / 255), lum * 0.353 * k, lum * 0.29 * k)


def to_night_array(values: UIntArray) -> UIntArray:
    r = ((values >> 16) & 0xFF).astype(np.float64)
    g = ((values >> 8) & 0xFF).astype(np.float64)
    b = (values & 0xFF).astype(np.float64)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    k = lum / 255.0
    nr = np.clip(np.rint(10 + lum * (245 / 255)), 0, 255).astype(np.uint32)
    ng = np.clip(np.rint(lum * 0.353 * k), 0, 255).astype(np.uint32)
    nb = np.clip(np.rint(lum * 0.29 * k), 0, 255).astype(np.uint32)
    return ((nr << 16) | (ng << 8) | nb).astype(np.uint32)


@lru_cache(maxsize=1)
def xterm_palette() -> NDArray[np.int64]:
    """RGB values of xterm colours 16–255 (6×6×6 cube + grey ramp)."""
    levels = [0, 95, 135, 175, 215, 255]
    cube = [(r, g, b) for r in levels for g in levels for b in levels]
    greys = [(v, v, v) for v in range(8, 239, 10)]
    return np.array(cube + greys, dtype=np.int64)


def quantize_256(values: UIntArray) -> UIntArray:
    """Map colours to the nearest xterm-256 colour (returned as RGB ints)."""
    flat = values.reshape(-1).astype(np.int64)
    uniq, inv = np.unique(flat, return_inverse=True)
    pal = xterm_palette()
    rgbs = np.stack([(uniq >> 16) & 0xFF, (uniq >> 8) & 0xFF, uniq & 0xFF], axis=-1)
    # weighted distance (perceptual-ish)
    w = np.array([2, 4, 3])
    d = (((rgbs[:, None, :] - pal[None, :, :]) ** 2) * w).sum(axis=-1)
    best = pal[np.argmin(d, axis=1)]
    mapped = ((best[:, 0] << 16) | (best[:, 1] << 8) | best[:, 2]).astype(np.uint32)
    return mapped[inv].reshape(values.shape)


def xterm_index(value: int) -> int:
    """Index (16–255) of the nearest xterm colour."""
    pal = xterm_palette()
    r, g, b = rgb(value)
    d = ((pal - np.array([r, g, b])) ** 2 * np.array([2, 4, 3])).sum(axis=1)
    return int(np.argmin(d)) + 16
