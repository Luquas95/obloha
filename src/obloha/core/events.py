"""Astronomical events calendar."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from skyfield import almanac
from skyfield.framelib import ecliptic_frame
from skyfield.searchlib import find_discrete, find_maxima, find_minima

from obloha.core.almanac import stars_altitude_at
from obloha.core.bodies import BODY_BY_ID, PLANETS, BodyInfo, body_target
from obloha.core.eclipses import find_lunar_eclipses, find_solar_eclipses
from obloha.core.ephem import ephemeris, to_datetime, ts_from_datetime
from obloha.core.location import Location

EVENT_KINDS: dict[str, str] = {
    "phase": "fáze Měsíce",
    "perigee": "perigeum/apogeum",
    "conjunction": "konjunkce",
    "opposition": "opozice a konjunkce se Sluncem",
    "elongation": "největší elongace",
    "season": "rovnodennosti a slunovraty",
    "eclipse": "zatmění",
    "meteor": "meteorické roje",
    "dst": "změna času",
}

PHASE_LABELS = ("nov Měsíce", "první čtvrť", "úplněk", "poslední čtvrť")
PHASE_SYMBOLS = ("●", "◐", "○", "◑")
SEASON_LABELS = (
    "jarní rovnodennost",
    "letní slunovrat",
    "podzimní rovnodennost",
    "zimní slunovrat",
)


@dataclass(frozen=True)
class MeteorShower:
    name: str
    month: int
    day: int
    zhr: int
    ra: float
    dec: float
    parent: str


METEOR_SHOWERS: tuple[MeteorShower, ...] = (
    MeteorShower("Kvadrantidy", 1, 3, 110, 230.0, 49.0, "planetka 2003 EH1"),
    MeteorShower("Lyridy", 4, 22, 18, 271.0, 34.0, "kometa C/1861 G1 Thatcher"),
    MeteorShower("Éta Akvaridy", 5, 6, 50, 338.0, -1.0, "Halleyova kometa"),
    MeteorShower("Jižní delta Akvaridy", 7, 30, 25, 340.0, -16.0, "kometa 96P/Machholz"),
    MeteorShower("Perseidy", 8, 12, 100, 48.0, 58.0, "kometa 109P/Swift–Tuttle"),
    MeteorShower("Drakonidy", 10, 8, 10, 262.0, 54.0, "kometa 21P/Giacobini–Zinner"),
    MeteorShower("Orionidy", 10, 21, 20, 95.0, 16.0, "Halleyova kometa"),
    MeteorShower("Severní Tauridy", 11, 12, 5, 58.0, 22.0, "kometa 2P/Encke"),
    MeteorShower("Leonidy", 11, 17, 15, 152.0, 22.0, "kometa 55P/Tempel–Tuttle"),
    MeteorShower("Geminidy", 12, 14, 150, 112.0, 33.0, "planetka 3200 Phaethon"),
    MeteorShower("Ursidy", 12, 22, 10, 217.0, 76.0, "kometa 8P/Tuttle"),
)


@dataclass(frozen=True)
class Event:
    """One calendar entry."""

    when: datetime  # UTC
    kind: str
    title: str
    symbol: str
    detail: str
    bodies: tuple[str, ...] = ()
    altitude: float | None = None  # of the main body at ``when`` from the location
    extra: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


def _dt(t: Any) -> datetime:
    return to_datetime(t)


def _fmt_local(when: datetime, location: Location) -> str:
    return when.astimezone(location.zone).strftime("%-d. %-m. %H:%M")


def _alt(info: BodyInfo, t: Any, location: Location) -> float:
    alt, _, _ = location.observer.at(t).observe(body_target(info)).apparent().altaz("standard")
    return float(alt.degrees)


def _where_text(alt: float) -> str:
    if alt > 0:
        return f"V tu chvíli je {alt:.0f}° nad obzorem."
    return f"V tu chvíli je {abs(alt):.0f}° pod obzorem, dívej se nejbližší noc."


def moon_phase_events(t0: Any, t1: Any, location: Location) -> list[Event]:
    times, phases = find_discrete(t0, t1, almanac.moon_phases(ephemeris()))
    out = []
    texts = (
        "Měsíc není vidět. Nejtmavší noci, nejlepší čas na Mléčnou dráhu a slabé objekty.",
        "Měsíc je osvětlený z poloviny a večer na jihu. Dalekohledem jsou krásně vidět krátery"
        " na rozhraní světla a stínu.",
        "Měsíc svítí celou noc a přesvětluje oblohu, slabé hvězdy zmizí.",
        "Měsíc vychází kolem půlnoci, večery jsou opět tmavé.",
    )
    moon = BODY_BY_ID["moon"]
    for t, p in zip(times, phases, strict=False):
        p = int(p)
        out.append(
            Event(
                _dt(t),
                "phase",
                PHASE_LABELS[p],
                PHASE_SYMBOLS[p],
                texts[p],
                ("moon",),
                _alt(moon, t, location),
            )
        )
    return out


def _geo_distance(info: BodyInfo) -> Callable[[Any], Any]:
    eph = ephemeris()

    def f(t: Any) -> Any:
        return eph["earth"].at(t).observe(body_target(info)).distance().km

    f.step_days = 1.0  # type: ignore[attr-defined]
    return f


def perigee_apogee_events(t0: Any, t1: Any, location: Location) -> list[Event]:
    moon = BODY_BY_ID["moon"]
    f = _geo_distance(moon)
    out = []
    for finder, label, symbol, text in (
        (
            find_minima,
            "Měsíc v perigeu",
            "◉",
            "Měsíc je nejblíž Zemi, vypadá o trochu větší (při úplňku se mluví o „superúplňku“).",
        ),
        (find_maxima, "Měsíc v apogeu", "◌", "Měsíc je nejdál od Země, vypadá o trochu menší."),
    ):
        times, dist = finder(t0, t1, f)
        for t, d in zip(times, dist, strict=False):
            out.append(
                Event(
                    _dt(t),
                    "perigee",
                    f"{label} ({d:,.0f} km)".replace(",", " "),
                    symbol,
                    text,
                    ("moon",),
                    _alt(moon, t, location),
                    {"distance_km": float(d)},
                )
            )
    return out


def _separation_fn(a: BodyInfo, b: BodyInfo, step: float) -> Callable[[Any], Any]:
    eph = ephemeris()

    def f(t: Any) -> Any:
        e = eph["earth"].at(t)
        return e.observe(body_target(a)).separation_from(e.observe(body_target(b))).degrees

    f.step_days = step  # type: ignore[attr-defined]
    return f


def conjunction_events(
    t0: Any, t1: Any, location: Location, moon_limit: float = 5.0, planet_limit: float = 3.0
) -> list[Event]:
    """Close approaches Moon-planet and planet-planet (geocentric)."""
    moon = BODY_BY_ID["moon"]
    sun = BODY_BY_ID["sun"]
    bright = [p for p in PLANETS if p.id not in ("uranus", "neptune")]
    out = []
    pairs: list[tuple[BodyInfo, BodyInfo, float, float]] = [
        (moon, p, moon_limit, 0.25) for p in bright
    ]
    pairs += [(a, b, planet_limit, 1.0) for a, b in itertools.combinations(bright, 2)]
    eph = ephemeris()
    for a, b, limit, step in pairs:
        times, seps = find_minima(t0, t1, _separation_fn(a, b, step))
        for t, sep in zip(times, seps, strict=False):
            if sep > limit:
                continue
            e = eph["earth"].at(t)
            elong = e.observe(body_target(sun)).separation_from(e.observe(body_target(b))).degrees
            if elong < 12:  # lost in the Sun's glare
                continue
            alt = _alt(b, t, location)
            sep_txt = f"{sep:.1f}".replace(".", ",")
            out.append(
                Event(
                    _dt(t),
                    "conjunction",
                    f"{a.name} a {b.name} {sep_txt}° od sebe",
                    "☌",
                    f"{a.name} a {b.name} budou na obloze blízko sebe ({sep_txt}°, "
                    f"to je zhruba {_fingers(sep)}). Hezký pohled okem i fotoaparátem. "
                    + _where_text(alt),
                    (a.id, b.id),
                    alt,
                    {"separation": float(sep)},
                )
            )
    return out


def _fingers(sep: float) -> str:
    if sep < 1:
        return "méně než šířka malíčku na natažené ruce"
    if sep < 2:
        return "šířka palce na natažené ruce"
    return f"{sep / 2:.0f} prsty na natažené ruce".replace("1 prsty", "1 prst")


def opposition_events(t0: Any, t1: Any, location: Location) -> list[Event]:
    eph = ephemeris()
    out = []
    for p in PLANETS:
        times, codes = find_discrete(t0, t1, almanac.oppositions_conjunctions(eph, body_target(p)))
        for t, c in zip(times, codes, strict=False):
            c = int(c)
            dist = eph["earth"].at(t).observe(body_target(p)).distance().au
            if c == 1:
                title = f"{p.name} v opozici"
                text = (
                    f"{p.name} je naproti Slunci: celou noc nad obzorem, nejblíž Zemi a "
                    "nejjasnější v roce. Nejlepší čas na pozorování."
                )
            elif p.id in ("mercury", "venus"):
                inferior = dist < 1.0
                title = f"{p.name} v {'dolní' if inferior else 'horní'} konjunkci"
                text = f"{p.name} je ve směru Slunce a není vidět."
            else:
                title = f"{p.name} v konjunkci se Sluncem"
                text = f"{p.name} je za Sluncem a několik týdnů není vidět."
            out.append(
                Event(
                    _dt(t),
                    "opposition",
                    title,
                    p.symbol,
                    text,
                    (p.id,),
                    _alt(p, t, location),
                    {"code": c},
                )
            )
    return out


def elongation_events(t0: Any, t1: Any, location: Location) -> list[Event]:
    eph = ephemeris()
    sun = BODY_BY_ID["sun"]
    out = []
    for pid in ("mercury", "venus"):
        p = BODY_BY_ID[pid]
        f = _separation_fn(sun, p, 3.0)
        times, elong = find_maxima(t0, t1, f)
        for t, el in zip(times, elong, strict=False):
            e = eph["earth"].at(t)
            _, lon_p, _ = e.observe(body_target(p)).frame_latlon(ecliptic_frame)
            _, lon_s, _ = e.observe(body_target(sun)).frame_latlon(ecliptic_frame)
            east = ((lon_p.degrees - lon_s.degrees) % 360.0) < 180.0
            side = "večerní (východní)" if east else "ranní (západní)"
            when_txt = (
                "večer po západu Slunce nízko na západě"
                if east
                else ("ráno před východem Slunce nízko na východě")
            )
            el_txt = f"{el:.1f}".replace(".", ",")
            out.append(
                Event(
                    _dt(t),
                    "elongation",
                    f"{p.name} v největší {side} elongaci ({el_txt}°)",
                    p.symbol,
                    f"{p.name} je nejdál od Slunce, nejlépe ji uvidíš {when_txt}."
                    if p.feminine
                    else f"{p.name} je nejdál od Slunce, nejlépe ho uvidíš {when_txt}.",
                    (pid,),
                    _alt(p, t, location),
                    {"elongation": float(el), "east": east},
                )
            )
    return out


def season_events(t0: Any, t1: Any, location: Location) -> list[Event]:
    times, seasons = find_discrete(t0, t1, almanac.seasons(ephemeris()))
    texts = (
        "Den a noc jsou zhruba stejně dlouhé, začíná astronomické jaro.",
        "Nejdelší den a nejkratší noc v roce, začíná astronomické léto.",
        "Den a noc jsou zhruba stejně dlouhé, začíná astronomický podzim.",
        "Nejkratší den a nejdelší noc v roce, začíná astronomická zima.",
    )
    sym = ("♈", "☀", "♎", "❄")
    return [
        Event(_dt(t), "season", SEASON_LABELS[int(s)], sym[int(s)], texts[int(s)], ("sun",))
        for t, s in zip(times, seasons, strict=False)
    ]


def eclipse_events(start: datetime, end: datetime, location: Location) -> list[Event]:
    out = []
    for se in find_solar_eclipses(start, end, location):
        if se.visible and se.maximum and se.begin and se.end:
            mag = f"{se.magnitude:.2f}".replace(".", ",")
            obs = f"{se.obscuration * 100:.0f}"
            title = f"{se.local_type.capitalize() if se.local_type else ''} zatmění Slunce"
            detail = (
                f"Globálně {se.global_type} zatmění Slunce, z místa {se.local_type}. "
                f"Začátek {_fmt_local(se.begin, location)}, maximum "
                f"{_fmt_local(se.maximum, location)} (magnituda {mag}, zakryto {obs} % plochy), "
                f"konec {_fmt_local(se.end, location)}. Slunce ve výšce "
                f"{se.sun_alt_at_max:.0f}°. Nikdy se nedívej do Slunce bez certifikovaného "
                "filtru!"
            )
            out.append(
                Event(
                    se.maximum,
                    "eclipse",
                    title,
                    "◐",
                    detail,
                    ("sun", "moon"),
                    se.sun_alt_at_max,
                    {"eclipse": se},
                )
            )
        else:
            out.append(
                Event(
                    se.global_maximum,
                    "eclipse",
                    f"{se.global_type.capitalize()} zatmění Slunce (odsud neviditelné)",
                    "◌",
                    f"Globálně {se.global_type} zatmění Slunce, z tohoto místa není vidět.",
                    ("sun", "moon"),
                    None,
                    {"eclipse": se},
                )
            )
    for le in find_lunar_eclipses(start, end, location):
        vis = "viditelné" if le.visible else "odsud neviditelné"
        parts = [f"Začátek polostínové fáze {_fmt_local(le.penumbral_begin, location)}"]
        if le.partial_begin:
            parts.append(f"částečné fáze {_fmt_local(le.partial_begin, location)}")
        if le.total_begin and le.total_end:
            parts.append(
                f"úplné fáze {_fmt_local(le.total_begin, location)}–"
                f"{_fmt_local(le.total_end, location)}"
            )
        mag = f"{le.umbral_magnitude:.2f}".replace(".", ",")
        detail = (
            f"{le.type_name.capitalize()} zatmění Měsíce ({vis}). "
            + ", ".join(parts)
            + f". Maximum {_fmt_local(le.maximum, location)}, magnituda ve stínu {mag}, "
            f"konec {_fmt_local(le.penumbral_end, location)}. Měsíc při maximu "
            f"{le.moon_alt_at_max:.0f}° nad obzorem. Zatmění Měsíce je bezpečné pozorovat okem."
        )
        out.append(
            Event(
                le.maximum,
                "eclipse",
                f"{le.type_name.capitalize()} zatmění Měsíce ({vis})",
                "◑",
                detail,
                ("moon",),
                le.moon_alt_at_max,
                {"eclipse": le},
            )
        )
    return out


def meteor_events(start: datetime, end: datetime, location: Location) -> list[Event]:
    from obloha.core.almanac import moon_info

    out = []
    for year in range(start.year, end.year + 1):
        for s in METEOR_SHOWERS:
            local_peak = datetime(year, s.month, s.day, 2, 0, tzinfo=location.zone) + timedelta(
                days=1
            )
            when = local_peak.astimezone(UTC)
            if not start <= when < end:
                continue
            mi = moon_info(when)
            moon_alt = _alt(BODY_BY_ID["moon"], ts_from_datetime(when), location)
            if moon_alt < 0 or mi.illumination < 0.25:
                moon_txt = "Měsíc neruší."
                factor = 1.0
            elif mi.illumination < 0.6:
                moon_txt = f"Měsíc ({mi.illumination * 100:.0f} %) trochu ruší."
                factor = 0.6
            else:
                moon_txt = (
                    f"Měsíc ({mi.illumination * 100:.0f} %) silně ruší, uvidíš jen jasné meteory."
                )
                factor = 0.3
            rad_alt = stars_altitude_at(s.ra, s.dec, when, location)
            out.append(
                Event(
                    when,
                    "meteor",
                    f"{s.name} (max., ZHR ~{s.zhr})",
                    "☄",
                    f"Maximum meteorického roje {s.name}, mateřské těleso {s.parent}. "
                    f"Za ideálních podmínek až {s.zhr} meteorů za hodinu. {moon_txt} "
                    f"Radiant je ve {rad_alt:.0f}° nad obzorem; dívej se kamkoli, "
                    "nejlépe po půlnoci "
                    "z tmavého místa.",
                    (),
                    rad_alt,
                    {"zhr": s.zhr, "moon_factor": factor},
                )
            )
    return out


def dst_events(start: datetime, end: datetime, location: Location) -> list[Event]:
    """Daylight saving time changes in the location's time zone."""
    out = []
    hour = start.replace(minute=0, second=0, microsecond=0)
    prev = hour.astimezone(location.zone).utcoffset()
    while hour < end:
        nxt = hour + timedelta(hours=1)
        off = nxt.astimezone(location.zone).utcoffset()
        if off is not None and prev is not None and off != prev:
            old_local = (nxt + prev).replace(tzinfo=None)
            new_local = nxt.astimezone(location.zone)
            kind = "konec" if off < prev else "začátek"
            title = f"{kind} letního času ({old_local:%H}:00 → {new_local:%H}:00)"
            out.append(Event(nxt, "dst", title, "◷", "Hodiny se posouvají o hodinu.", ()))
        prev = off
        hour = nxt
    return out


def compute_events(
    start: datetime,
    end: datetime,
    location: Location,
    kinds: Iterable[str] | None = None,
    moon_limit: float = 5.0,
    planet_limit: float = 3.0,
) -> list[Event]:
    """All events of the selected kinds between ``start`` and ``end``, sorted."""
    selected = set(kinds) if kinds is not None else set(EVENT_KINDS)
    t0, t1 = ts_from_datetime(start), ts_from_datetime(end)
    out: list[Event] = []
    if "phase" in selected:
        out += moon_phase_events(t0, t1, location)
    if "perigee" in selected:
        out += perigee_apogee_events(t0, t1, location)
    if "conjunction" in selected:
        out += conjunction_events(t0, t1, location, moon_limit, planet_limit)
    if "opposition" in selected:
        out += opposition_events(t0, t1, location)
    if "elongation" in selected:
        out += elongation_events(t0, t1, location)
    if "season" in selected:
        out += season_events(t0, t1, location)
    if "eclipse" in selected:
        out += eclipse_events(start, end, location)
    if "meteor" in selected:
        out += meteor_events(start, end, location)
    if "dst" in selected:
        out += dst_events(start, end, location)
    out.sort(key=lambda e: e.when)
    return out
