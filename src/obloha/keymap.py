"""Key bindings: definitions, user remapping from ``[keys]`` and collision checks.

Contexts form a tree: ``global`` → ``sky`` → ``sky-beginner`` / ``sky-advanced``
and ``global`` → ``events`` / ``places``. A key may be used in two contexts
only when neither context contains the other, or when the more specific
action explicitly *shadows* the general one (documented in DECISIONS.md).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

CONTEXT_PARENTS: dict[str, str | None] = {
    "global": None,
    "sky": "global",
    "sky-beginner": "sky",
    "sky-advanced": "sky",
    "events": "global",
    "places": "global",
}
CONTEXT_NAMES = {
    "global": "Globální",
    "sky": "Obloha",
    "sky-beginner": "Obloha – začátečník",
    "sky-advanced": "Obloha – pokročilý",
    "events": "Úkazy",
    "places": "Výběr místa",
}

#: human readable / config spelling -> Textual key name
_CHAR_KEYS = {
    "?": "question_mark",
    "/": "slash",
    " ": "space",
    "space": "space",
    ".": "full_stop",
    ",": "comma",
    ">": "greater_than_sign",
    "<": "less_than_sign",
    "+": "plus",
    "-": "minus",
    "[": "left_square_bracket",
    "]": "right_square_bracket",
    "=": "equals_sign",
    "enter": "enter",
    "tab": "tab",
    "escape": "escape",
    "esc": "escape",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "backspace": "backspace",
    "home": "home",
    "end": "end",
    "pageup": "pageup",
    "pagedown": "pagedown",
    "*": "asterisk",
    "#": "number_sign",
    "!": "exclamation_mark",
    ":": "colon",
    ";": "semicolon",
    "'": "apostrophe",
    '"': "quotation_mark",
    "_": "underscore",
    "~": "tilde",
    "`": "grave_accent",
    "|": "vertical_line",
    "\\": "backslash",
    "(": "left_parenthesis",
    ")": "right_parenthesis",
    "{": "left_curly_bracket",
    "}": "right_curly_bracket",
    "@": "at",
    "^": "circumflex_accent",
    "&": "ampersand",
    "%": "percent_sign",
    "$": "dollar_sign",
}
_DISPLAY = {v: k for k, v in _CHAR_KEYS.items() if len(k) == 1 and k != " "}
_DISPLAY.update(
    {
        "space": "Space",
        "enter": "Enter",
        "tab": "Tab",
        "escape": "Esc",
        "up": "↑",
        "down": "↓",
        "left": "←",
        "right": "→",
    }
)


class KeymapError(ValueError):
    """Invalid or colliding key configuration (message in Czech)."""


def normalize_key(key: str) -> str:
    """Turn ``"?"``, ``"Ctrl+P"``, ``"space"`` or ``"N"`` into a Textual key name."""
    k = key.strip()
    if not k:
        raise KeymapError("prázdná klávesa")
    if k in _CHAR_KEYS:
        return _CHAR_KEYS[k]
    low = k.lower()
    if low in _CHAR_KEYS:
        return _CHAR_KEYS[low]
    if "+" in k and len(k) > 1:
        mods, _, base = k.rpartition("+")
        mod_parts = [m.lower() for m in mods.split("+")]
        for m in mod_parts:
            if m not in ("ctrl", "alt", "shift"):
                raise KeymapError(f"neznámý modifikátor {m!r} v {key!r}")
        if "ctrl" in mod_parts and "shift" in mod_parts:
            raise KeymapError(f"{key!r}: kombinace Ctrl+Shift nejsou podporované (Termux)")
        return "+".join([*mod_parts, normalize_key(base) if len(base) > 1 else base.lower()])
    if len(k) == 1 and (k.isalnum() or k in _CHAR_KEYS):
        return k
    if low.startswith("f") and low[1:].isdigit():
        return low
    if low in ("delete", "insert"):
        return low
    raise KeymapError(f"neznámá klávesa {key!r}")


def display_key(key: str) -> str:
    """Short label for a Textual key name (for the footer and help)."""
    if key in _DISPLAY:
        return _DISPLAY[key]
    if key.startswith("ctrl+"):
        return "Ctrl+" + display_key(key[5:]).upper()
    return key


@dataclass(frozen=True)
class Action:
    id: str
    context: str
    keys: tuple[str, ...]
    description: str
    footer: str = ""  # short label for the footer, empty = not in footer
    shadows: frozenset[str] = field(default_factory=frozenset)


DEFAULT_ACTIONS: tuple[Action, ...] = (
    # global
    Action("screen_sky", "global", ("1",), "Obloha", "obloha"),
    Action("screen_tonight", "global", ("2",), "Dnes v noci", "dnes"),
    Action("screen_satellites", "global", ("3",), "Satelity", "satelity"),
    Action("screen_events", "global", ("4",), "Úkazy", "úkazy"),
    Action("screen_settings", "global", ("5",), "Nastavení", "nastavení"),
    Action("toggle_mode", "global", ("m",), "Začátečnický / pokročilý režim", "mapa"),
    Action("lessons", "global", ("u",), "Úkoly a průvodce", "úkoly"),
    Action("help", "global", ("?", "H"), "Nápověda (všechny zkratky)", "nápověda"),
    Action("command_palette", "global", ("ctrl+p",), "Příkazová paleta"),
    Action("search", "global", ("/",), "Hledat objekt", "hledat"),
    Action("night", "global", ("n",), "Noční vidění (červený režim)", "noční"),
    Action("quit", "global", ("q",), "Zpět / konec", "konec"),
    Action("place", "global", ("L",), "Výběr místa podle města", "místo"),
    Action("toggle_info", "global", ("i",), "Skrýt / ukázat informační panel"),
    # time (global)
    Action("time_pause", "global", ("space",), "Pauza / živě", "pauza"),
    Action("time_forward", "global", (".",), "Čas dopředu o krok", "čas"),
    Action("time_back", "global", (",",), "Čas dozadu o krok"),
    Action("time_faster", "global", (">",), "Zrychlit čas", "rychlost"),
    Action("time_slower", "global", ("<",), "Zpomalit čas (i do záporu)"),
    Action("time_set", "global", ("T",), "Zadat datum a čas"),
    Action("time_now", "global", ("0",), "Zpět na teď"),
    Action("time_step", "global", ("s",), "Změnit délku kroku (min, 10 min, h, den)"),
    # sky (both modes)
    Action("zoom_in", "sky", ("+", "="), "Přiblížit (zúžit zorné pole)", "zoom"),
    Action("zoom_out", "sky", ("-",), "Oddálit"),
    Action("face_north", "sky", ("N",), "Natočit na sever"),
    Action("face_south", "sky", ("S",), "Natočit na jih"),
    Action("face_east", "sky", ("E",), "Natočit na východ"),
    Action("face_west", "sky", ("W",), "Natočit na západ"),
    Action("mag_down", "sky", ("[",), "Snížit mezní magnitudu"),
    Action("mag_up", "sky", ("]",), "Zvýšit mezní magnitudu"),
    Action("select", "sky", ("enter",), "Podrobnosti o objektu", "podrobnosti"),
    # beginner sky
    Action("turn_left", "sky-beginner", ("left", "h"), "Otočit doleva", "otočit"),
    Action("turn_right", "sky-beginner", ("right", "l"), "Otočit doprava"),
    Action("look_up", "sky-beginner", ("up", "k"), "Podívat se výš", "výš/níž"),
    Action("look_down", "sky-beginner", ("down", "j"), "Podívat se níž"),
    Action(
        "identify",
        "sky-beginner",
        ("?",),
        "Co je to za světlo?",
        "co je to",
        shadows=frozenset({"help"}),
    ),
    Action("compass", "sky-beginner", ("c",), "Kompas telefonu (Termux)", "kompas"),
    Action("found", "sky-beginner", ("f",), "Úkol: našel jsem"),
    Action("hint", "sky-beginner", ("x",), "Úkol: další nápověda"),
    # advanced sky
    Action("cursor_left", "sky-advanced", ("left", "h"), "Kurzor doleva"),
    Action("cursor_right", "sky-advanced", ("right", "l"), "Kurzor doprava"),
    Action("cursor_up", "sky-advanced", ("up", "k"), "Kurzor nahoru"),
    Action("cursor_down", "sky-advanced", ("down", "j"), "Kurzor dolů"),
    Action("toggle_view", "sky-advanced", ("v",), "Celá obloha / pohled jedním směrem", "pohled"),
    Action("layer_constellations", "sky-advanced", ("c",), "Vrstva: čáry souhvězdí", "souhvězdí"),
    Action("layer_borders", "sky-advanced", ("b",), "Vrstva: hranice souhvězdí"),
    Action("layer_milky_way", "sky-advanced", ("M",), "Vrstva: Mléčná dráha"),
    Action("layer_grid", "sky-advanced", ("g",), "Vrstva: souřadnicová síť (alt-az / RA-Dec)"),
    Action("layer_ecliptic", "sky-advanced", ("e",), "Vrstva: ekliptika"),
    Action("layer_labels", "sky-advanced", ("p",), "Vrstva: popisky"),
    Action("layer_below", "sky-advanced", ("B",), "Zobrazit i pod obzorem (tlumeně)"),
    # events
    Action("event_jump", "events", ("j",), "Skočit na čas úkazu", "skočit"),
    Action("event_filter", "events", ("f",), "Filtr podle typu"),
    # places dialog
    Action("place_favorites", "places", ("tab",), "Přepnout oblíbená / poslední místa"),
    Action("place_compare", "places", ("ctrl+o",), "Přidat do porovnání měst"),
)


class Keymap:
    """Resolved key bindings."""

    def __init__(
        self,
        actions: Iterable[Action] = DEFAULT_ACTIONS,
        overrides: Mapping[str, str | list[str]] | None = None,
    ) -> None:
        by_id = {a.id: a for a in actions}
        resolved: dict[str, Action] = {}
        for a in by_id.values():
            resolved[a.id] = Action(
                a.id,
                a.context,
                tuple(normalize_key(k) for k in a.keys),
                a.description,
                a.footer,
                a.shadows,
            )
        for action_id, value in (overrides or {}).items():
            if action_id not in by_id:
                raise KeymapError(
                    f"[keys] neznámá akce {action_id!r}. Platné akce: " + ", ".join(sorted(by_id))
                )
            raw = [value] if isinstance(value, str) else list(value)
            keys = []
            for item in raw:
                for k in item.split(",") if item.strip() != "," else [item]:
                    keys.append(normalize_key(k))
            a = resolved[action_id]
            resolved[action_id] = Action(
                a.id, a.context, tuple(keys), a.description, a.footer, a.shadows
            )
        self.actions = resolved
        self._check()

    @staticmethod
    def ancestors(context: str) -> list[str]:
        out = []
        c: str | None = context
        while c is not None:
            out.append(c)
            c = CONTEXT_PARENTS[c]
        return out

    def _related(self, a: str, b: str) -> bool:
        return a in self.ancestors(b) or b in self.ancestors(a)

    def _check(self) -> None:
        items = list(self.actions.values())
        problems = []
        for i, a in enumerate(items):
            for b in items[i + 1 :]:
                common = set(a.keys) & set(b.keys)
                if not common or not self._related(a.context, b.context):
                    continue
                if b.id in a.shadows or a.id in b.shadows:
                    continue
                for k in sorted(common):
                    problems.append(
                        f"klávesa {display_key(k)!r} je přiřazená akcím {a.id!r} i {b.id!r}"
                    )
        if problems:
            raise KeymapError("Kolize klávesových zkratek: " + "; ".join(problems))

    def action_for(self, key: str, context: str) -> str | None:
        """Most specific action bound to ``key`` in ``context`` (or its ancestors)."""
        for ctx in self.ancestors(context):
            for a in self.actions.values():
                if a.context == ctx and key in a.keys:
                    return a.id
        return None

    def keys_for(self, action_id: str) -> tuple[str, ...]:
        return self.actions[action_id].keys

    def label(self, action_id: str) -> str:
        """Display label of the first key of an action, e.g. ``?``."""
        keys = self.actions[action_id].keys
        return display_key(keys[0]) if keys else ""

    def footer(self, context: str, ids: Iterable[str] | None = None) -> list[tuple[str, str]]:
        """(key label, short description) pairs for the footer of ``context``."""
        wanted = list(ids) if ids is not None else None
        out = []
        ctxs = self.ancestors(context)
        pool = [a for a in self.actions.values() if a.context in ctxs and a.footer]
        if wanted is not None:
            pool = [self.actions[i] for i in wanted if i in self.actions]
        for a in pool:
            if not a.keys:
                continue
            out.append((display_key(a.keys[0]), a.footer or a.description))
        return out

    def help_rows(self) -> list[tuple[str, str, str]]:
        """(context name, keys, description) for the help screen."""
        rows = []
        for ctx in CONTEXT_PARENTS:
            for a in self.actions.values():
                if a.context == ctx:
                    rows.append(
                        (
                            CONTEXT_NAMES[ctx],
                            " ".join(display_key(k) for k in a.keys),
                            a.description,
                        )
                    )
        return rows
