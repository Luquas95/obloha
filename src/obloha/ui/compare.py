"""City comparison table (pure functions, used by the compare dialog)."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from obloha.core.almanac import night_start, rise_transit_set, twilight
from obloha.core.bodies import BODY_BY_ID
from obloha.core.eclipses import find_solar_eclipses
from obloha.core.location import Location
from obloha.core.satellites import passes_for_all
from obloha.ui.formatting import date_short, duration, hm, num

if TYPE_CHECKING:
    from obloha.ui.model import AppModel


def compare_rows(model: AppModel, places: list[Location]) -> list[tuple[str, list[str]]]:
    """Rows (label, value per place) for tonight and the next solar eclipse."""
    now = model.now()
    cols: list[dict[str, str]] = []
    for loc in places:
        z = loc.zone
        start = night_start(now, loc)
        tw = twilight(start, loc)
        moon = rise_transit_set(BODY_BY_ID["moon"], start, loc)
        row = {
            "zeměpisná šířka": f"{num(loc.lat, 2)}°",
            "časové pásmo": loc.tz,
            "západ Slunce": hm(tw.sunset, z),
            "tma (konec astr. soumraku)": hm(tw.astro_end, z) if tw.astro_end else "není",
            "astronomická noc": duration(tw.astro_night) if tw.astro_night else "není",
            "východ Slunce": hm(tw.sunrise, z),
            "východ Měsíce": hm(moon.rise, z),
            "výška Polárky": f"{max(loc.lat, 0):.0f}°" if loc.lat > 0 else "pod obzorem",
        }
        if model.sats:
            passes = [p for p in passes_for_all(model.sats[:3], start, loc, days=1) if p.visible]
            best = max(passes, key=lambda p: p.peak.alt, default=None)
            row["ISS nejvýš (dnes v noci)"] = (
                f"{hm(best.peak.when, z)} {best.peak.alt:.0f}°" if best else "neviditelná"
            )
        eclipses = find_solar_eclipses(now, now + timedelta(days=400), loc)
        seen = next((e for e in eclipses if e.visible), None)
        if seen and seen.maximum:
            row["příští zatmění Slunce"] = (
                f"{date_short(seen.maximum, z)} {seen.maximum.astimezone(z).year} "
                f"{seen.local_type} {seen.magnitude * 100:.0f} %"
            )
        else:
            row["příští zatmění Slunce"] = "do roka žádné"
        cols.append(row)
    labels: list[str] = []
    for c in cols:
        for k in c:
            if k not in labels:
                labels.append(k)
    return [(label, [c.get(label, "—") for c in cols]) for label in labels]
