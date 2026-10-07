"""``obloha --web``: serve the TUI in a browser via textual-serve."""

from __future__ import annotations

import shlex
import sys
from collections.abc import Sequence


def serve(host: str, port: int, argv: Sequence[str]) -> int:
    """Start textual-serve. Listens on 127.0.0.1 unless ``--host`` says otherwise."""
    try:
        from textual_serve.server import Server
    except ImportError:
        print(
            "obloha --web potřebuje balíček textual-serve: pip install 'obloha[web]'",
            file=sys.stderr,
        )
        return 2
    skip = {"--host", "--port"}
    args: list[str] = []
    it = iter(argv)
    for a in it:
        if a in skip:
            next(it, None)
            continue
        if a.startswith(("--host=", "--port=")):
            continue
        args.append(a)
    command = " ".join(shlex.quote(x) for x in [sys.executable, "-m", "obloha", *args])
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(
            f"POZOR: obloha je dostupná na {host}:{port} BEZ PŘIHLÁŠENÍ. "
            "Kdokoli v síti ji může ovládat.",
            file=sys.stderr,
        )
    server = Server(command, host=host, port=port, title="obloha")
    server.serve()
    return 0
