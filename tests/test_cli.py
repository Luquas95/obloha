from datetime import UTC, datetime

import pytest

from obloha import terminal
from obloha.cli import build_parser, main, parse_time_arg, resolve_location
from obloha.core.location import PRAGUE


def test_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert "obloha" in capsys.readouterr().out


def test_location_from_args():
    args = build_parser().parse_args(["--lat", "49.195", "--lon", "16.608"])
    loc = resolve_location(args, env={})
    assert loc.lat == pytest.approx(49.195) and loc.tz == "Europe/Prague"
    assert "Brno" in loc.label or loc.label.startswith("u obce")


def test_location_dms_and_env():
    args = build_parser().parse_args(["--lat", "50°4'N", "--lon", "14°26'E"])
    assert resolve_location(args, env={}).lat == pytest.approx(50.0667, abs=1e-3)
    args = build_parser().parse_args([])
    loc = resolve_location(args, env={"OBLOHA_PLACE": "Reykjavik"})
    assert loc.tz == "Atlantic/Reykjavik"
    loc = resolve_location(args, env={"OBLOHA_LAT": "-33.87", "OBLOHA_LON": "151.21"})
    assert loc.tz == "Australia/Sydney"
    assert resolve_location(args, env={}) is None


def test_location_errors():
    p = build_parser()
    with pytest.raises(SystemExit):
        resolve_location(p.parse_args(["--lat", "50"]), env={})
    with pytest.raises(SystemExit):
        resolve_location(p.parse_args(["--place", "Xyzzyqwq"]), env={})
    with pytest.raises(SystemExit):
        resolve_location(p.parse_args(["--lat", "abc", "--lon", "def"]), env={})


def test_time_arg():
    when = parse_time_arg("2026-10-01 21:00", PRAGUE.zone)
    assert when == datetime(2026, 10, 1, 19, 0, tzinfo=UTC)


def test_web_without_textual_serve(monkeypatch, capsys):
    import builtins

    real_import = builtins.__import__

    def fake(name, *a, **k):
        if name.startswith("textual_serve"):
            raise ImportError(name)
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    assert main(["--web"]) == 2
    assert "textual-serve" in capsys.readouterr().err


def test_web_server_args(monkeypatch, capsys):
    calls = {}

    class FakeServer:
        def __init__(self, command, host, port, title):
            calls.update(command=command, host=host, port=port)

        def serve(self):
            calls["served"] = True

    import textual_serve.server

    monkeypatch.setattr(textual_serve.server, "Server", FakeServer)
    assert main(["--web", "--host", "0.0.0.0", "--port", "9000", "--ascii"]) == 0
    assert calls["host"] == "0.0.0.0" and calls["port"] == 9000 and calls["served"]
    assert "--ascii" in calls["command"] and "--web" not in calls["command"]
    assert "BEZ PŘIHLÁŠENÍ" in capsys.readouterr().err
    assert build_parser().parse_args(["--web"]).host == "127.0.0.1"


def test_terminal_detection():
    assert terminal.color_mode({"COLORTERM": "truecolor"}) == "truecolor"
    assert terminal.color_mode({"TERM": "xterm-kitty"}) == "truecolor"
    assert terminal.color_mode({"TERM": "tmux-256color"}) == "256"
    assert terminal.is_ssh({"SSH_CONNECTION": "1 2 3 4"})
    assert not terminal.is_ssh({})
    assert terminal.in_tmux({"TMUX": "/tmp/x"})
    assert terminal.char_problem({"TERM": "linux"})
    assert terminal.char_problem({"LANG": "cs_CZ.ISO-8859-2"})
    assert terminal.char_problem({"LANG": "cs_CZ.UTF-8", "TMUX": "x"}, tmux=(2, 6))
    assert terminal.char_problem({"LANG": "cs_CZ.UTF-8"}) is None
    assert terminal.tmux_version(run=False) is None
