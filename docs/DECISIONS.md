# Rozhodnutí

Záznam rozhodnutí přijatých během vývoje (nejnovější dole v každé sekci).

## Proces a repozitář

- **Větev.** Zadání žádá `feat/initial-implementation`, prostředí (cloudový sandbox) ale
  povoluje push jen do přidělené větve `claude/new-session-6xeb9q`. Vývoj proto probíhá tam,
  PR míří do `main`. Commity dodržují Conventional Commits a pořadí bloků ze zadání.
- **Python 3.12, uv**, build backend hatchling. `uv.lock` je v repozitáři kvůli CI.

## Data

- **Efemeridy:** PyPI balíček `skyfield-data` (7.0.0, MIT) obsahuje `de421.bsp` (17 MB).
  Balíček `de421` z PyPI je jen sdist 27 MB, proto zvolen `skyfield-data`. DE421 je dílo
  JPL/NASA, volně šiřitelné. Soubor `finals2000A.all` z balíčku nepoužíváme (časová škála
  Skyfieldu s vestavěnými tabulkami ΔT a přestupných sekund, `builtin=True`), takže
  nehrozí varování o expiraci ani stahování. Rozsah času 1900–2049, mimo něj aplikace
  odmítne posun hláškou.
- **Hvězdy:** `d3-celestial` 0.7.35 (BSD-3). Čáry souhvězdí jsou v d3 uložené jako
  souřadnice; při buildu se každý vrchol přiřadí nejbližší hvězdě (tolerance 0,12°),
  takže v katalogu jsou čáry jako dvojice indexů hvězd. Jeden vrchol nemá hvězdu do 6 mag,
  doplní se z `stars.8.json`. Výsledek: 5045 hvězd, 89 záznamů souhvězdí (Had je rozdělen
  na dvě části, 88 jmen).
- **Mléčná dráha:** polygony z `mw.json` se při buildu rastrují (sudo-lichý test
  svislými paprsky, funguje i pro pás kolem celé oblohy) do mřížky 1° s ředěním u pólů;
  při vykreslování se body promítnou a obarví pozadí buněk. Rychlé a bez polygonové
  geometrie za běhu.
- **Formát dat:** `catalog.npz` (80 kB) + `catalog.json` (136 kB), ručně psaný
  `names_cs.json` (české názvy 88 souhvězdí, ~90 hvězd, pomocné obrazce, 5 objektů
  hlubokého vesmíru).
- **Města:** obce ČR z npm balíčku `text-to-map` (`souradnice.csv`, 6259 obcí s okresem
  a krajem; data ČSÚ/RÚIAN), SR a svět z GeoNames přes PyPI `geonamescache` (CC BY 4.0):
  SR z `cities500` (750 sídel), svět z `cities15000`. Názvy krajů z npm `cities.json`.
  Celkem 40 829 míst, SQLite 8,6 MB. Exonyma (Vídeň, Mnichov…) jsou ručně doplněná a
  u velkých měst jsou i latinkou psané alternativní názvy GeoNames (Wien, Prague…).
  Nadmořské výšky v žádném dostupném zdroji nejsou (viz VERIFY.md).
- **Časová pásma:** u měst z GeoNames, obce ČR Europe/Prague. Pro ručně zadané souřadnice
  `timezonefinder` (volitelná závislost `obloha[tz]`, kvůli Termuxu), bez něj pásmo
  nejbližšího města.

## Výpočty

- **Hvězdy** se transformují vektorově jednou maticí (precese+nutace `t.M`, GAST,
  místní rámec). Aberace (≤ 20″) a pohyb pólu se zanedbávají; odchylka proti plné
  redukci Skyfieldu < 0,05° (test). Refrakce Sæmundsson pro výšky > −2°.
- **Tělesa Sluneční soustavy** plně přes Skyfield `observe().apparent()`, topocentricky
  (u Měsíce zásadní, paralaxa ~1°). Magnitudy planet: Mallama & Hilton (Skyfield),
  pro Saturn při fázovém úhlu > 6,5° záložní vzorec, Měsíc podle Allena.
- **Východy a západy:** `almanac.find_risings/settings/transits` (Skyfield ≥ 1.47),
  horizont −34′ refrakce minus poloměr disku; nadmořská výška pozorovatele nesnižuje
  horizont (předpokládá se okolní terén ve stejné výšce).
- **Zatmění Měsíce:** `eclipselib` (Danjon), kontakty dopočítané vlastním hledáním
  kořenů na stejné geometrii.
- **Zatmění Slunce:** Skyfield je neumí, implementována vlastní metoda: novy s malou
  ekliptikální šířkou, globální typ z geometrie osy stínu, lokální okolnosti z
  topocentrické separace středů disků Slunce a Měsíce (krok 30 s, zpřesnění bisekcí).
  Magnituda = podíl zakrytého průměru, zakrytí = podíl plochy.
- **Konjunkce:** geocentrické minimum úhlové vzdálenosti, Měsíc–planeta ≤ 5°,
  planeta–planeta ≤ 3° (nastavitelné), vyřazené jsou ty blíže než 12° od Slunce.
- **Meteorické roje:** statická tabulka 11 hlavních rojů (datum maxima IMO, ZHR,
  radiant). Maximum se klade do 02:00 místního času noci po datu; rušení Měsícem podle
  osvětlení a výšky.
- **Satelity:** TLE z CelesTraku (skupina `stations` + Hubble CATNR 20580, volitelně
  Starlink), cache v `$XDG_CACHE_HOME/obloha/tle`, obnova po 24 h, varování nad 7 dní.
  Viditelnost: satelit osvětlený (`is_sunlit`) a Slunce u pozorovatele pod −6°,
  vzorkováno po 10 s. Jasnost ze standardní magnitudy (1000 km, fáze 90°) a fázové
  funkce difúzní koule; standardní magnitudy jen pro ISS, Tiangong a Hubble.
- **Skóre pozorovatelnosti 0–100:** tma (0 nad −6°, 1 pod −18°) × rušení Měsícem
  (osvětlení × √sin výšky) × oblačnost (nízká a střední oblačnost váží víc než tenké
  cirry, viditelnost < 10 km snižuje). Nejlepší okno = nejdelší souvislý úsek ≥ 50.

## Vykreslování a UI

- **Renderer v jádru** (numpy): braille 2×4 body na buňku nebo půlbloky 1×2, barva
  bodu podle priority (jasnější hvězda vyhrává), text nad body, detekce kolizí popisků
  s mezerou. Výstupem je `Frame` (pole znaků a barev); Textual jen zobrazuje řádky
  (`render_line`) a **překresluje pouze řádky, jejichž hash se změnil**.
- **Výkon:** limit 50 ms na scénu + render celé oblohy 120×40 se všemi vrstvami
  (benchmark test, nejlepší ze 7 běhů; v sandboxu ~33 ms). Na pomalejších strojích lze
  test zmírnit `OBLOHA_BENCH_FACTOR`; CI na sdílených runnerech používá faktor 2.
- **Pohled z okna** (začátečník): válcová projekce s horizontem dole; svislé měřítko se
  natahuje (max. 2×), aby horní okraj končil u zenitu. Siluety střech jsou
  deterministický pseudonáhodný profil podle azimutu (otáčí se s pohledem).
- **Celá obloha:** azimutální ekvidistantní, sever nahoře, východ vlevo. **Pohled
  jedním směrem:** stereografická projekce.
- **Barvy:** truecolor nebo xterm-256 (vlastní kvantizace mapy i CSS proměnných, aby
  vypadalo stejně i bez `terminal-overrides`). Detekce z `COLORTERM`/`TERM`, ruční
  přepnutí `--colors`.
- **Noční vidění:** každá barva (i barvy hvězd podle B−V) se převádí na červenou se
  stejnou luminancí; klíčové barvy podle návrhu (#0a0000, #e0403a, #ff5a4a, #8a2622).
- **Bezpečný režim znaků** (`--ascii`): půlbloky místo braille a dvoupísmenné zkratky
  planet (Me, Ve, Ma, Ju, Sa, Ur, Ne), Slunce `O`, Měsíc `o/D/O/C` podle fáze,
  satelit `^`. Aplikace ho nabídne při `TERM=linux`, ne-UTF-8 locale nebo tmuxu < 3.0.
- **Rozložení:** podle šířky terminálu: < 72 sloupců mobilní (vše pod sebou, dotyková
  tlačítka), 72–99 úzké (užší panely), ≥ 100 plné. Přepíná se za běhu při změně
  velikosti.
- **Přes SSH** se živé překreslování zpomalí na `ssh_fps` (výchozí 0,5×/s).
- **Kompas** jen přímo v Termuxu (`TERMUX_VERSION`/`PREFIX`, ne přes SSH) a s příkazem
  `termux-sensor`. Náklon kompenzovaný kurz zadní kamery telefonu, exponenciální
  vyhlazení na kružnici, nestabilita = kruhová směrodatná odchylka posledních 12 hodnot
  > 20°.

## Klávesové zkratky (řešení kolizí z návrhu)

| Kolize v návrhu | Řešení |
|---|---|
| `?` nápověda × `?` „co je to“ (začátečník) | V začátečnické obloze `?` = „Co je to za světlo?“, nápověda je i na `H` (všude) a v menu `≡` / paletě. Jinde `?` = nápověda. |
| `c` kompas × `c` čáry souhvězdí | Kontextově: kompas v začátečnické obloze, čáry souhvězdí v pokročilé mapě. |
| `m` režim × `m` Mléčná dráha | `m` = režim (globální), Mléčná dráha `M`. |
| `L` místo × `L` popisky | `L` = místo, popisky `p`. |
| `j` skočit (úkazy) × `j` kurzor dolů | Různé kontexty, nekolidují. |
| — | Nové: `s` délka kroku času, `i` informační panel, `f`/`x` úkol našel jsem/nápověda, `B` obloha pod obzorem, `+` i `=` zoom. |

Kontexty tvoří strom (globální → obloha → začátečník/pokročilý, globální → úkazy,
místa); kolize se hlásí, pokud je stejná klávesa ve dvou příbuzných kontextech, kromě
výslovně povoleného „zastínění“ (`identify` zastiňuje `help`). Žádná akce nevyžaduje
`Ctrl+Shift` ani funkční klávesy; validace je odmítne i v `[keys]`.

## Struktura

- Jádro (`obloha.core`, `obloha.render`, `obloha.beginner`, `obloha.keymap`,
  `obloha.config`, `obloha.terminal`) neimportuje Textual. `obloha.ui.model.AppModel`
  drží stav a akce bez Textualu, Textual vrstva (`obloha.ui.app`, panely, dialogy) ho
  jen zobrazuje.
- Pokrytí testy: celkem ≥ 85 %, bez UI vrstvy ≥ 90 % (CI to hlídá zvlášť).
