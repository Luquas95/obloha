import pytest

from obloha.keymap import DEFAULT_ACTIONS, Keymap, KeymapError, display_key, normalize_key


def test_defaults_have_no_collisions():
    km = Keymap()
    assert km.action_for("question_mark", "sky-beginner") == "identify"
    assert km.action_for("question_mark", "sky-advanced") == "help"
    assert km.action_for("c", "sky-beginner") == "compass"
    assert km.action_for("c", "sky-advanced") == "layer_constellations"
    assert km.action_for("m", "sky-advanced") == "toggle_mode"
    assert km.action_for("M", "sky-advanced") == "layer_milky_way"
    assert km.action_for("j", "events") == "event_jump"
    assert km.action_for("j", "sky-advanced") == "cursor_down"
    assert km.action_for("1", "events") == "screen_sky"
    assert km.action_for("x", "global") is None


def test_no_ctrl_shift_or_function_keys():
    for a in DEFAULT_ACTIONS:
        for k in a.keys:
            assert "ctrl+shift" not in k.lower()
            assert not (k.lower().startswith("f") and k[1:].isdigit())


@pytest.mark.parametrize(
    ("raw", "norm"),
    [
        ("?", "question_mark"),
        ("space", "space"),
        (".", "full_stop"),
        ("Ctrl+P", "ctrl+p"),
        ("N", "N"),
        ("[", "left_square_bracket"),
        ("Enter", "enter"),
        ("f5", "f5"),
    ],
)
def test_normalize(raw, norm):
    assert normalize_key(raw) == norm


def test_normalize_errors():
    for bad in ("", "Hyper+x", "ctrl+shift+p", "nonsense"):
        with pytest.raises(KeymapError):
            normalize_key(bad)


def test_override_and_collision():
    km = Keymap(overrides={"night": "r"})
    assert km.action_for("r", "global") == "night"
    assert km.label("night") == "r"
    with pytest.raises(KeymapError, match="Kolize"):
        Keymap(overrides={"night": "q"})
    with pytest.raises(KeymapError, match="neznámá akce"):
        Keymap(overrides={"fly": "f"})
    km = Keymap(overrides={"time_back": ",", "search": ["/", "ctrl+f"]})
    assert km.keys_for("search") == ("slash", "ctrl+f")
    # same key in sibling contexts is fine
    Keymap(overrides={"found": "v"})


def test_footer_and_help():
    km = Keymap()
    footer = km.footer("sky-advanced", ["help", "search"])
    assert footer == [("?", "nápověda"), ("/", "hledat")]
    assert km.footer("events")
    rows = km.help_rows()
    assert any(r[2] == "Noční vidění (červený režim)" for r in rows)
    assert display_key("ctrl+p") == "Ctrl+P"
    assert display_key("left") == "←"
