# Vizuální návrh TUI (wireframy)

Převzato ze zadání. Hodnoty jsou ilustrační (pozice hvězd přibližně pro 1. 10. 2026, 21:00 SELČ; časy přeletů ISS jsou vymyšlené). Skutečné screenshoty implementace jsou v `docs/screenshots/`.


Hlavní principy pokročilé mapy:
- Celá obloha jako kruh: zenit uprostřed, **sever nahoře, východ vlevo** (tak, jak se díváš nahoru na oblohu), horizont jako tečkovaný kruh, světové strany česky (S, V, J, Z, SV…), kružnice výšky 30° a 60°.
- Hvězdy v braille bodech podle magnitudy a barvy (B−V), nejjasnější jako větší skupinka bodů. Čáry souhvězdí tlumeně, názvy souhvězdí velkými písmeny a tlumeně, jména jasných hvězd normálně. **Popisky se nesmí překrývat** (detekce kolizí, méně důležitý popisek ustoupí).
- Planety a Měsíc jako symboly v barvě (♄ Saturn, ♃ Jupiter, ♂ Mars, ♀ Venuše, ☿ Merkur, ♅ Uran, ☽/◑ Měsíc podle fáze). Vybraný objekt má hranaté závorky `[♄]`.
- Záhlaví: místo, živý/nastavený čas, výška Slunce a fáze noci, Měsíc, nejzajímavější objekt, mezní magnituda a skóre pozorovatelnosti s pruhem.
- Fáze Měsíce na obrazovce Dnes v noci jako disk z braille bodů (osvětlená část jasně, neosvětlená tlumeně).

Paleta tmavého tématu: pozadí `#0a0e1a`, panel `#0d1222`, obloha uvnitř horizontu `#070b16`, výběr `#1c2a48`, text `#d6dcea`, tlumený `#7a86a3`, potlačený `#2f3a55`, rámečky `#2a3452`, akcent `#8fb8ff`, sekundární akcent `#c9a8ff`, čáry souhvězdí `#3d5a8a`, horizont `#5a6a8f`, Měsíc `#f4f1e0`, Saturn `#f0d58a`, hvězdy podle B−V `#bcd2ff` → `#ffffff` → `#fff1c4` → `#ffc58a` → `#ff9e70`, dobré `#7bd88f`, špatné `#ff7a85`. **Noční vidění:** všechny barvy převedené na odstíny červené (pozadí `#0a0000`, text `#e0403a`, akcent `#ff5a4a`, tlumený `#8a2622`), žádná modrá ani bílá.


**Začátečnický režim, pohled z okna na jih, desktop 120×40 (výchozí obrazovka):**
```
╭─ obloha · Praha ──────────────────────────────────────────────────────────────────── ● živě · čt 1. 10. 2026 · 21:00 ╮
│ Je tma (astronomická noc).  Měsíc vyjde v 21:11 a trochu přisvítí.  Podmínky: dobré ✓                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ POHLED Z OKNA · díváš se na JIH ────────────────────── ◀ ▶ otočit · ▲ ▼ výš/níž ╮╭─ CO TEĎ UVIDÍŠ ──────────────────╮
│                                     ⡀Deneb                                       ││ ● Saturn  planeta                │
│                                     ⠙⠉ ⠐⠤ ⢀⡀                                     ││   Nízko na jihovýchodě,          │
│8┤                                    ⠰⡀    ⠈ ⠐⠢⠄⢀⣀                    ⠄          ││   asi 2 pěsti nad obzorem.       │
│                                        ⡀           ⠐⠒ ⠠⣀                         ││   Nejjasnější bod v té           │
│                                    ⠈   ⠑                 ⠈⠒ ⠠⢄                   ││   části oblohy, nebliká.         │
│7┤                                       ⢢                      ⠈⠑ ⠠⠤             ││                                  │
│                                          ⢀ Letní trojúhelník     ⡀   ⠈⠉ ⠐⢴Vega   ││ ✦ Vega  hvězda                   │
│                                           ⠃            ⠈           ⣁⠄ ⠊⠁         ││   Vysoko na jihozápadě,          │
│6┤                                          ⢢                 ⣀⡀ ⠒⠁               ││   6–7 pěstí nad obzorem.         │
│       ⠠                                     ⢀           ⡀ ⠔⠂                     ││   Jasná, bílomodrá.              │
│                                             ⠈⠂      ⠤⠄ ⠉                         ││                                  │
│5┤                         ⡀Enif               ⣦Altair  ⠂                         ││ ✦ Altair  hvězda                 │
│             Markab                            ⠈                                  ││   Na jihu, napůl k nebi.         │
│4┤               ⠈     ⠐                                                          ││   Vedle něj dvě slabší           │
│                                           ⠂                        ⢀             ││   hvězdy v řadě.                 │
│    ⠠                    ⠈     ⡀                                               ⡀  ││                                  │
│3┤                                                  ⠄                             ││ ◌ Letní trojúhelník  obrazec     │
│                                                                                  ││   Vega, Deneb a Altair           │
│                                         ⠂                                        ││   tvoří velký trojúhelník.       │
│2┤  ● ← Saturn                ⠁                                                   ││   Dobrý začátek orientace.       │
│        nažloutlý, nebliká                                                        ││                                  │
│                                                                                  ││                                  │
│1┤                                                ⠄                               ││                                  │
│                                                   ▄                              ││                                  │
│           ⠠            ⠐Fomalhaut                ███                             ││                                  │
│⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤▄▄⠤▄█⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤███⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄││                                  │
│                ██ ██          ▄              ▄▄▄▄███▄▄▄▄▄█  ▄▄▄█████▪████████████││ ↵ podrobnosti · ? co je to       │
│█████▄▄▄▄▄▄▄▄▄▄▄██▄██▄▄▄▄▄▄▄▄▄▄████████████████████████████▄▄█████████████████████││                                  │
│  ·      ·     JV       ·      ·      J      ·       ·     JZ      ·      ·       ││ ilustrační data                  │
╰──────────────────────────────────────────────────────────────────────────────────╯╰──────────────────────────────────╯
╭─ ÚKOL 2 / 5 · Najdi Letní trojúhelník ───────────────────────────────────────────────────────────────────────────────╮
│ 1. Podívej se na jih a zvedni pohled napůl k nebi: najdeš Altair (s dvěma slabšími sousedy).                         │
│ 2. Doprava a výš, na jihozápadě: nejjasnější je Vega.  3. Skoro přímo nad hlavou je Deneb.                           │
│ Hotovo?  ✓ našel jsem    nápověda    další úkol: Od Velkého vozu k Polárce                                           │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
  ◀▶  otočit  ▲▼  výš/níž  +-  zoom  ?  co je to  u  úkoly  m  mapa (pokročilé)  n  noční  L  místo
```

**Začátečnický režim na mobilu: kompas zapnutý, telefon míří na jihovýchod, „Co je to za světlo?“:**
```
 obloha · Praha ▾                ● 21:00 živě
 Tma ✓  Měsíc vyjde 21:11
╭─ MÍŘÍŠ NA JIHOVÝCHOD ↘ ───── ◎ kompas zap. ╮
│6┤                                          │
│            ⠐                               │
│5┤                                          │
│     Alpheratz                  ⠠Enif       │
│    ⠁             ⠂Markab                   │
│4┤                           ⠁              │
│                               ⠄            │
│         ⠈                          ⠐       │
│3┤                                          │
│                                            │
│                                   ⠠        │
│2┤     ( ● )                                │
│                                            │
│1┤                                          │
│                           ▄                │
│                ⠠          ██⠐Fomalhaut     │
│⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤█⠤⠤⠤⠤⠤⠤⠤⠤▄▄⠤⠤⠤⠤⠤██⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤⠤│
│      ███ ███       ██     ██               │
│██████████████████████▄▄████████████████████│
│V      ·      ·      JV      ·      ·       │
╰────────────────────────────────────────────╯
╭─ ? CO JE TO ZA SVĚTLO ─────────────────────╮
│ ●  Saturn  planeta                         │
│ To nažloutlé světlo nízko na               │
│ jihovýchodě, asi 2 pěsti nad               │
│ obzorem. Nebliká (hvězdy blikají).         │
│                                            │
│ Právě je nejblíž Zemi za celý rok          │
│ (opozice 4. 10.). Celou noc                │
│ nad obzorem, o půlnoci na jihu.            │
│ Prstenec uvidíš jen dalekohledem.          │
│                                            │
│                                            │
╰────────────────────────────────────────────╯

   ◀     ?     ▶     úkoly     ≡

 otoč telefon a mapa se natočí s tebou
 ?  co je to  c  kompas  n  noční

[0] 0:obloha*                  "termux" 21:00
```

**Pokročilý režim (`m`):** následující obrazovky.

**Obloha (pokročilý režim), desktop 120×40:**
```
╭─ obloha · Praha ──────────────────────────────────────────────────────────── ● živě · čt 1. 10. 2026 · 21:00:00 SELČ ╮
│ ☉ −22° astronomická noc   ☽ ◑ 70 % ubývá   ♄ Saturn u opozice   mez. mag. 5,5                                        │
│ 50,08° N  14,44° E   pozorovatelnost ██████████ 86  oblačnost 10 % · Měsíc ruší po 22:00                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ OBLOHA · celá obloha ─────────────────────────────── zenit uprostřed · S nahoře ╮╭─ VYBRÁNO ────────────────────────╮
│                                     ⢀⣀⣀⣀S⣀⣀⣀                                     ││ ♄ Saturn                         │
│                             ⢀⣀⠤⠔⠒⠊⠉⡉⠁  ⠄    ⠉⠉⠉⠒⠒⠤⢄⣀                             ││ planeta · souhvězdí Ryby         │
│                         ⢀⡠⠖⠊⠁               ⠄       ⠉⠒⠦⣀                         ││                                  │
│                      ⢀⠴⠊⠁⢀⠠⠂⢀  ⢀   ⠠      ⢀  ⠁          ⠉⠲⢄                      ││ magnituda    0,6                 │
│                SV  ⡠⠚⠁ ⠐⢀⠢⢖⢆⡀⠂ ⣀       ⠄    ⠈⠈ ⠄         ⠊⠂⠙⠢⡀SZ                 ││ výška        19°                 │
│                  ⡠⠊    ⠐ ⣪Capella          ⠐  ⠂Dubhe    ⠄    ⠈⠢⡀                 ││ azimut       110° (JV)           │
│                ⢠⠊⡀ ⠂⠠   ⠈⠌⡰VOZKA⢀ ⠤⠰ ⠂⡁⠈ ⠈ ⠅⠂⠠ ⠄⠛⠢VELKÁ MEDVĚDICE                ││ RA / Dec     0h 51m / +2° 48′    │
│               ⡜⠁⠁  ⡀ ⠠   ⠂⠐⡂⢔⠚⡐⠥ ⠐⡀    ⠁ ⠁⠄     ⠈⠠⠂⠞⢄ ⠈  ⠁   ⠂⠁  ⠙⡄              ││ vzdálenost   ≈ 8,6 au            │
│             ⢀⠎       ⠤⣀⣀ ⠈⣈⠆⡎⡑⡲⢈ ⠈       ⠐  ⠄  ⠠    ⠈⠦⡈  ⠈⡀   ⠂⠄ ⡀⡈⢆             ││ vychází      18:59               │
│            ⢀⠎ ⢀Plejády⠐⢀⡵Mirfak⡀⠐⠁⠁  ⢀ ⠠Polárka  ⠒ ⠐  ⠊⠑⠄     ⠈    ⠈⢆            ││ kulminuje    01:09 · 43°         │
│           ⢀⠏ ⢄  ⠘ ⠂⠠ ⠢⡊⠃  PERSEUS     ⡀ ⡀⠙⠒⠒⠲⡩⠜MALÁ MEDVĚDICE    ⠐  ⠈⢇           ││ zapadá       07:23               │
│           ⡜⠐         ⢠⡁⢀  ⡀⢁⢍⢐⡿⠨⠂⠠ ⢀ ⢧⠂⠐ ⠔⠡⠁⣀⠁    ⠠⠐   ⠐⡀⠄⠠   ⠈    ⡄ ⠘⡄          ││                                  │
│          ⢰⠁          ⠂ ⡄ ⢀ ⢄⠂⡨⡽⠊⡇⡔⢂   ⢣     ⠈⢨⠠⠐⠁⠌⠊ ⢀   ⠂⡀ ⢁⠈  ⢀⣀⡠⢴Arktur        ││ Blízko opozice: celou noc        │
│          ⡎      ⠈   ⡁ ⠰⡇    ⠈⢐⢙⡓⠟⡦⡱⠐⡀ ⢸  ⠂⡀⢠⠁⡄⡐⠉⢣ ⡉⡀⢀ ⠁     ⠄  ⠁ ⠆⠄⠠  ⠈⡆         ││ nad obzorem, nejjasnější         │
│         ⢀⠇  ⣀    ⡄ ⠠⢀  ⡇     ⠐⠠KASIOPEJA⠄⡐⢠⠢⣅⢈⠄⠉ ⡴⠁  ⠄      ⠐ ⠁ ⠠⠠⠐⠠   ⢇         ││ kolem půlnoci na jihu.           │
│         ⢸  ⢀    ⠸ BERAN⡇ANDROMEDA⠑⠽⣁⣉⡈⢀⡐KEFEUS⠄⡁⠈ ⢁ ⠠   ⠂   ⠈⡁  ⠠ ⠈    ⢸         ││                                  │
│        V⢸          ⡁   ⢇⢀⠊ ⠐ ⢈⠁ ⢅⠈⡢⢉⡨⣂⢖⣛⡑⡱⠒⡅ ⠂⠈⠄  DRAK  ⠁⠠ ⢀ ⠄         ⢸ Z       ││ NEJJASNĚJŠÍ NAD OBZOREM          │
│         ⢸  ⠁       ⠄⠄⠊  ⢣Alpheratz ⢈⠐⣨⢩⡸Deneb⠄ ⢀⣄Vega    ⠈⠂⢀ ⠂    ⠈  ⠆ ⢸         ││ ♄ Saturn        0,6    19°       │
│         ⠸⡀ ⠂⡀   ⠂  ⠰   ⡰⠓⠈⠑⠤⡀ ⢂    ⠡ ⠤⣀⠠⣐⠿⢄⣔⠃⣚⠁⢺⡇⢀LYRA    ⠄ ⢀⢁  ⡀  ⠄   ⡸         ││ ✦ Arktur       -0,1    11°       │
│          ⡇⡈ ⠠    ⡀⠄⠈⡀ ⣔⠁ ⠠  ⢸⠁ ⠨⠈⠈⡀    ⠐⠑ ⡡LABUŤ⢑⠆⣀      ⡀⡀ ⠄     ⠠   ⠄⡇         ││ ✦ Vega          0,0    66°       │
│          ⢸     [♄]Saturn⠢⣄⡄⢀⠇⢀ ⡀⠈⠰   ⠰     ⠌ ⠍⢐⣎⠥⡄⠁⠄ ⠠   ⢀ ⡈          ⢸          ││ ✦ Capella       0,1    16°       │
│          ⠈⢆     ⠡    ⠁⡀   ⠈⠺⡀⡀⣀ ⠂⢀⠈ ⠂⠠ ⡀⡀⢄⡀⠄⠐⠍⠠⠒⠄⠜⢀⠢⠊⠢  ⠈ ⠠   ⣀ ⠄  ⠁ ⢀⠎          ││ ✦ Altair        0,8    48°       │
│           ⠘⡄     ⢀  ⠐ ⠐  ⡀  ⠑PEGAS⠢⠈ ⠂ ⠠⠐ ⠁ ⠤ ⠐⡠⢶⠨⠣⠒⠇⡀⠂  ⡐   ⠐⡀⢀   ⠅ ⡜           ││ ✦ Fomalhaut     1,2     5°       │
│            ⠸⡀          ⠈⠠     ⠑⢌⠤⠔⠂⠂  ⠄     ⢴Altair⠂⢊⠄⠙ ⠆⡀       ⢀  ⡸            ││ ✦ Deneb         1,2    85°       │
│             ⠙⡄   ⠠ ⠂  ⠁⠁ ⠈⠠⠎   ⢀⠄   ⢀  ⢐  ⠠⢀⠎ OREL ⠑⠄⡙⠝⡣⢈⢀      ⡀  ⡜⠁            ││ ✦ Mirfak        1,8    30°       │
│              ⠘⢤⠁ ⡀      ⠂ ⠂ ⠁⠄⢀ ⠑⠤⡀⢀   ⠠ ⠁ ⠎⠁    ⠸⡐⠑⡊⠌⠈⢠⡀⠔⠤      ⢠⠜              ││ ✦ Polárka       2,0    50°       │
│                ⠣⡄    ⠂      ⢀  ⠐ ⠌⢉ ⡄       ⢀ ⠄⠐ ⠁   ⠐⠡⠁⠖⠲⡀⠐⠠   ⡤⠃               ││                                  │
│                 ⠈⠢⡀       ⠁ ⢀    ⣀⣠⣀⣀⣈⣠⣁⣁⣈⡀⠁         ⡐ ⠊⠐⠂⢁⠈⠂ ⡠⠊                 ││                                  │
│                JV ⠉⠢⣰  ⠁        ⠈         ⠠         ⡀⠄⠋⠡⠒ ⡈⣀⡢⠊JZ                 ││ ☽ vychází v 21:11                │
│                      ⠑⠤⣊ ⢶Fomalhaut   ⠁⠈ ⠁   ⠠⠄   ⢈⠂⠂⡊⠙⡠⢈⡠⠔⠁                     ││ ▲ ISS přelet 05:42 (−3,1 mag)    │
│                         ⠓⠢⢄⡀⠈         ⠠   ⢀   ⢐    ⠁⡁⣙⠬⢒⠃                        ││                                  │
│                            ⠈⠙⠢⠤⢄⣀⡀        ⠂⠄   ⣀⣀⠤⠤⠚⠉⠈                           ││ ilustrační data                  │
│                                  ⠈⠉⠉⠑⠒⠒J⠒⠒⠒⠒⠉⠉⠉                                  ││                                  │
╰──────────────────────────────────────────────────────────────────────────────────╯╰──────────────────────────────────╯
  ?  nápověda  /  hledat  space  pauza  ,.  čas  <>  rychlost  v  pohled  c  souhvězdí  n  noční  q  konec
```

**Dnes v noci, desktop 120×40:**
```
╭─ obloha · Praha ──────────────────────────────────────────────────────────── ● živě · čt 1. 10. 2026 · 21:00:00 SELČ ╮
│ ☉ −22° astronomická noc   ☽ ◑ 70 % ubývá   ♄ Saturn u opozice   mez. mag. 5,5                                        │
│ 50,08° N  14,44° E   pozorovatelnost ██████████ 86  oblačnost 10 % · Měsíc ruší po 22:00                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ DNES V NOCI · 1.–2. 10. 2026 ──────────────────────────────────────────────────────────────────────────────── Praha ╮
│             18     19     20     21▾    22     23     00      01     02     03     04     05     06     07           │
│ obloha      ████████████████████████████████████████████████████████████████████████████████████████████████████     │
│ Měsíc                                ◑━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━     │
│ Saturn          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━             │
│ Uran                         ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━         │
│ Jupiter                                                      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━     │
│ pozorov.    ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▃▃▃▃▃▃▃▅▅▅▅▅▅▅▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ ▅▅▅▅▅▅▅▅▅▅▅▅▅▅▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▃▃▃▃▃▃▃▁▁▁▁▁▁▁      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ ☉ SLUNCE  ·  ☽ MĚSÍC ───────────────╮╭─ PLANETY ─────────────────────────────────── seřazeno podle pozorovatelnosti ╮
│ západ Slunce                 18:47   ││ planeta     mag    souhvězdí     nad obzorem       nejvýš     hodnocení      │
│ konec občanského soumraku    19:19   ││                                                                              │
│ konec nautického soumraku    19:56   ││ ♄ Saturn    0,6    Ryby          18:59 – 07:23     01:09 43°  █████          │
│ konec astronomického         20:33   ││ ♅ Uran      5,7    Býk           20:25 – 13:10     04:47 59°  ███░░          │
│ astronomická noc             10 h 05 m│ ♃ Jupiter   −2,1   Rak           00:52 – 16:30     08:40 58°  ██░░░          │
│ východ Slunce                07:06   ││ ♂ Mars      1,6    Lev           03:05 – 17:20     ráno 25°   █░░░░          │
│                                      ││ ♀ Venuše    −4,3   Panna         pod obzorem       u Slunce   ░░░░░          │
│   ⣠⣴⣶⣶⣤⡀   ubývající                 ││ ☿ Merkur    −0,2   Váhy          pod obzorem       u Slunce   ░░░░░          │
│  ⣼⣿⣿⣿⣿⣿⣿⡄  osvětleno 70 %, stáří 20 d││                                                                              │
│  ⢿⣿⣿⣿⣿⣿⣿⠇  vychází 21:11, zapadá 13:29│ Tip: Saturn je 4. 10. v opozici, prstence jsou letos skoro z boku.           │
│  ⠈⠻⢿⣿⣿⠿⠋   nov 10. 10. · úplněk 26. 10│                                                                              │
╰──────────────────────────────────────╯╰──────────────────────────────────────────────────────────────────────────────╯
╭─ ÚKAZY · PŘÍŠTÍCH 30 DNÍ ────────────────────────────────╮╭─ ▲ PŘELETY ISS · viditelné ──────────────────────────────╮
│ 4. 10.  ♄ Saturn v opozici                               ││ datum     začátek   nejvýš        konec       jasnost    │
│ 8. 10.  ☄ Drakonidy (max., ZHR ~10)                      ││                                                          │
│ 10. 10. ● nov Měsíce                                     ││ 2. 10.    05:39 SZ  05:42 71°     05:45 JV    −3,4       │
│ 21. 10. ☄ Orionidy (max., ZHR ~20)                       ││ 3. 10.    04:51 S   04:54 35°     04:57 V     −2,1       │
│ 24. 10. ♀ Venuše v dolní konjunkci                       ││ 3. 10.    06:27 Z   06:30 48°     06:31 J     −2,8       │
│ 25. 10. ◷ konec letního času (03:00 → 02:00)             ││ 4. 10.    05:40 SZ  05:43 82°     05:46 JV    −3,6       │
│ 26. 10. ○ úplněk                                         ││                                                          │
│                                                          ││                                                          │
│ ↵ detail · j skočit na čas úkazu                         ││ dráhy z CelesTraku · stáří 6 h                           │
│                                                          ││                                                          │
│                                                          ││                                     ilustrační data      │
╰──────────────────────────────────────────────────────────╯╰──────────────────────────────────────────────────────────╯
  1  obloha  2  dnes  3  satelity  4  úkazy  5  nastavení  ?  nápověda  q  konec
```

**Obloha, mobil na výšku v tmuxu 46×44 (místo Brno, spodní řádek je stavový řádek tmuxu):**
```
 obloha · Brno ▾                 ● 21:00 živě
 ☉ noc  ☽ 70 %  ♄ Saturn  ◆ 86
 49,20° N 16,61° E · čt 1. 10. 2026
╭─ OBLOHA ────────────────────────────── S ↑ ╮
│                                            │
│                   ⢀⣀⣀S⣀⣀                   │
│             ⣀⠤⠔⠒⠉⠉⠁ ⠂   ⠉⠉⠑⠒⠤⢄⡀            │
│         ⢀⡠⡔⠍⠊ ⠄⡀      ⠄ ⠁     ⠈⠑⠤⣀         │
│       ⢀⠔⠋ ⠄⣊⡵⣰⢘⡀    ⠂   ⠠⢀⠦⢄⡀  ⢀  ⠓⢄       │
│     ⢀⠔⠁⠄⡀⠁⡅⡙Capella⠂⡂⢀⠂⠂⠠ ⡉⠒⢯⠄⠠   ⠠⠠⠑⢄     │
│    ⢠⠎     ⠢⢘⡒⣔⢮⡒⠬     ⠁    ⠈ ⠷⣔      ⠈⢦    │
│   ⢠⠃⢀   ⠈⠍⡱⠧⡻⠦⠖⢆⠆⠂ ⠠ Polárka⠈  ⠃   ⠈   ⢣   │
│  ⢠⠇    ⠐⠐⠮⠑⠊⠕⠽⣲⠼⡑⡡⢀⣔ ⠢⢐ ⡙⡁⡠ ⡀  ⢀⠁⠄⢀   ⢠⠄⢧  │
│  ⡎      ⠐⠁⡄⢂⡈⡱⢺⣿⣛⣆⡕⣈⡆ ⢠⢀⡇⡠⢤⢀⠥⠐⠠⠈ ⠐  ⠔⠲⡙⠁⠈⡆ │
│ ⢠⠃    ⠁⢀⠁ ⡇ ⠈⢀⠏⣻KASIOPEJA⠢⠬⣦⠚⠠    ⢁⡀ ⠄⠄⠂ ⢣ │
│ ⢸⠁ ⠐  ⠇⠠⠂ ⢣⢀  ⡸⠞⢐⠬⠶⣦⡒⠗⣲⡤⠲⡠⠆⠐   ⠈  ⠠  ⠁   ⢸ │
│V⢸      ⠐  ⠘⢆  ⠠⠘⠁⠏⠲⢊⡟⣿Deneb⢄⠡    ⠂⠔   ⠈  ⢸Z│
│ ⠸⡀ ⡀  ⠂⠈⡀ ⡠⠓⠉⠢⡐ ⠌⠈⢑⠉⠇⡱⣷⠭LABUŤ⡀    ⡈⠂   ⠁ ⡸ │
│  ⢇⠃  [♄]Saturn⠃⢈⠠   ⠌⠑ ⠞⠘⡃⢕⢪⣁⣰⠄⡀⡈⠌⠄    ⡀⢀⠇ │
│  ⠸⣀   ⠐ ⠁⢁  ⠈⠛⢔⠄ ⢊⠠⠂⠠⢄⠐⠅⢓⠢⢙⡖⣡⢬⢀⠠⢀⠁ ⠰⠂   ⡸  │
│   ⢱⡀      ⢐⠈  ⠈PEGAS    ⢴Altair⢕⠨⢀     ⣰⠁  │
│    ⠱⡀⠄ ⠂⠂ ⠁⠈⢠⠠⡀ ⠤⣀ ⠐ ⡀ ⢨⠃ ⠂⢺⡈⠤⢸⠬⠑⠧⠠  ⠂⡰⠁   │
│     ⠘⢆      ⢀  ⠂⠠⠈⡂⢀ ⡀⢀ ⡀⠠ ⠂⠐⠁⠠⣐⠩⢂⢄⡁⢀⠞     │
│       ⠑⢤  ⠠     ⠠⠒⠓⠒⠒⠒⠒⢂     ⡘⢘⡠⠑⠁⣤⠔⠁      │
│         ⠉⠦⣀⠠⡦ ⡀     ⠁    ⠒ ⢈⠰⣂⣁⣱⡪⡏⠁        │
│            ⠉⠲⠤⣀⡀       ⠂ ⠐ ⣀⡠⠴⢊⠁⠆          │
│                ⠈⠉⠉⠒⠒⠒⠒⠒⠒⠊⠉⠉                │
│                     J                      │
╰────────────────────────────────────────────╯
╭─ ♄ Saturn ─────────────────────────────────╮
│ mag 0,6  výška 21°  az 111° JV             │
│ vychází 18:49  kulm. 01:02  zapadá 07:14   │
│ Ryby · ≈ 8,6 au · blízko opozice           │
│                                            │
│ ▲ ISS přelet 05:41 · −3,4 mag              │
│ ◑ Měsíc vychází 21:07                      │
╰────────────────────────────────────────────╯

   ◀◀      ▌▌      ▶▶      ⌕      ≡

 klepnutí = výběr · tažení = posun · 2× zoom
 ?  pomoc  /  hledat  n  noční  v  pohled

[xia] 0:obloha*  1:zsh            "xia" 21:00
```
Noční vidění vypadá stejně, jen v odstínech červené.

