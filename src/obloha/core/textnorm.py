"""Text normalisation for diacritics-insensitive search."""

from __future__ import annotations

import unicodedata


def fold(text: str) -> str:
    """Lowercase and strip diacritics: ``"České Budějovice" -> "ceske budejovice"``."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.casefold().replace("-", " ").split())


def levenshtein(a: str, b: str, limit: int = 3) -> int:
    """Damerau-Levenshtein (optimal string alignment) distance, capped at ``limit + 1``."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2: list[int] = []
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        row_min = cur[0]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                v = min(v, prev2[j - 2] + 1)
            cur[j] = v
            row_min = min(row_min, v)
        if row_min > limit:
            return limit + 1
        prev2, prev = prev, cur
    return min(prev[-1], limit + 1)
