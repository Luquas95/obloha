"""Glossary of terms, explained in one or two Czech sentences."""

from __future__ import annotations

import re
from dataclasses import dataclass

GLOSSARY: dict[str, str] = {
    "magnituda": "Číslo pro jasnost: čím menší, tím jasnější. Nejslabší hvězdy viditelné "
    "ve městě mají asi 3,5, na venkově 6; Venuše má až −4,7.",
    "azimut": "Směr na obzoru ve stupních: 0° je sever, 90° východ, 180° jih a 270° západ.",
    "výška": "Úhel nad obzorem: 0° je obzor, 90° přímo nad hlavou. Pěst na natažené ruce "
    "je asi 10°.",
    "zenit": "Bod přímo nad tvou hlavou (výška 90°).",
    "obzor": "Pomyslná čára, kde se obloha potkává se zemí.",
    "opozice": "Planeta je naproti Slunci: vychází při západu Slunce, je vidět celou noc a "
    "je nejjasnější.",
    "konjunkce": "Dvě tělesa jsou na obloze zdánlivě blízko sebe, ve skutečnosti mohou být "
    "daleko od sebe.",
    "elongace": "Úhlová vzdálenost planety od Slunce. Merkur a Venuše jsou nejlépe vidět při "
    "největší elongaci.",
    "kulminace": "Okamžik, kdy je objekt nejvýš nad obzorem (prochází jižním směrem).",
    "rektascenze": "Souřadnice na obloze podobná zeměpisné délce, měří se v hodinách (0–24 h).",
    "deklinace": "Souřadnice na obloze podobná zeměpisné šířce, od −90° do +90°.",
    "ekliptika": "Dráha, po které se Slunce během roku posouvá mezi hvězdami. Planety a Měsíc "
    "jsou vždy blízko ní.",
    "perigeum": "Bod dráhy, kde je Měsíc nejblíž Zemi.",
    "apogeum": "Bod dráhy, kde je Měsíc nejdál od Země.",
    "soumrak": "Doba po západu Slunce, kdy je ještě šero. Občanský končí při −6°, nautický "
    "při −12° a astronomický při −18° Slunce pod obzorem.",
    "souhvězdí": "Oblast oblohy s hvězdným obrazcem. Celou oblohu pokrývá 88 souhvězdí.",
    "asterismus": "Výrazný obrazec z hvězd, který není celé souhvězdí, např. Velký vůz.",
    "radiant": "Místo na obloze, odkud zdánlivě vylétají meteory jednoho roje.",
    "ZHR": "Kolik meteorů za hodinu by bylo vidět za ideálních podmínek. Skutečně jich je "
    "obvykle méně.",
    "au": "Astronomická jednotka, průměrná vzdálenost Země od Slunce (150 milionů km).",
    "zatmění": "Jedno těleso zakryje druhé nebo vrhne stín: Měsíc zakryje Slunce, nebo "
    "Země zastíní Měsíc.",
}

_ALIASES = {
    "magnituda": ("magnitud", "mag."),
    "výška": ("výšk",),
    "opozice": ("opozic",),
    "konjunkce": ("konjunkc",),
    "elongace": ("elongac",),
    "kulminace": ("kulmin",),
    "soumrak": ("soumrak",),
    "souhvězdí": ("souhvězdí",),
    "azimut": ("azimut",),
    "zenit": ("zenit",),
    "ekliptika": ("eklipti",),
    "perigeum": ("perige",),
    "apogeum": ("apoge",),
    "radiant": ("radiant",),
    "zatmění": ("zatmění",),
    "rektascenze": ("rektascenz", "RA"),
    "deklinace": ("deklinac", "Dec"),
}


@dataclass(frozen=True)
class TextPart:
    text: str
    term: str | None = None  # glossary key when this part is a term


def explain(term: str) -> str:
    return GLOSSARY.get(term, "")


def mark_terms(text: str) -> list[TextPart]:
    """Split ``text`` into plain parts and glossary terms (first occurrence of each)."""
    patterns: list[tuple[str, str]] = []
    for term in GLOSSARY:
        for stem in _ALIASES.get(term, (term,)):
            patterns.append((stem, term))
    patterns.sort(key=lambda p: -len(p[0]))
    regex = re.compile("|".join(rf"\b{re.escape(stem)}\w*" for stem, _ in patterns), re.IGNORECASE)
    parts: list[TextPart] = []
    seen: set[str] = set()
    pos = 0
    for m in regex.finditer(text):
        word = m.group(0)
        term = next(t for stem, t in patterns if word.lower().startswith(stem.lower()))
        if term in seen:
            continue
        seen.add(term)
        if m.start() > pos:
            parts.append(TextPart(text[pos : m.start()]))
        parts.append(TextPart(word, term))
        pos = m.end()
    if pos < len(text):
        parts.append(TextPart(text[pos:]))
    return parts
