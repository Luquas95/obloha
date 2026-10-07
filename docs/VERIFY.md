# Co nebylo možné ověřit nezávisle (a jak to ověřit)

Vývoj probíhal v sandboxu s přístupem jen k PyPI a npm. JPL, CelesTrak, NASA, USNO,
timeanddate, GeoNames ani Open-Meteo nebyly dostupné. Proto rozlišujeme:

- **nezávislé ověření** – porovnání s publikovanými hodnotami,
- **kontrola konzistence** – porovnání s jinou cestou výpočtu ve Skyfieldu (stejná
  efemerida, jiný algoritmus).

## Referenční hodnoty v testech, přepsané bez přístupu k síti

| Test | Hodnoty | Zdroj | Stav |
|---|---|---|---|
| `test_events.py::test_moon_phases_2026` | novy a úplňky 2026, UTC na minuty | USNO „Phases of the Moon“ | přepsáno z publikované tabulky bez možnosti kontroly online; výpočet sedí ±1 min. **Ověř** proti https://aa.usno.navy.mil/data/MoonPhases |
| `test_events.py::test_seasons_2026_2027` | rovnodennosti a slunovraty | USNO „Earth's Seasons“ | stejné jako výše, **ověř** https://aa.usno.navy.mil/data/Earth_Seasons |
| `test_eclipses.py::test_lunar_eclipse_catalog` | 8 zatmění Měsíce 2026–2028, čas maxima a magnituda | NASA Five Millennium Canon | přepsáno, výpočet sedí ±1 min a ±0,01. **Ověř** https://eclipse.gsfc.nasa.gov/LEcat5/LE2001-2100.html |
| `test_eclipses.py::test_solar_2026_08_12_from_prague` | globální maximum 17:46 UT; v Praze částečné, max. ≈ 18:12 UT, magnituda ≈ 0,88, Slunce nízko | NASA, místní okolnosti | globální čas a typ jsou z katalogu; **místní čas a magnituda pro Prahu jsou vlastní výpočet** potvrzený jen přibližnou znalostí (≈ 20:13 SELČ, ≈ 0,88). Ověř v Hvězdářské ročence 2026 nebo na https://eclipse.gsfc.nasa.gov/SEgoogle/SEgoogle2001/SE2026Aug12Tgoogle.html (klik na Prahu). |
| `test_eclipses.py::test_solar_2027_08_02_from_prague` | globální max. 10:07 UT; Praha max. ≈ 09:15 UT, magnituda ≈ 0,52 | NASA | stejné jako výše, místní hodnoty **ověřit** (SE2027Aug02T). |
| `test_almanac.py::test_sun_times_published_prague` | východ/západ Slunce v Praze 21. 6. a 21. 12. 2026 | timeanddate.com | přepsáno, tolerance ±2 min. **Ověř** https://www.timeanddate.com/sun/czech-republic/prague |

## Pouze kontrola konzistence

- **Východy a západy Slunce a Měsíce (±1 min)** – porovnání našeho obalu
  (`find_risings/settings`, výpočet po dnech v pásmu místa, přechody SEČ/SELČ) se
  starší nezávislou cestou Skyfieldu `risings_and_settings` + `find_discrete`.
  Ověřuje logiku kolem (časová pásma, letní čas, výběr dne), ne samotnou astronomii.
- **Přelety ISS** – nad fixní TLE z dokumentace Skyfieldu (epocha 20. 1. 2014) proti
  přímému volání `EarthSatellite.find_events`; viditelnost proti nezávislému vzorkování
  osvětlení satelitu a výšky Slunce. Skutečné časy přeletů neověřeny (chybí síť).
  **Ověř:** porovnej `obloha` (obrazovka 3) s https://www.heavens-above.com pro stejné
  místo, tolerance ~1 min.
- **Jasnost satelitů** – odhad ze standardní magnitudy a fázové funkce difúzní koule,
  standardní magnitudy jen pro ISS (−1,8), Tiangong (−0,8) a Hubble (2,2). Odchylky
  ±1 mag jsou běžné.
- **Hvězdy alt/az** – proti plné redukci Skyfieldu (< 0,05°) a proti Polárce/Veze
  (výška ≈ zeměpisná šířka, horní kulminace Vegy ≈ 78,7°).
- **Konjunkce, elongace, opozice, perigea** – jen výpočtem Skyfieldu; sedí s
  ilustračními údaji ze zadání (opozice Saturnu 4. 10. 2026, dolní konjunkce Venuše
  24. 10. 2026).

## Data, která chybí nebo jsou neúplná

- **Nadmořské výšky měst.** Žádný dostupný balíček (text-to-map, geonamescache,
  cities.json) je neobsahuje, sloupec `elevation` je prázdný a počítá se s 0 m (Praha
  ve výchozí konfiguraci má 235 m). Vliv na východy a západy je pod 1 minutu (výška
  horizontu se nemění). **Doplnění:** stáhni GeoNames `cities500.zip` /
  `CZ.zip` (sloupce `elevation`, `dem`) a ve `scripts/build_cities.py` je spáruj podle
  `geonameid` nebo polohy.
- **Obce Slovenska.** GeoNames `cities500` obsahuje 750 slovenských sídel, Slovensko má
  ~2 890 obcí. **Doplnění:** číselník obcí Štatistického úradu SR (CSV s kódy) + polohy
  z GeoNames `SK.zip`; formát vstupu stejný jako pro ČR (`Obec, Okres, Kraj, Latitude,
  Longitude`), stačí přidat druhý CSV zdroj do `build_cities.py`.
- **Data meteorických rojů** jsou pevná kalendářní data maxim (IMO), skutečné maximum
  se rok od roku posouvá o ±1 den podle délky Slunce.

## Neotestováno na skutečném zařízení

- **Termux** (instalace podle README, `termux-sensor`, dotyk) – kód kompasu je testovaný
  s falešným senzorem a syntetickými daty. Orientace os vychází z dokumentace Androidu
  (`SensorManager.getRotationMatrix`). **Ověř** na telefonu: `c` v pohledu z okna,
  telefon na výšku, zadní kamera k jihu → nadpis „MÍŘÍŠ NA JIH“.
- **tmux přes SSH, 256 barev, braille v různých fontech** – ověřeno jen snapshoty a
  detekcí proměnných prostředí.
- **PKGBUILD** – nesestaveno (sandbox není Arch). Ověř `makepkg -si` v
  `packaging/aur/`.
- **Open-Meteo a CelesTrak** – formát odpovědí podle dokumentace, testováno přes `respx`
  mocky; skutečné stažení neproběhlo.
