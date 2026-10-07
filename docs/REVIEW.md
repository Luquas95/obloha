# Revize

Na konci vývoje proběhly tři nezávislé revize (samostatní subagenti, bez úprav kódu):
(1) astronomická správnost, (2) kvalita kódu a testů, (3) UX z pohledu úplného
začátečníka. Nálezy **high** a **medium** jsou opravené (commit
`fix: review findings …` a `fix(ux): …`), u **low** je uvedeno, co se stalo.

## 1. Astronomická správnost

| # | Závažnost | Nález | Stav |
|---|---|---|---|
| 1 | high | Horní konjunkce Merkuru a Venuše hlášené jako „v opozici“ (`oppositions_conjunctions` u vnitřních planet jen mění stranu). | Opraveno: u Merkuru a Venuše je každý přechod konjunkce, dolní/horní podle vzdálenosti. Test `test_inner_planet_conjunctions_are_not_oppositions`. |
| 2 | medium | Volba „čas pozorovatele“ používala pevný posun UTC místo pásma (chyba o hodinu přes změnu času). | Opraveno: `local_zone()` z `TZ` nebo `/etc/localtime`. Test `test_local_zone`. |
| 3 | medium | Konjunkce Měsíce s planetami geocentricky (paralaxa ~1°): jiná vzdálenost i čas než z místa. | Opraveno: geocentrické kandidáty se zpřesní topocentricky (±12 h, 1 min). Test `test_moon_conjunction_is_topocentric`. |
| 4 | low | Změny času v pásmech s půlhodinovým posunem (St. John's, Lord Howe). | Ponecháno; pro ČR/SR bez vlivu, zapsáno sem. |
| 5 | low | Práh západu Slunce −0,833° porovnáván s již refraktovanou výškou. | Opraveno (−0,27° u refraktované výšky) v `sky_phase` i u viditelnosti zatmění. |
| 6 | low | Hodiny mimo předpověď počítány jako jasno. | Opraveno: označené jako neznámé, nevyhrávají „nejlepší okno“. Test `test_unknown_hours_do_not_win`. |
| – | ok | Globální typy všech 108 zatmění Slunce 2001–2049 souhlasí s katalogem NASA; hvězdy proti plné redukci ≤ 21″; refrakce, topocentrická tělesa, východy/západy, polární den/noc, ΔT, zatmění Měsíce, viditelnost a jasnost satelitů, skóre. | — |

## 2. Kvalita kódu a testů

| # | Závažnost | Nález | Stav |
|---|---|---|---|
| 1 | high | Selhávající worker (např. úkazy přes konec DE421) se donekonečna restartoval a vytěžoval CPU. | Opraveno: chyba se ohlásí jednou a stejný výpočet se neopakuje; rozsahy úkazů a přeletů oříznuté na DE421. Test `test_background_workers_compute_and_do_not_loop_on_errors` (s `sync=False`), `test_events_clamped_near_ephemeris_end`. |
| 2 | medium | Závod: worker mohl uložit přelety ke starým TLE po jejich znehodnocení. | Opraveno: čítač generací, výsledky ze staré generace se neukládají. |
| 3 | medium | Po přepnutí oblíbeného místa se nestáhlo počasí; probíhající stažení mohlo zapsat předpověď starého místa. | Opraveno: stahování po každé změně místa, výsledek se zahodí, pokud se místo mezitím změnilo. |
| 4 | medium | `fetch_forecast` padal na poškozené cache/odpovědi (TypeError, IndexError). | Opraveno, testy `test_corrupt_cache_is_ignored`, `test_malformed_payload`. |
| 5 | medium | Satelity kreslené daleko mimo platnost TLE (nesmyslné polohy a stovky „přeletů“). | Opraveno: mimo ±30 dní od epochy se satelit nezobrazuje ani nepočítá. |
| 6 | medium | Uložení konfigurace mazalo neznámé klíče, komentáře v `[[favorites]]` a zapisovalo všechny výchozí hodnoty. | Opraveno: zachovává neznámé klíče a komentáře, zapisuje jen změny, oblíbená místa upravuje na místě. Rozšířený `test_roundtrip_keeps_comments`. |
| 7 | low | `parse_tle` bral řádky bez kontrolního součtu. | Opraveno + test. |
| 8 | low | Poškozený `meta.json` shodil úložiště TLE. | Opraveno + test. |
| 9 | low | Keymap přijímal `ctrl+`, `ctrl+ctrl+a`; `[keys]` neuměl seznamy. | Opraveno + testy. |
| 10 | low | Nečitelný `config.toml` (kódování, práva) skončil tracebackem. | Opraveno: `ConfigError` + test. |
| – | testy | Aserce s `or True` a vždy pravdivý výraz. | Opraveno (přesné hodnoty). |

## 3. UX pro začátečníka

| # | Závažnost | Nález | Stav |
|---|---|---|---|
| 1 | high | Noční vidění propouštělo modrou a bílou (tlačítka, scrollbary, odkazy, vstupy). | Opraveno: vlastní Textual téma odvozené z palety pro všechny vestavěné widgety. Test `test_night_vision_has_only_red_hues` prochází i otevřené dialogy. |
| 2 | high | Patička v pohledu z okna ukazovala „? nápověda“, i když `?` tam znamená „co je to“. | Opraveno: patička i nápověda respektují zastínění (`H nápověda`). Test. |
| 3 | high | Saturn (cíl první lekce) na úzkých displejích bez popisku. | Opraveno: cíle lekcí a „Co teď uvidíš“ jsou vždy popsané, popisky se drží uvnitř mapy. |
| 4 | high | `--ascii` nebylo ASCII ani čitelné. | Opraveno: hvězdy jako `. + *`, střechy `#`, horizont `_`, bez výplně Mléčné dráhy, ASCII rámečky, symboly v textech nahrazené (`Sa`, `C`, `*`…). |
| 5 | medium | Z pokročilé mapy nebylo vidět, jak zpět. | Opraveno: `m začátečník` / `m pokročilý` v patičce obou režimů. |
| 6 | medium | „Podívej se na jihu“ (špatný pád). | Opraveno („Podívej se na jih“). |
| 7 | medium | „Co je to“: označení `β Cap`, nepravděpodobné alternativy, zkratky a stupně. | Opraveno: „hvězda v souhvězdí Kozoroh“, alternativy až od 8 %, „Ukazuješ na východ, asi 2 pěsti“, „jistota 95 %“. |
| 8 | medium | Stav Měsíce si odporoval (70 % „trochu přisvítí“). | Opraveno: nad 50 % „hodně přisvítí“, uvádí směr. |
| 9 | medium | Klávesy lekcí nebyly vidět, „nápověda“ kolidovala se slovem pro help. | Opraveno: „f ✓ našel jsem“, „x poraď mi“. |
| 10 | medium | Popisky splývaly. | Opraveno: mezera dvou buněk vpravo. |
| 11 | medium | Žargon na obrazovce Dnes v noci. | Částečně: v začátečnickém režimu „jasnost“, „jak dobře“, roje „až ~N meteorů/h“; pojmy v detailech úkazů jsou ve slovníčku. |
| 12 | medium | Mobil: patička uříznutá a duplicitní, chybí ▲▼. | Opraveno: na mobilu jen nápověda gest, tlačítka ◀ ▲ ? ▼ ▶ úkoly ≡. |
| 13–17 | low | „5 prsty“, „nejbližší noc“, „Osvětlený z“, „Měsíc Měsíc“, zdvojená věta u trojúhelníku. | Opraveno. |
| 18 | low | „napůl k nebi“ už od 25°. | Ponecháno (hranice dle testů a zadání „nízko / napůl k nebi / skoro nad hlavou“). |
| 19 | low | Číslování úkolů podle celého kurzu. | Ponecháno záměrně (postup kurzem). |
| 20 | low | Orion „nad/pod pásem“ neplatí při východu. | Opraveno („na jedné / druhé straně pásu“). |
| 21 | low | Nápověda na rámečku mapy zabírá místo. | Ponecháno. |
