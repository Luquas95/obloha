import pytest

from obloha.config import (
    Config,
    ConfigError,
    Place,
    State,
    cache_dir,
    config_path,
    load_config,
    load_state,
    save_config,
    save_state,
)
from obloha.core.location import Location


def test_xdg_paths(tmp_path):
    assert config_path() == tmp_path / "config" / "obloha" / "config.toml"
    assert cache_dir() == tmp_path / "cache" / "obloha"


def test_defaults_are_prague_beginner():
    cfg, _ = load_config()
    assert cfg.location.name == "Praha"
    assert cfg.location.to_location().tz == "Europe/Prague"
    assert cfg.display.mode == "beginner"
    assert cfg.beginner_limit() == 3.5


def test_roundtrip_keeps_comments():
    cfg, doc = load_config()
    save_config(cfg, doc)
    text = config_path().read_text()
    assert text.startswith("# Konfigurace aplikace obloha")
    assert "[location]" in text and "[display]" not in text  # minimal file
    text += "\n[display]\n# moje poznámka\nfuture_option = 1\n"
    text += '\n# oblíbená\n[[favorites]]\n# hvězdárna\nname = "Ondřejov"\n'
    text += "lat = 49.91\nlon = 14.78\n"
    config_path().write_text(text)
    cfg, doc = load_config()
    assert cfg.favorites[0].name == "Ondřejov"
    cfg.display.mode = "advanced"
    cfg.favorites[0].elevation = 528
    save_config(cfg, doc)
    text = config_path().read_text()
    assert "# moje poznámka" in text and "future_option = 1" in text
    assert "# hvězdárna" in text and "elevation = 528" in text
    cfg.favorites.append(Place(name="Brno", lat=49.195, lon=16.608, elevation=237))
    save_config(cfg, doc)
    cfg2, _ = load_config()
    assert cfg2.display.mode == "advanced"
    assert [p.name for p in cfg2.favorites] == ["Ondřejov", "Brno"]
    cfg2.favorites = []
    save_config(cfg2, _)
    assert "[[favorites]]" not in config_path().read_text()


def test_unreadable_config():
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(ConfigError, match="nejde přečíst"):
        load_config()


def test_keys_accept_lists():
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text('[keys]\nsearch = ["/", "ctrl+f"]\n')
    cfg, _ = load_config()
    assert cfg.keys["search"] == ["/", "ctrl+f"]


def test_invalid_config_message():
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text("[location]\nlat = 120\n")
    with pytest.raises(ConfigError, match=r"location\.lat"):
        load_config()
    config_path().write_text("[location\n")
    with pytest.raises(ConfigError, match="Chyba v souboru"):
        load_config()


def test_invalid_timezone():
    with pytest.raises(ValueError):
        Place(tz="Mars/Olympus")


def test_place_location_roundtrip():
    loc = Location("Brno", 49.195, 16.608, 237, "Europe/Prague", "okr. Brno-město")
    assert Place.from_location(loc).to_location() == loc


def test_state_roundtrip():
    st = load_state()
    assert st.recent == []
    for i in range(10):
        st.add_recent(Place(name=f"P{i}", lat=i, lon=i))
    st.add_recent(Place(name="P3", lat=3, lon=3))
    assert st.recent[0].name == "P3" and len(st.recent) == 8
    st.lessons_done.append("summer_triangle")
    save_state(st)
    assert load_state().lessons_done == ["summer_triangle"]


def test_quality_limit():
    cfg = Config()
    cfg.display.sky_quality = "venkov"
    assert cfg.beginner_limit() == 6.0
    cfg.display.beginner_limiting_mag = 4.2
    assert cfg.beginner_limit() == 4.2
    assert isinstance(State().recent, list)
