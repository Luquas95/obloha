# obloha – pokyny pro vývoj

Terminálové planetárium (Python 3.12, Textual, Skyfield). UI česky, kód anglicky.

## Spuštění a testy

```sh
uv sync                       # závislosti (vč. dev)
uv run obloha                 # aplikace; --time, --place, --offline, --ascii, --advanced
uv run pytest                 # všechny testy (síť se nikdy nevolá)
uv run pytest -m "not ui"     # jen jádro (rychlé)
uv run pytest tests/test_snapshots.py --snapshot-update   # po vědomé změně vzhledu
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest --cov && uv run coverage report --omit='src/obloha/ui/*,src/obloha/cli.py,src/obloha/web.py'
uv run python scripts/screenshots.py            # PNG do docs/screenshots
uv run python scripts/preview.py full 82 34     # rychlý náhled rendereru v terminálu
```

Data se generují skripty `scripts/build_catalog.py` a `scripts/build_cities.py` (stahují
přes `npm pack` / `pip download` do `scripts/_work`). Výsledky jsou v `src/obloha/data`.

## Architektura

- `obloha/core` – výpočty bez UI: `ephem` (DE421, timescale), `coords`, `projection`,
  `bodies`, `almanac`, `events`, `eclipses`, `satellites`, `weather`, `cities`,
  `sky` (SkyScene = polohy všeho pro čas a místo), `objects`.
- `obloha/render` – numpy plátno (`canvas`: braille/půlbloky → `Frame`), `sky`
  (vrstvy, popisky, pohled z okna), `night` (disk Měsíce, časová osa), `theme`, `color`.
- `obloha/beginner` – popisy slovy, „co teď uvidíš“, „co je to“, lekce, slovníček, kompas.
- `obloha/keymap.py` – definice vazeb a kontrola kolizí, `config.py` – pydantic + tomlkit.
- `obloha/ui` – `model.AppModel` (stav a akce bez Textualu), `app.ObloApp`, panely,
  dialogy, widgety. Akce klávesy `x` volá `ObloApp.do_<akce>`.

## Jak přidat nový typ úkazu

1. V `core/events.py` napiš funkci `xxx_events(t0, t1, location) -> list[Event]`
   (nebo s datetime `start, end`), vracej `Event(when, kind, title, symbol, detail, …)`.
2. Přidej `kind` do `EVENT_KINDS` (český popis pro filtr) a zavolej funkci
   v `compute_events`.
3. Test do `tests/test_events.py` s referenční hodnotou (zdroj do komentáře,
   neověřené do `docs/VERIFY.md`). Pojmy v `detail` se automaticky podtrhnou,
   pokud jsou ve slovníčku (`beginner/glossary.py`).

## Jak přidat vrstvu mapy

1. Přidej pole do `render/sky.Layers` a kreslicí metodu do `SkyRenderer`
   (zavolej ji v `render()` ve správném pořadí; priority bodů: vyšší vyhrává barvu).
2. Přidej pole do `config.LayerConfig`, popisek do `ui/panes/settings.LAYER_LABELS`
   a mapování v `AppModel.__init__`.
3. Přidej akci do `keymap.DEFAULT_ACTIONS` (kontext `sky-advanced`) a metodu
   `do_layer_xxx` do `ObloApp`. Test kolizí kláves proběhne automaticky.

## Zásady

- Testy nesmí volat síť (httpx přes `respx`, TLE fixtura v `tests/fixtures`).
- Čas je vždy aware UTC uvnitř, převod do pásma místa jen při zobrazení.
- Jádro nesmí importovat Textual. Pokrytí: celkem ≥ 85 %, bez UI ≥ 90 %.
