"""Terminal capability detection: colours, SSH, tmux, Unicode width problems."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Mapping


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def color_mode(env: Mapping[str, str] | None = None) -> str:
    """``"truecolor"`` if the terminal advertises it, else ``"256"``."""
    e = _env(env)
    colorterm = e.get("COLORTERM", "").lower()
    if colorterm in ("truecolor", "24bit"):
        return "truecolor"
    term = e.get("TERM", "").lower()
    if any(t in term for t in ("kitty", "alacritty", "wezterm", "foot", "direct", "ghostty")):
        return "truecolor"
    if e.get("TERM_PROGRAM", "") in ("iTerm.app", "WezTerm", "vscode"):
        return "truecolor"
    return "256"


def is_ssh(env: Mapping[str, str] | None = None) -> bool:
    e = _env(env)
    return bool(e.get("SSH_CONNECTION") or e.get("SSH_TTY") or e.get("SSH_CLIENT"))


def in_tmux(env: Mapping[str, str] | None = None) -> bool:
    return bool(_env(env).get("TMUX"))


def tmux_version(run: bool = True) -> tuple[int, int] | None:
    if not run or shutil.which("tmux") is None:
        return None
    try:
        out = subprocess.run(["tmux", "-V"], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(\d+)\.(\d+)", out)
    return (int(m[1]), int(m[2])) if m else None


def char_problem(
    env: Mapping[str, str] | None = None, tmux: tuple[int, int] | None = None
) -> str | None:
    """Reason why braille/planet symbols may render badly, or None."""
    e = _env(env)
    term = e.get("TERM", "")
    if term == "linux":
        return "linuxová konzole nemá braille znaky"
    lang = " ".join(e.get(k, "") for k in ("LC_ALL", "LC_CTYPE", "LANG")).upper()
    if lang.strip() and "UTF-8" not in lang and "UTF8" not in lang:
        return "terminál neběží v UTF-8"
    if in_tmux(e) and tmux is not None and tmux < (3, 0):
        return f"starší tmux {tmux[0]}.{tmux[1]} může počítat šířku znaků jinak"
    return None
