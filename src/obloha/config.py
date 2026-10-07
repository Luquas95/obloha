"""Configuration (``$XDG_CONFIG_HOME/obloha/config.toml``) and persistent state.

The configuration is validated with pydantic and written with tomlkit so
that user comments survive saving. Small runtime state (recent places,
lesson progress) lives in ``$XDG_STATE_HOME/obloha/state.json``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

import tomlkit
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from tomlkit.items import AoT

from obloha.core.location import Location


def _xdg(var: str, default: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else Path.home() / default


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / "obloha"


def cache_dir() -> Path:
    return _xdg("XDG_CACHE_HOME", ".cache") / "obloha"


def state_dir() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state") / "obloha"


def config_path() -> Path:
    return config_dir() / "config.toml"


class Place(BaseModel):
    """A stored location."""

    model_config = ConfigDict(extra="ignore")

    name: str = "Praha"
    lat: float = Field(50.0755, ge=-90, le=90)
    lon: float = Field(14.4378, ge=-180, le=180)
    elevation: float = 235.0
    tz: str = "Europe/Prague"
    label: str = ""

    @field_validator("tz")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"neznámé časové pásmo {v!r}") from exc
        return v

    def to_location(self) -> Location:
        return Location(self.name, self.lat, self.lon, self.elevation, self.tz, self.label)

    @classmethod
    def from_location(cls, loc: Location) -> Place:
        return cls(
            name=loc.name,
            lat=loc.lat,
            lon=loc.lon,
            elevation=loc.elevation,
            tz=loc.tz,
            label=loc.label,
        )


class Display(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: Literal["beginner", "advanced"] = "beginner"
    theme: Literal["dark", "light"] = "dark"
    night: bool = False
    sky_quality: Literal["město", "předměstí", "venkov"] = "město"
    beginner_limiting_mag: float | None = None
    limiting_mag: float = Field(5.5, ge=-1, le=8)
    ascii: bool = False
    colors: Literal["auto", "truecolor", "256"] = "auto"
    fps: float = Field(1.0, gt=0, le=10)
    ssh_fps: float = Field(0.5, gt=0, le=10)
    units: Literal["deg", "hm"] = "deg"
    time_zone: Literal["place", "observer"] = "place"
    info_panel: bool = True
    window_fov: float = Field(150.0, ge=90, le=200)
    view_fov: float = Field(90.0, ge=30, le=180)


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    constellation_lines: bool = True
    constellation_borders: bool = False
    labels: bool = True
    milky_way: bool = True
    grid: Literal["none", "altaz", "eq"] = "none"
    ecliptic: bool = False
    planets: bool = True
    moon: bool = True
    sun: bool = True
    satellites: bool = True
    below_horizon: bool = False


class SatelliteConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    groups: list[str] = Field(default_factory=lambda: ["stations"])
    catnr: list[int] = Field(default_factory=lambda: [20580])
    starlink: bool = False
    refresh_hours: float = Field(24.0, gt=0)
    min_altitude: float = Field(10.0, ge=0, le=60)


class NetworkConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    offline: bool = False
    weather: bool = True
    timeout: float = Field(10.0, gt=0)


class EventsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    months: int = Field(3, ge=1, le=24)
    moon_conjunction_deg: float = Field(5.0, gt=0, le=15)
    planet_conjunction_deg: float = Field(3.0, gt=0, le=15)


class Config(BaseModel):
    """Whole configuration file."""

    model_config = ConfigDict(extra="ignore")

    location: Place = Field(default_factory=Place)
    favorites: list[Place] = Field(default_factory=list)
    display: Display = Field(default_factory=Display)
    layers: LayerConfig = Field(default_factory=LayerConfig)
    satellites: SatelliteConfig = Field(default_factory=SatelliteConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    events: EventsConfig = Field(default_factory=EventsConfig)
    keys: dict[str, str | list[str]] = Field(default_factory=dict)

    def beginner_limit(self) -> float:
        from obloha.core.sky import sky_quality_limit

        if self.display.beginner_limiting_mag is not None:
            return self.display.beginner_limiting_mag
        return sky_quality_limit(self.display.sky_quality)


class ConfigError(Exception):
    """Invalid configuration file (message is user-facing Czech text)."""


HEADER = """\
# Konfigurace aplikace obloha (terminálové planetárium).
# Soubor se při ukládání z aplikace přepisuje, komentáře zůstávají zachovány.
# Klávesové zkratky jde přemapovat v sekci [keys], např.:
#   [keys]
#   night = "r"
"""


def load_config(path: Path | None = None) -> tuple[Config, tomlkit.TOMLDocument]:
    """Load (or create defaults for) the configuration file."""
    path = path or config_path()
    if not path.exists():
        cfg = Config()
        doc = tomlkit.document()
        for line in HEADER.splitlines():
            doc.add(tomlkit.comment(line.lstrip("# ")))
        _merge(doc, {"location": cfg.location.model_dump(mode="json")})
        return cfg, doc
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"Soubor {path} nejde přečíst: {exc}") from exc
    try:
        doc = tomlkit.parse(text)
    except Exception as exc:  # tomlkit raises various parse errors
        raise ConfigError(f"Chyba v souboru {path}: {exc}") from exc
    try:
        cfg = Config.model_validate(doc.unwrap())
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise ConfigError(f"Neplatná konfigurace v {path}: {problems}") from exc
    return cfg, doc


def _plain(item: Any) -> Any:
    return item.unwrap() if hasattr(item, "unwrap") else item


def _fill_table(tbl: Any, item: dict[str, Any]) -> None:
    for k, v in item.items():
        if v is None:
            if k in tbl:
                del tbl[k]
        elif k not in tbl or _plain(tbl[k]) != v:
            tbl[k] = v


def _merge(target: Any, data: dict[str, Any], defaults: dict[str, Any] | None = None) -> None:
    """Update a tomlkit container with plain data.

    Keeps comments and unknown keys, updates values already present, and adds only
    values that differ from ``defaults`` (so a minimal file stays minimal).
    """
    defaults = defaults or {}
    for key, value in data.items():
        default = defaults.get(key)
        present = key in target
        if isinstance(value, dict):
            if not present:
                if value == default:
                    continue
                target[key] = tomlkit.table()
            elif not isinstance(target[key], dict):
                target[key] = tomlkit.table()
            _merge(target[key], value, default if isinstance(default, dict) else {})
        elif isinstance(value, list) and (
            (value and isinstance(value[0], dict)) or (present and isinstance(target[key], AoT))
        ):
            if not value:
                if present:
                    del target[key]
                continue
            existing = target[key] if present and isinstance(target[key], AoT) else None
            if existing is not None and len(existing) == len(value):
                for tbl, item in zip(existing, value, strict=True):
                    _fill_table(tbl, item)  # in place: comments inside entries survive
                continue
            aot = tomlkit.aot()
            for item in value:
                tbl = tomlkit.table()
                _fill_table(tbl, item)
                aot.append(tbl)
            target[key] = aot
        elif value is None:
            if present:
                del target[key]
        elif present:
            if _plain(target[key]) != value:
                target[key] = value
        elif value != default:
            target[key] = value


def save_config(cfg: Config, doc: tomlkit.TOMLDocument, path: Path | None = None) -> None:
    """Write ``cfg`` into ``doc`` (preserving comments) and save it."""
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _merge(doc, cfg.model_dump(mode="json"), Config().model_dump(mode="json"))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(tomlkit.dumps(doc), encoding="utf-8")
    tmp.replace(path)


class State(BaseModel):
    """Small runtime state kept between sessions."""

    model_config = ConfigDict(extra="ignore")

    recent: list[Place] = Field(default_factory=list)
    lessons_done: list[str] = Field(default_factory=list)
    lesson_step: dict[str, int] = Field(default_factory=dict)
    compare: list[Place] = Field(default_factory=list)
    ascii_offered: bool = False

    def add_recent(self, place: Place, limit: int = 8) -> None:
        self.recent = [p for p in self.recent if (p.lat, p.lon) != (place.lat, place.lon)]
        self.recent.insert(0, place)
        del self.recent[limit:]


def state_path() -> Path:
    return state_dir() / "state.json"


def load_state(path: Path | None = None) -> State:
    path = path or state_path()
    try:
        return State.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError):
        return State()


def save_state(state: State, path: Path | None = None) -> None:
    path = path or state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    except OSError:  # pragma: no cover - read-only home
        pass
