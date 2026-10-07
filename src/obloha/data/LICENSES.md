# Licence a atribuce dat

## Hvězdy, souhvězdí, Mléčná dráha (`catalog.npz`, `catalog.json`)

Odvozeno z npm balíčku **d3-celestial** (verze 0.7.35), © 2015 Olaf Frohn,
licence BSD-3-Clause. Soubory `stars.6.json`, `stars.8.json` (jen hvězdy
potřebné pro čáry souhvězdí), `starnames.json`, `constellations.json`,
`constellations.lines.json`, `constellations.borders.json` a `mw.json`.
Převedeno skriptem `scripts/build_catalog.py`. Původní data hvězd pocházejí
z katalogu Hipparcos (ESA), hranice souhvězdí z IAU (Davenhall & Leggett),
obrys Mléčné dráhy z projektu Milky Way outline (Jose R. Vieira).

```
Copyright (c) 2015, Olaf Frohn
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## České názvy (`names_cs.json`)

Vlastní ručně sestavený soubor tohoto projektu (licence MIT jako zbytek kódu).

## Efemeridy DE421

Soubor `de421.bsp` se instaluje jako závislost z PyPI balíčku **skyfield-data**
(MIT). Samotná efemerida DE421 je dílo JPL/NASA (Folkner et al. 2008) a je
volně šiřitelná (US Government work, public domain).

## Databáze měst (`cities.sqlite`)

Viz sekce níže, doplněno skriptem `scripts/build_cities.py`.

### Obsah `cities.sqlite`

* **Obce ČR** (všech 6 259 obcí s okresem a krajem): npm balíček **text-to-map**
  (© 2023 Marek Lisý, MIT), soubor `dist/souradnice.csv`, odvozeno z otevřených
  dat ČSÚ / RÚIAN.
* **Slovensko a svět**: **GeoNames** (https://www.geonames.org), licence
  **CC BY 4.0**, získáno přes PyPI balíček **geonamescache** 3.0.2 (MIT):
  SR z `cities500`, ostatní státy z `cities15000` (města nad 15 000 obyvatel).
  Názvy krajů (admin1) z npm balíčku **cities.json** (CC BY 4.0, GeoNames).
* Časová pásma pocházejí z GeoNames, české exonymy (Vídeň, Mnichov…) jsou
  ručně doplněné v `scripts/build_cities.py`.
* Nadmořské výšky nejsou v žádném z balíčků k dispozici (viz `docs/VERIFY.md`).
