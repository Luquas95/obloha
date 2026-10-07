"""Header, key hint bar, touch buttons and simple boxed panels."""

from __future__ import annotations

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual import events
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Static

BOX_ASCII = str.maketrans("╭╮╰╯─│·▾●◼…", "++++-|-vo#~")


def fit(text: str, width: int) -> str:
    """Cut ``text`` to ``width`` cells (with an ellipsis)."""
    if cell_len(text) <= width:
        return text
    out = ""
    for ch in text:
        if cell_len(out + ch) > width - 1:
            break
        out += ch
    return out + "…"


class HeaderBar(Widget):
    """Three-line header: title with place and time, then status lines."""

    DEFAULT_CSS = """
    HeaderBar { height: 4; width: 1fr; }
    HeaderBar.-compact { height: 3; }
    """

    class PlaceClicked(Message):
        pass

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.place = "Praha"
        self.time_text = ""
        self.lines: list[str] = []
        self.compact = False
        self.ascii = False
        self.palette: dict[str, str] = {}

    def set_content(self, place: str, time_text: str, lines: list[str], compact: bool) -> None:
        changed = (place, time_text, lines, compact) != (
            self.place,
            self.time_text,
            self.lines,
            self.compact,
        )
        self.place, self.time_text, self.lines, self.compact = place, time_text, lines, compact
        self.set_class(compact, "-compact")
        height = len(lines[:2]) + (1 if compact else 2)
        if self.styles.height is None or self.styles.height.value != height:
            self.styles.height = height
        if changed:
            self.refresh()

    def render(self) -> Text:
        w = max(10, self.size.width)
        c = self.palette
        border = Style(color=c.get("border", "#2a3452"))
        accent = Style(color=c.get("accent", "#8fb8ff"), bold=True)
        text_st = Style(color=c.get("text", "#d6dcea"))
        muted = Style(color=c.get("muted", "#7a86a3"))
        out = Text(no_wrap=True, overflow="crop")
        if self.compact:
            title = f" obloha · {self.place} ▾"
            right = f"{self.time_text} "
            gap = max(1, w - cell_len(title) - cell_len(right))
            if cell_len(title) + cell_len(right) >= w:
                right = fit(right, max(0, w - cell_len(title) - 1))
                gap = max(1, w - cell_len(title) - cell_len(right))
            out.append(title, accent)
            out.append(" " * gap)
            out.append(right, text_st)
            for line in self.lines[:2]:
                out.append("\n " + fit(line, w - 1), text_st)
            return self._finish(out)
        title = f"─ obloha · {self.place} ▾ "
        right = f" {self.time_text} ╮"
        fill = w - 1 - cell_len(title) - cell_len(right)
        if fill < 1:
            right = fit(right, max(2, w - 2 - cell_len(title)))
            fill = max(0, w - 1 - cell_len(title) - cell_len(right))
        out.append("╭", border)
        out.append("─ ", border)
        out.append(f"obloha · {self.place} ▾", accent)
        out.append(" " + "─" * fill, border)
        out.append(right[:-1], text_st)
        out.append("╮", border)
        for i, line in enumerate(self.lines[:2]):
            body = fit(line, w - 4)
            out.append("\n│ ", border)
            out.append(body, text_st if i == 0 else muted)
            out.append(" " * max(0, w - 4 - cell_len(body)) + " │", border)
        out.append("\n╰" + "─" * (w - 2) + "╯", border)
        return self._finish(out)

    def _finish(self, out: Text) -> Text:
        if self.ascii:
            out.plain = out.plain.translate(BOX_ASCII)
        return out

    def on_click(self, event: events.Click) -> None:
        if event.y == 0 and event.x < cell_len(f"─ obloha · {self.place} ▾ ") + 2:
            self.post_message(self.PlaceClicked())


class KeyBar(Static):
    """One line of key hints (generated from the keymap)."""

    DEFAULT_CSS = """
    KeyBar { height: 1; width: 1fr; color: $text-muted; }
    """

    def show(self, items: list[tuple[str, str]], key_color: str = "#8fb8ff") -> None:
        width = max(10, self.size.width or 80)
        text = Text(no_wrap=True, overflow="crop")
        used = 0
        for key, label in items:
            chunk = f"  {key}  {label}"
            if used + cell_len(chunk) > width:
                break
            text.append("  ")
            text.append(key, Style(color=key_color, bold=True))
            text.append(f"  {label}")
            used += cell_len(chunk)
        self.update(text)


class TouchBar(Horizontal):
    """Big buttons for touch screens (mobile layout)."""

    DEFAULT_CSS = """
    TouchBar { height: 3; width: 1fr; align: center middle; }
    TouchBar Button { min-width: 4; width: 1fr; height: 3; margin: 0 0 0 1; }
    """

    class Pressed(Message):
        def __init__(self, action: str) -> None:
            super().__init__()
            self.action = action

    def __init__(self, buttons: list[tuple[str, str]], *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._buttons = buttons

    def compose(self):  # type: ignore[no-untyped-def]
        for label, action in self._buttons:
            yield Button(label, id=f"touch-{action}", classes="touch")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        bid = event.button.id or ""
        self.post_message(self.Pressed(bid.removeprefix("touch-")))
