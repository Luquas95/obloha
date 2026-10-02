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
    text = text.replace("[display]", "[display]\n# moje poznámka")
    config_path().write_text(text)
    cfg, doc = load_config()
    cfg.display.mode = "advanced"
    cfg.favorites.append(Place(name="Brno", lat=49.195, lon=16.608, elevation=237))
    save_config(cfg, doc)
    text = config_path().read_text()
    assert "# moje poznámka" in text
    cfg2, _ = load_config()
    assert cfg2.display.mode == "advanced"
    assert cfg2.favorites[0].name == "Brno"


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
