# Programm-Umstrukturierung 2026 (MS50 / Plus-neu / A1-neu)

> **Arbeitsdokument / Zwischenstand.** Wird während der schrittweisen Daten-Einspielung
> gepflegt. Kein fertiges Lastenheft. Stand fortlaufend aktualisieren.

## Kontext

CALLERLAB strukturiert die Tanzprogramme um (gültig ab 01.09.2026):

- **Mainstream** wird auf **50 Calls** gestrichen (MS50).
- **Plus** bekommt etliche Calls dazu — teils aus dem alten Mainstream, teils aus Advanced 1.
- **Basic 1 + Basic 2** fallen als eigene Programme weg; ihre Figuren zählen künftig zu Mainstream (2026).
- Für eine Übergangszeit existieren **alte und neue Listen parallel**.

## Namenskonvention — Jahres-Suffix

Neue Programme bekommen das Jahr als Suffix, alte behalten den blanken Namen:

| alt (Bestand) | neu (2026) |
|---|---|
| `Mainstream` | `Mainstream (2026)` |
| `Plus` | `Plus (2026)` |
| `Advanced 1` | `Advanced 1 (2026)` |

## Nummernband-Schema

`teaching_order` = REAL. Ganzzahl = Programm-Band, Nachkomma = `SLOT`(4) + `SUB`(2).
Regel: **neu = alt + 1**. Die **runden Bänder halten das NEUE** Programm (MS50 auf `30`
war bereits gesetzt; per DB-Analyse liegen auch Plus-2026 auf `40` und A1-2026 auf `50`
schon vor). Die **alten** Programme gehen jeweils eine Stufe tiefer und müssen neu
aufgebaut werden.

| Programm | Band alt (aufbauen) | Band neu (schon da) |
|---|---|---|
| Basic 1 | `10` | — (geht in MS50 auf) |
| Basic 2 | `20` | — (geht in MS50 auf) |
| **Mainstream** | **`29`** | `30` ✅ (= MS50) |
| **Plus** | **`39`** | `40` ✅ (= Plus 2026) |
| **Advanced 1** | **`49`** | `50` ✅ (= A1 2026) |
| A2, C1, C2, C3a, C3b | `60`/`70`/`80`/`90`/`100` | unverändert (kein alt/neu) |

10er-Schritte lassen genug Luft für die Zwischen-Bänder.

**Aktueller DB-Zustand (per Analyse 2026-08-27):** Die DB ist bereits Richtung NEU
migriert — Band 30 = MS50 (20 von 90 Figuren drin), Band 40 = Plus 2026 (51 von 55),
Band 50 = A1 2026 (vollständig, 12 A1→Plus-Wanderer bereits raus). Zu tun bleibt: die
ALTEN Bänder 29/39/49 aufbauen, MS50 (30) mit den restlichen Basic-Figuren auffüllen,
Plus 2026 (40) um die 4 Basic-Wanderer ergänzen. Davids „im Plus/A1 ist noch das Alte
drin" traf den Ist-Zustand nicht ganz — es ist umgekehrt das Neue schon da.

## Ziel-Architektur (4 Pakete, noch nicht umgesetzt)

1. **Schema — Mehrfachnennung erlauben.** Heute ist `teaching_order_calls.entity_id`
   PRIMARY KEY → ein Call = ein Programm. Neu: Call-Identität von Zugehörigkeit trennen.
   - `calls` (`entity_id` PK, `canonical_name`) — stabile Identität
   - `call_programs` (`entity_id`, `teaching_order`, `program`) — mehrere Programme je Call
   - `call_text_mappings` bleibt unverändert (zeigt weiter auf stabile `entity_id`)
2. **Lokation → mehrere Programme.** Statt einer `locations.dance_program_id` eine
   Verknüpfungstabelle (`location_programs`); Mehrfachauswahl im Lokations-Editor.
   Grund: Wer Plus (2026) tanzt, tanzt auch MS50 (included). Wer alt tanzt, will
   Basic 1+2 + Mainstream + Plus + A1 (alt) zusammen.
3. **Sequenz-Filter neu — Mengen-Zugehörigkeit statt Schwellwert.** Heute:
   `max_teaching_order <= Programm-Grenze` (~47 Stellen). Neu: „**sind ALLE Calls der
   Sequenz im gewählten Programm-Set enthalten?**". Löst das Problem, dass der
   „schwerste Call" bei Mehrfachnennung nicht mehr eindeutig ist. Innerhalb eines
   gewählten Sets kommt jeder Call wieder genau einmal vor.
4. **Datenpflege.** Quell-Listen einspielen (siehe unten), Basics ins MS50-Band
   ergänzen, Alt-Bänder 29/39/49 aufbauen.
5. **Verteilung an Bestandsnutzer** (siehe eigener Abschnitt unten). Referenzdaten
   liegen in derselben DB wie Nutzerdaten; der Update-ZIP schließt die DB aus. Es
   braucht einen versionierten Referenzdaten-Reseed beim Start.

## Umsetzungsstand

**Paket 1 — Schema: ✅ ERLEDIGT & getestet (2026-08-27), noch nicht gebaut/ausgerollt.**
- `song_db.py`: neue Tabellen `calls` (Identität) + `call_programs` (Mehrfach-Zugehörigkeit);
  `teaching_order_calls` ist jetzt eine **VIEW** über beide → alle Leser laufen unverändert.
- `call_text_mappings.entity_id`-FK auf `calls` umgebogen.
- Migration `_migrate_calls_split()` konvertiert Bestands-DBs einmalig & idempotent
  (Tabelle→View), erhält alle Daten und Mappings (inkl. der 65 vorbestehenden verwaisten).
- Writer angepasst: `bulk_insert_teaching_order_calls`, `clear_teaching_order_calls`,
  `ensure_filler_words_entity`.
- Verifiziert: Bestands-Migration (594 calls/594 programs, View==Original), Frisch-DB-Pfad,
  **Mehrfachnennung** (call_dosado in Band 10 + 30), Idempotenz.
- Backups: `_fallback/song_db.py.bak_ms50_schema_20260827`, `2_Test/callers_caddy.db.bak_pre_ms50_*`.
- **Offen:** die echte `2_Test/callers_caddy.db` migriert beim nächsten App-Start automatisch.

**Paket 2 — Datenmodell `location_programs`: ✅ ERLEDIGT & getestet (2026-08-27).**
- Junction-Tabelle `location_programs(location_id, dance_program_id)`; `dance_program_id`-Spalte
  bleibt als Kompat-Spiegel (erstes Programm) bestehen.
- Backfill-Migration `_migrate_location_programs()` (einmalig, zwingt entfernte Programme nicht zurück).
- Accessoren `get/set_location_program_ids`. Verifiziert inkl. Zwei-Programme-Zuweisung.
- **Offen (Paket 2 UI):** Mehrfachauswahl im Lokations-Editor + Rückstell-UI. Noch nicht gebaut.

**Paket 3 — Mengen-Filter-Methode: ✅ Kern fertig & getestet (2026-08-27), noch NICHT verdrahtet.**
- `get_sequence_ids_for_bands(allowed_bands)` in `song_db.py`: gibt Sequenzen zurück, deren
  gemappte Calls ALLE in der Vereinigung der gewählten Bänder liegen und die mind. einen
  erkannten Call haben. Performant (~70 ms Vollbestand, GROUP BY/HAVING, kein Korrelieren).
- **Entscheidungen umgesetzt:** (1) **nicht-kumulativ** — Caller wählt die tieferen Programme
  explizit mit; Filter = Vereinigung der eigenen Bänder der gewählten Programme. (2) call-lose
  Sequenzen (30 Stück) werden ausgeschlossen.
- **Wichtiger Befund:** Die 6.441 Sequenzen ohne `max_teaching_order` sind Import-Altlast
  (`source=''`, Max nie berechnet), 6.411 davon HABEN gemappte Calls → der Mengen-Filter
  klassifiziert sie korrekt (repariert die Altlast nebenbei). Der alte Max-Filter blendete
  sie fälschlich aus. Umstieg ändert also sichtbar (meist mehr) Ergebnisse — gewollt.
- **Mehrfachnennungs-Bug gefixt (2026-08-27):** Filter aggregiert jetzt pro FIGUR
  (`MIN(covered)=1`), nicht pro call_programs-Zeile. Vorher wurde eine Figur mit Bändern
  z.B. [10,30] bei Auswahl {30} über ihre Band-10-Zeile fälschlich als Fremd-Call gewertet.
  Validiert: auf Sim-DB (Basic in Band 30) springt `{30}` von 4 → **2.417**; auf
  unveränderter DB unverändert (2.555 / 7.856). Perf ~100–130 ms.
- **Offen (Verdrahtung):** neuen Filter statt `max_teaching_order <= limit` in
  `_build_sequence_where`/Aufrufer einhängen, gespeist aus `location_programs` → Bänder.

**Daten-Entscheidungen für Paket 4 (2026-08-27):**
- **MS50 Band 30 muss ALLE Basic-Calls enthalten** (76 minus 4 Plus-Wanderer) + MS-Ergänzung.
  Sonst zeigt „nur MS 2026" fast nichts (Sequenzen nutzen Basic-Calls).
- **Forward and Back** (`call_forward_and_back`) → Band 30, direkt nach Circle:
  `teaching_order = 30.000150` (renummeriert nichts).
- **Merge `call_trade` → `call_named_dancers_trade`** (generische Basic-„Trade" = MS50-„Trade").
- **Merge `call_walk_around_the_corner` → `call_walk_around`** (verallgemeinerte Figur).
  Merges betreffen `call_text_mappings` (umhängen) + `call_programs` (vereinen) + Identität löschen.

**Paket 4 — Daten/Referenz: ✅ gebaut & auf echter Datenkopie validiert (2026-08-27), noch NICHT in App/DB.**
- `installer/reference_gen.py` erzeugt `installer/reference_calls.json` (762 call_programs,
  13 dance_programs, 2 Merges). Bänder: 10/20 (Basic), 29/30/39/40/49/50 (neu/umgebaut,
  inkl. Forward and Back @30.000150), 60–90 unverändert übernommen.
- Auf Kopie angewandt (Merges + call_programs ersetzt) → Filter liefert real:
  MS 2026 **3.238**, Plus 2026 6.801, A1 2026 8.016; alt-Programme 3.996/6.658/8.007.
  MS 2026 < Mainstream alt = korrekter Reduktions-Effekt.
- **Offen:** Reseed in die echte DB gehört in Paket 5 (mit Pflicht-Backup + `user_version`).

**Paket 5 — Reseed-Routine: ✅ gebaut & getestet (2026-08-27), Auto-Start noch NICHT aktiv.**
- `reseed_reference_data()` in `song_db.py`: Pflicht-Backup → Merges → call_programs ersetzen →
  Builtin-`dance_programs` neu (origin builtin/user) → Lokationen auf 2026-Set migrieren →
  `app_meta`-Version. Idempotent (einmal pro `REFERENCE_DATA_VERSION`).
- `reference_calls.json` liegt in `src/` (lädt zur Laufzeit) und `installer/` (Quelle).
- Getestet auf Kopie: 13 Programme, Lokation Mainstream → 2026 {30} = 3238 Sequenzen, Backup ok.
- **Offen:** Auto-Aufruf in `__init__` (erst aktivieren, wenn UI steht); für EXE-Build muss
  `reference_calls.json` mitgebündelt werden (spec ergänzen). Class-Programm-Varianten
  entfallen im Reseed (nur 13 Basis-Programme) — bei Bedarf später ergänzen.

**Filter-Verdrahtung (DB-seitig): ✅** `bands_filter` in `_build_sequence_where` +
`get_filtered_sequences/count/sequence_ids`; identische Zahlen wie Direktmethode, kombinierbar
mit Typ/Tag/Contains.

**UI-Integration: ✅ implementiert (2026-08-27), noch nicht im App-Lauf verifiziert.**
1. **Sequenz-View**: `_program_bands` + `set_program_bands()`; `_load_sequences` und die
   Navigations-`get_filtered_sequence_ids` übergeben `bands_filter`. Hauptfenster
   `_location_bands(location)` + Push in `_set_current_location`. Altes Limit-Auto-Sync in
   `_on_dance_program_changed` entfernt (sonst Doppel-/Stale-Filter).
2. **Lokations-Editor** `_LocationSettingsDialog`: Mehrfachauswahl über neue
   `_MultiProgramPickerDialog` (Checkbox-Liste); lädt/speichert `location_programs`
   (`get_location_program_ids`/`set_location_program_ids`). Neuer i18n-Key `loc_settings_multi_hint`.
3. **Auto-Reseed** in `SongDatabase.__init__` aktiv (`reseed_reference_data()`), einmalig
   pro Version, mit Pflicht-Backup.

**Fix-Runde 1 (nach 1. App-Test, 2026-08-27) — Referenz v2:**
- **"Only"** aufs Band-Modell verdrahtet: `bands_below_filter` (id NOT IN Containment der
  Bänder ohne das oberste) in `_build_sequence_where` + `_get_bands_below()` in der
  Sequenz-View; im Band-Modus ersetzt es den alten `max_teaching_order`-`min_to`.
  Validiert: {30,40} gesamt 6801 = Only 3563 + nur-{30} 3238.
- **Player-Programm-Button** (`_on_program_btn_clicked`) öffnet jetzt `_MultiProgramPickerDialog`
  für die aktuelle Lokation, speichert `location_programs`, zieht Filter neu (Player-Callback
  `on_programs_changed`). Player merkt sich Lokation (`set_location` → `self._location`).
  Neuer i18n-Key `dance_need_location`.
- **Programm-Trenner** (`separator_<band>`, "-- Label --" bei band.999999) wieder in
  `reference_calls.json`; Reseed hält Namen aktuell (UPSERT). `REFERENCE_DATA_VERSION=2`
  → Bestands-DBs reseeden erneut.

**Class-Programme (2026-08-28, Referenz v3):** Entscheidung mit David — die „X Class"-Programme
(Mainstream (Class) … Challenge 3A (Class)) BLEIBEN (Hintergrund: Class-Tanzrunden dauern oft
länger; Ziel-Dauer bleibt aber überall 7 min, der Caller passt selbst an). Sie **nutzen dieselben
Calls wie die 2026er Liste** → Class-Band = Band des 2026-/Basis-Programms (MS Class=30, PL Class=40,
A1 Class=50; A2+ = Basis-Band). Ursache des vorherigen Flimmerns: `_insert_default_dance_programs`
(kennt die Classes) läuft VOR dem Reseed (der sie nur beim ersten Mal löschte). Fix: Classes sind
jetzt in `reference_calls.json` + Reseed (`is_class`-Flag). Neue **strukturierte Reihenfolge** (je
Familie alt→2026→Class), `sort_order` 10..200. Class-Programme sind aus `band_to_pid` der
Lokations-Migration ausgeschlossen (Band 30 → MS2026, nicht MS Class). Lokations-Migration jetzt
**einmalig** (Flag `app_meta.ms50_locations_migrated`), damit Referenz-Bumps manuelle Lokations-
Programme nicht zurücksetzen. `REFERENCE_DATA_VERSION` **2→3** (`song_db.py` + `reference_gen.py`).
`reference_calls.json` neu generiert (call_programs bit-identisch zu v2, nur dance_programs 13→20 +
Version); in `src/` + `installer/`. Reseed v2→v3 auf echter DB-Kopie getestet (20 Programme, Backup,
Flag gesetzt, idempotent). Fallbacks `_fallback/song_db.py.bak_ms50_classes_20260828`,
`installer/*.bak_*_20260828`. NOCH NICHT neu gebaut.

**Performance-Überarbeitung Sequenz-Filter (2026-08-28):** Der teure Containment-Join
(`sequence_calls` × mappings × `call_programs`, GROUP BY/HAVING) lief pro Programmwechsel
3–6× (count/page/detail, ×2 bei Only). Gemessen (Desktop, echtes Widget): ~430 ms normal,
~850 ms Only+Detail; GUI-Aufbau selbst billig (Tabelle 1 ms, Contains-Combo 3 ms). Fix in
`song_db.py`: `_cover_ids(bänder)` cacht die tanzbare ID-Menge je Band-Menge (frozenset),
`_ensure_band_scope` materialisiert sie in TEMP `seq_scope`; `_build_sequence_where` referenziert
nur noch `id IN (SELECT id FROM seq_scope)`. Auto-Invalidierung per SQLite-Triggern auf
sequences/sequence_calls/call_text_mappings/call_programs (`_band_cache_ver`) — kein Writer
kann vergessen werden. Ergebnis: erster Programm-Aufruf ~137 ms (1 Durchlauf), danach warm
**3–9 ms** (count 2/page 0/ids 2). Korrektheit streng gegen rohe Referenz geprüft (alle
Band-Mengen, Alt-Listen, Only, Type-Kombi identisch). Perf-Messpunkte bleiben drin
(`SeqFilter.*`, zero-overhead wenn `debug/performance_logging` aus). Backup
`_fallback/song_db.py.bak_bandcache_20260828`.

**Filter-Listen an Bänder + Limit-Filter (2026-08-28):** Contains-/Limit-Listen zeigen nur
Figuren der gewählten Bänder (Mehrfach-Figur im niedrigsten gewählten Band), Neuaufbau bei
Programmwechsel (`_calls_for_current_bands`, `_rebuild_limit_items`). Limit-**Filter** über
die Cover-Logik statt kaputtem `max_teaching_order`: Der Limit-Eintrag liefert eine **feine
Teaching-Order-Obergrenze** `cover_max_to`, die in `_cover_ids` als Zusatzbedingung
(`cp.teaching_order <= cover_max_to`) INNERHALB der gewählten Bänder greift — so schließt
"Limit = Spin Chain Thru" die im selben Band später gelehrten Figuren (Recycle) korrekt aus.
(Frühere Band-Reduktion `_effective_bands` war zu grob und wieder entfernt; Fix nach Davids
68-Sequenzen-Bug.) Cache-Key = (Band-Menge, cover_max_to). "Only" bezieht sich auf die volle
Auswahl. Filter-Ableitung zentralisiert in `_current_filter_args` (Tabelle/Zähler/Detail aus
einer Quelle). Verifiziert (Davids Szenario = 0, Ground-Truth exakt). Backup
`_fallback/main.py.bak_bandlists_20260828`. NICHT neu gebaut.

**Vor Abnahme im App-Lauf prüfen / bekannte Punkte:**
- Der **Player-Schnellbutton** (btn_program) setzt weiterhin nur EIN Programm (für
  Ziel-Dauer etc.) und steuert den Sequenz-Filter NICHT mehr — der läuft über die
  Lokations-Programmauswahl. Ggf. später anpassen.
- ~~**Class-Programmvarianten** entfallen (nur 13 Basis-Programme).~~ ÜBERHOLT (2026-08-28):
  Class-Programme bleiben (Referenz v3, 20 Programme) — siehe Abschnitt „Class-Programme" oben.
- **EXE-Build**: ✅ `reference_calls.json` in `installer/callers_caddy.spec` als `datas`-Eintrag
  (Ziel `.`) aufgenommen (2026-08-28). Reseed findet die Datei im Bundle über
  `os.path.dirname(__file__)` == `_internal/`.
- Bestandsnutzer landen per Reseed auf 2026 (Default); Zurückstellen auf alt = im
  Lokations-Editor die alten Programme (Basic 1/2 + Mainstream + Plus + A1) anhaken.

## Quell-Listen (schrittweise Einspielung)

> **Slot-Konvention (wichtig):** Das ALTE Schema nummeriert durchgehend — Basic 1 =
> Positionen (Slots) 1–32, Basic 2 = 33–48, altes Mainstream = ab 49. Das MS50-Band 30
> hat dagegen eine **eigene, frisch vergebene** Slot-Nummerierung (1–50). Die Slots im
> `teaching_order`-Nachkomma der Bänder 10/20 entsprechen bereits 1:1 David's
> Positionsnummern.

### Basic 1 (alt) — Band `10` — bereits korrekt in DB

Positionen 1–32; in der DB als `10.00SSxx` (SS = Slot). Vollständig vorhanden, kein
Handlungsbedarf. Familien mit Sub-Positionen: 5 Promenade (a–d), 8 Right&Left Grand (a–c),
11 Half Sashay (a–c), 12 Turn Back (a–b), 13 Separate (a–b), 16 Ladies Chain (a–c),
18 Lead R/L, 19 Veer L/R, 21 Circulate (a–e), 26 First/Next, 30 Square Thru / Left.

### Basic 2 (alt) — Band `20` — bereits korrekt in DB

Positionen 33–48; in der DB als `20.00SSxx`. Vollständig vorhanden. Familien:
33 Wheel Around / Reverse, 35 Trade (a–c), 36 Ocean Wave (Step to a Wave / Balance),
38 Swing Thru / Left, 39 Run / Cross Run, 44 Flutterwheel / Reverse.

**Re-Teach-Positionen (eigene Figuren, behalten ihre Familien-Nummer):** Die eckigen
`[…]`-Einträge sind KEINE Erinnerungen, sondern eigenständige Figuren, die an einer
späteren Teaching-Position **erneut** auftauchen. Sie behalten dabei ihre interne
Nummer (Sub-Buchstabe = Sub-Ziffer, a=1/b=2/c=3 …):

| Re-Teach an Position | interne Nr. | Figur | entity_id | DB-Slot |
|---|---|---|---|---|
| nach 19 (Part 1) | 16.3 | Chain Down the Line | `call_chain_down_the_line` | 10.001603 |
| nach 34 (Part 2) | 8.3 | Wrong Way Grand | `call_wrong_way_grand` | 10.000803 |
| nach 36 | 21.3 | All Eight Circulate | `call_all_eight_circulate` | 10.002103 |
| nach 47 | 21.4 | Single File Circulate | `call_single_file_circulate` | 10.002104 |
| nach 47 | 21.5 | Split/Box Circulate | `call_split_circulate` | 10.002105 |

Die interne Nummer entspricht bereits 1:1 dem `teaching_order`-Nachkomma des DB-Eintrags.
**Offen:** ob die Wieder-Auftritte als zusätzliche Teaching-Order-Zeile materialisiert
werden (das neue Mehrfach-Zeilen-Schema aus Paket 1 würde das erlauben) oder nur in der
Anzeige-Reihenfolge erscheinen.

### Mainstream (alt) — Band `29` — Positionen ab 49

> Die 19 MS-Calls folgen den 48 Basic-Positionen → **Slots 49–67** (David's Liste 1–19
> + Offset 48). Provisorische `teaching_order` = `29.00SSxx`. Alle Calls existieren
> bereits als `entity_id`; nur eine zusätzliche Zeile im Band 29 nötig.
> „DB-Band jetzt" = wo der Call aktuell (halb-migriert) liegt.

| Slot | Call | entity_id | DB-Band jetzt |
|---|---|---|---|
| 49 | Cloverleaf | `call_cloverleaf` | 40 (Plus) |
| 50 | Turn Thru | `call_turn_thru` | 40 (Plus) |
| 51 | Eight Chain Thru | `call_eight_chain_thru` | 40 (Plus) |
| 52 | Pass to the Center | `call_pass_to_the_center` | 40 (Plus) |
| 53a | Allemande Thar | `call_allemande_thar` | 40 (Plus) |
| 53b | Allemande Left to an Allemande Thar | `call_allemande_left_to_allemande_thar` | 40 (Plus) |
| 53c | Wrong Way Thar | `call_wrong_way_thar` | 40 (Plus) |
| 54 | Slip the Clutch | `call_slip_the_clutch` | 40 (Plus) |
| 55 | Shoot the Star / Full Around | `call_shoot_the_star` | 40 (Plus) |
| 56a | Single Hinge | `call_single_hinge` | 30 (MS50) |
| 56b | Couples Hinge | `call_couples_hinge` | 30 (MS50) |
| 57 | Centers In | `call_centers_in` | 30 (MS50) |
| 58 | Cast Off 3/4 | `call_cast_off_three_quarters` | 30 (MS50) |
| 59 | Spin the Top | `call_spin_the_top` | 30 (MS50) |
| 60 | Walk and Dodge | `call_walk_and_dodge` | 40 (Plus) |
| 61 | Slide Thru | `call_slide_thru` | 30 (MS50) |
| 62a | Fold | `call_fold` | 30 (MS50) |
| 62b | Cross Fold | `call_cross_fold` | 30 (MS50) |
| 63 | Dixie Style to an Ocean Wave | `call_dixie_style_to_a_wave` | 40 (Plus) |
| 64 | Spin Chain Thru | `call_spin_chain_thru` | 40 (Plus) |
| 65a | Tag the Line (In/Out/Left/Right) | `call_tag_the_line` | 30 (MS50) |
| 65b | Fraction (1/4,1/2,3/4) Tag | `call_fraction_tag` | 30 (MS50) |
| 66 | Scoot Back | `call_scoot_back` | 30 (MS50) |
| 67 | Recycle (from a Wave only) | `call_recycle` | 30 (MS50) |

**Beobachtung:** Die 19 Alt-MS-Calls sind heute schon geteilt — 12 stehen in Band 30
(bleiben in MS50), die anderen in Band 40 (wandern nach Plus 2026 hoch). Die
Alt-Mainstream-Liste (Band 29) führt sie alle wieder zusammen.

### Mainstream (2026) / MS50 — Band `30` — 50 Positionen

> **MS50 absorbiert die Basics.** 90 Figuren (50 Positionen inkl. Sub-Familien), alle
> als `entity_id` vorhanden (0 fehlend). Aktuell stehen erst **20** in Band 30; die
> übrigen **70** müssen aus den Basic-Bändern (10/20) zusätzlich ins Band 30 ergänzt
> werden (Mehrfach-Zeile, Basic-Zeile bleibt fürs alte Schema erhalten).
> Status: `in 30` = schon da · `ADD aus X` = aus Band X ins Band 30 kopieren.

| Pos | Figur | entity_id | Status |
|---|---|---|---|
| 1a | Circle Left / Right | call_circle_left<br>call_circle_right | ADD aus 10 |
| 1b | Circle of 4 Left/Right | call_circle_of_4 | in 30 |
| 1c | Single Circle Left/Right | call_single_circle | in 30 |
| 2 | Dosado | call_dosado | ADD aus 10 |
| 3a | Couples Promenade | call_couples_promenade | ADD aus 10 |
| 3b | Single File Promenade | call_single_file_promenade | ADD aus 10 |
| 3c | Star Promenade | call_star_promenade | ADD aus 10 |
| 3d | Wrong Way Promenade | call_wrong_way_promenade | ADD aus 10 |
| 4a | Right/Left Arm Turn | call_arm_turns | ADD aus 10 |
| 4b | Allemande Left / Right | call_allemande_left<br>call_allemande_right | ADD aus 10/30 |
| 5 | Star Right / Left | call_right_hand_star<br>call_left_hand_star | ADD aus 10 |
| 6a | Right and Left Grand | call_right_and_left_grand | ADD aus 10 |
| 6b | Weave the Ring | call_weave_the_ring | ADD aus 10 |
| 6c | Wrong Way Grand | call_wrong_way_grand | ADD aus 10 |
| 7 | Pass Thru | call_pass_thru | ADD aus 10 |
| 8 | Wheel Around / Reverse | call_wheel_around<br>call_reverse_wheel_around | ADD aus 20 |
| 9 | Courtesy Turn | call_courtesy_turn | ADD aus 10 |
| 10 | Right and Left Thru | call_right_and_left_thru | ADD aus 10 |
| 11 | Swing | call_swing | ADD aus 10 |
| 12a | Ladies Chain (3/4) | call_two_ladies_chain | ADD aus 10 |
| 12b | Four Ladies Chain (3/4) | call_four_ladies_chain | ADD aus 10 |
| 12c | Chain Down the Line | call_chain_down_the_line | ADD aus 10 |
| 13a | Half Sashay | call_half_sashay | ADD aus 10 |
| 13b | Rollaway | call_rollaway | ADD aus 10 |
| 13c | Ladies In, Men Sashay | call_ladies_in_men_sashay | ADD aus 10 |
| 14a | U-Turn Back | call_u_turn_back | ADD aus 10 |
| 14b | Backtrack | call_backtrack | ADD aus 10 |
| 15a | Separate | call_separate | in 30 |
| 15b | Separate Around 1/2 to a Line | call_separate_around_to_a_line | ADD aus 10 |
| 15c | Separate Around 1/2 into middle | call_separate_around_come_into_middle | ADD aus 10 |
| 16 | Lead Right / Left | call_lead_right<br>call_lead_left | ADD aus 10 |
| 17 | Veer Left / Right | call_veer_left<br>call_veer_right | ADD aus 10 |
| 18 | Star Thru | call_star_thru | ADD aus 10 |
| 19a | Couples Circulate | call_couples_circulate | ADD aus 10 |
| 19b | (Named Dancers) Circulate | call_named_dancers_circulate | ADD aus 10 |
| 19c | All Eight Circulate | call_all_eight_circulate | ADD aus 10 |
| 19d | Single File (Column) Circulate | call_single_file_circulate | ADD aus 10 |
| 19e | Box / Split Circulate | call_split_circulate | ADD aus 10 |
| 20 | Bend the Line | call_bend_the_line | ADD aus 10 |
| 21 | Square Thru / Left Square Thru | call_square_thru<br>call_left_square_thru | ADD aus 10 |
| 22 | Split Two | call_split_two | ADD aus 10 |
| 23 | Grand Square | call_grand_square | ADD aus 10 |
| 24 | Double Pass Thru | call_double_pass_thru | ADD aus 10 |
| 25 | First Couple Go L/R, Next Go R/L | call_first_go_next_go | ADD aus 10 |
| 26 | Wheel and Deal | call_wheel_and_deal | ADD aus 20 |
| 27 | California Twirl | call_california_twirl | ADD aus 10 |
| 28 | Slide Thru | call_slide_thru | in 30 |
| 29 | Dive Thru | call_dive_thru | ADD aus 10 |
| 30 | Box the Gnat | call_box_the_gnat | ADD aus 20 |
| 31a | Alamo Style | call_alamo_style | ADD aus 20 |
| 31b | Balance | call_balance | ADD aus 20 |
| 31c | Step to a Wave | call_step_to_a_wave | ADD aus 20 |
| 31d | Dosado to a Wave | call_dosado_to_a_wave | ADD aus 10 |
| 31e | Single Circle to a Wave | call_single_circle_to_a_wave | in 30 |
| 32a | Couples Trade | call_couples_trade | ADD aus 20 |
| 32b | (Named Dancers) Trade | call_named_dancers_trade | in 30 |
| 32c | Right/Left Hand Trade | call_right_hand_trade<br>call_left_hand_trade | in 30 |
| 32d | Partner Trade | call_partner_trade | ADD aus 20 |
| 33 | Swing Thru / Left Swing Thru | call_swing_thru<br>call_left_swing_thru | ADD aus 20 |
| 34 | Run / Cross Run | call_run<br>call_cross_run | ADD aus 20 |
| 35 | Pass the Ocean | call_pass_the_ocean | ADD aus 20 |
| 36 | Extend | call_extend | ADD aus 20 |
| 37 | Flutterwheel / Reverse | call_flutterwheel<br>call_reverse_flutterwheel | ADD aus 20 |
| 38 | Sweep a Quarter | call_sweep_a_quarter | ADD aus 20 |
| 39 | Trade By | call_trade_by | ADD aus 20 |
| 40 | Ferris Wheel | call_ferris_wheel | ADD aus 20 |
| 41 | Zoom | call_zoom | ADD aus 20 |
| 42 | Touch a Quarter | call_touch_a_quarter | ADD aus 20 |
| 43a | Single Hinge | call_single_hinge | in 30 |
| 43b | Couples Hinge | call_couples_hinge | in 30 |
| 44 | Centers In | call_centers_in | in 30 |
| 45 | Cast Off Three-Quarters | call_cast_off_three_quarters | in 30 |
| 46 | Spin the Top | call_spin_the_top | in 30 |
| 47 | Scoot Back | call_scoot_back | in 30 |
| 48 | Fold / Cross Fold | call_fold<br>call_cross_fold | in 30 |
| 49a | Tag the Line | call_tag_the_line | in 30 |
| 49b | Fraction Tag | call_fraction_tag | in 30 |
| 50 | Recycle (from Waves only) | call_recycle | in 30 |

**Wichtig fürs Datenmodell:** Ein und dieselbe `entity_id` (z.B. `call_dosado`) steht nach
dem Umbau in Band 10 (Basic, altes Schema) **und** Band 30 (MS50, neues Schema) — genau
der Mehrfachnennungs-Fall aus Paket 1. Ohne Schema-Änderung (entity_id nicht mehr PK)
lässt sich MS50 nicht vollständig befüllen.

### Plus (alt) — Band `39` — 29 Positionen (aufbauen)

> Alle 29 als `entity_id` vorhanden (0 fehlend). **Band 39 ist noch leer** und muss aus
> diesen 29 Calls aufgebaut werden. „Status" = wo der Call heute liegt: 28 davon stehen
> im NEU-Band 40 (Plus 2026, das viele Alt-Plus-Calls behält), *Single Circle to a Wave*
> in Band 30 (MS50). Für Band 39 bekommt jeder eine eigene Zeile.

| Pos | Figur | entity_id | Status |
|---|---|---|---|
| 1 | Acey Deucey | call_acey_deucey | in 40 |
| 2 | Spin Chain the Gears | call_spin_chain_the_gears | in 40 |
| 3 | Grand Swing Thru | call_grand_swing_thru | in 40 |
| 4 | Triple Scoot | call_triple_scoot | in 40 |
| 5 | Teacup Chain | call_teacup_chain | in 40 |
| 6 | Ping Pong Circulate | call_ping_pong_circulate | in 40 |
| 7 | Load the Boat | call_load_the_boat | in 40 |
| 8 | Peel Off | call_peel_off | in 40 |
| 9 | Coordinate | call_coordinate | in 40 |
| 10 | (Anything) & Spread | concept_anything_and_spread | in 40 |
| 11 | Track 2 | call_track_2 | in 40 |
| 12 | (Anything) & Roll | concept_anything_and_roll | in 40 |
| 13 | Follow Your Neighbor | call_follow_your_neighbor | in 40 |
| 14 | Fan the Top | call_fan_the_top | in 40 |
| 15 | Dixie Grand | call_dixie_grand | in 40 |
| 16 | Spin Chain & Exchange the Gears | call_spin_chain_and_exchange_the_gears | in 40 |
| 17 | Explode the Wave | call_explode_the_wave | in 40 |
| 18 | Explode & (Anything) | concept_explode_and_anything | in 40 |
| 19 | Crossfire | call_crossfire | in 40 |
| 20 | Relay the Deucey | call_relay_the_deucey | in 40 |
| 21 | Linear Cycle | call_linear_cycle | in 40 |
| 22 | Peel the Top | call_peel_the_top | in 40 |
| 23 | Diamond Circulate | call_diamond_circulate | in 40 |
| 24 | Cut the Diamond | call_cut_the_diamond | in 40 |
| 25 | Single Circle to a Wave | call_single_circle_to_a_wave | ADD aus 30 |
| 26 | Trade the Wave | call_trade_the_wave | in 40 |
| 27 | Flip the Diamond | call_flip_the_diamond | in 40 |
| 28 | All 8 Spin the Top | call_all_8_spin_the_top | in 40 |
| 29 | Chase Right | call_chase_right | in 40 |

### Plus (2026) — Band `40` — 50 Positionen (schon da, 3 ergänzen)

> Alle Figuren als `entity_id` vorhanden (0 fehlend). **Band 40 IST bereits Plus 2026**
> (51 von 55 Figuren drin). Es fehlen nur **3 Basic-Calls** (See Saw, Circle to a Line,
> Do Paso), die aus MS50 herausgefallen sind (ADD aus 10). #11 Walk Around = `call_walk_around`
> (die verallgemeinerte Figur, liegt schon in 40) — NICHT `call_walk_around_the_corner`.
> Quarter-Thru-Familie ist Position 14 (a=1/4, b=3/4, c=Grand 1/4, d=Grand 3/4),
> im Teaching über die Liste verteilt. Thar-Familie = Position 26.

| Pos | Figur | entity_id | Status |
|---|---|---|---|
| 1 | Acey Deucey | call_acey_deucey | in 40 |
| 2 | Cloverleaf | call_cloverleaf | in 40 |
| 3 | Ping Pong Circulate | call_ping_pong_circulate | in 40 |
| 4 | Turn Thru | call_turn_thru | in 40 |
| 5 | Pass to the Center | call_pass_to_the_center | in 40 |
| 6 | Spin Chain Thru | call_spin_chain_thru | in 40 |
| 7 | Scoot & Dodge | call_scoot_and_dodge | in 40 |
| 8 | Pair Off | call_pair_off | in 40 |
| 9 | Teacup Chain | call_teacup_chain | in 40 |
| 10 | Dixie Style to an Ocean Wave | call_dixie_style_to_a_wave | in 40 |
| 11 | Walk Around (verallg. Corner/Partner) | call_walk_around | in 40 |
| 12 | See Saw | call_see_saw | ADD aus 10 |
| 13 | Load the Boat | call_load_the_boat | in 40 |
| 14a | 1/4 Thru | call_quarter_thru | in 40 |
| 15 | Walk & Dodge | call_walk_and_dodge | in 40 |
| 16 | Spin Chain the Gears | call_spin_chain_the_gears | in 40 |
| 17 | Grand Swing Thru | call_grand_swing_thru | in 40 |
| 14b | 3/4 Thru | call_three_quarter_thru | in 40 |
| 18 | Triple Scoot | call_triple_scoot | in 40 |
| 19 | Track 2 | call_track_2 | in 40 |
| 14c | Grand 1/4 Thru | call_grand_quarter_thru | in 40 |
| 14d | Grand 3/4 Thru | call_grand_three_quarter_thru | in 40 |
| 20 | (anything) & Roll | concept_anything_and_roll | in 40 |
| 21 | Diamond Circulate | call_diamond_circulate | in 40 |
| 22 | Pass the Sea | call_pass_the_sea | in 40 |
| 23 | Flip the Diamond | call_flip_the_diamond | in 40 |
| 24 | Follow Your Neighbor | call_follow_your_neighbor | in 40 |
| 25 | Cut the Diamond | call_cut_the_diamond | in 40 |
| 26a | Allemande Thar | call_allemande_thar | in 40 |
| 26b | Allemande Left to an Allemande Thar | call_allemande_left_to_allemande_thar | in 40 |
| 26c | Wrong Way Thar | call_wrong_way_thar | in 40 |
| 27 | Slip the Clutch | call_slip_the_clutch | in 40 |
| 28 | Triple Trade | call_triple_trade | in 40 |
| 29 | Shoot the Star / Full Around | call_shoot_the_star | in 40 |
| 30 | Peel Off | call_peel_off | in 40 |
| 31 | Coordinate | call_coordinate | in 40 |
| 32 | (anything) & Spread | concept_anything_and_spread | in 40 |
| 33 | Fan the Top | call_fan_the_top | in 40 |
| 34 | Relay the Deucey | call_relay_the_deucey | in 40 |
| 35 | Partner Tag | call_partner_tag | in 40 |
| 36 | Dixie Grand | call_dixie_grand | in 40 |
| 37 | Explode the Wave | call_explode_the_wave | in 40 |
| 38 | Crossfire | call_crossfire | in 40 |
| 39 | Explode & (anything) | concept_explode_and_anything | in 40 |
| 40 | Partner Hinge | call_partner_hinge | in 40 |
| 41 | Spin Chain & Exchange the Gears | call_spin_chain_and_exchange_the_gears | in 40 |
| 42 | Linear Cycle | call_linear_cycle | in 40 |
| 43 | Peel the Top | call_peel_the_top | in 40 |
| 44 | Circle to a Line | call_circle_to_a_line | ADD aus 10 |
| 45 | Chase Right | call_chase_right | in 40 |
| 46 | Clover and (anything) | concept_clover_and_anything | in 40 |
| 47 | Trade the Wave | call_trade_the_wave | in 40 |
| 48 | Eight Chain Thru | call_eight_chain_thru | in 40 |
| 49 | All 8 Spin the Top | call_all_8_spin_the_top | in 40 |
| 50 | Do Paso | call_do_paso | ADD aus 10 |

### A1 (alt) — Band `49` — aufbauen

> Alle Figuren als `entity_id` vorhanden (0 fehlend). **Band 49 ist noch leer.** Die
> 12 mit **→Plus** markierten Calls wandern nach Plus 2026 runter und liegen heute schon
> in Band 40; die übrigen liegen in Band 50 (= A1 2026). Reihenfolge = Davids Teaching Order.
> Re-Teach-Positionen (Turn and Deal / Cross Over Circulate ein zweites Mal) = dieselbe
> `entity_id`, zweiter Auftritt.

| Figur | entity_id | wandert? |
|---|---|---|
| Belles and Beaus | dancer_belle<br>dancer_beau | |
| Brace Thru | call_brace_thru | |
| Cross Trail Thru | call_cross_trail_thru | |
| Triple Trade | call_triple_trade | →Plus |
| Grand Follow Your Neighbor | call_grand_follow_your_neighbor | |
| Quarter Thru | call_quarter_thru | →Plus |
| Wheel Thru | call_wheel_thru | |
| Turn and Deal (two-faced lines / facing out) | call_turn_and_deal | |
| Pass In / Out | call_pass_in<br>call_pass_out | |
| Chain Reaction (1/4 tag only) | call_chain_reaction | |
| Mix | call_mix | |
| Lockit | call_lockit | |
| Right/Left Roll to a Wave | call_roll_to_a_wave | |
| Cast a Shadow | call_cast_a_shadow | |
| Six-Two Acey Deucey | call_six_two_acey_deucey | |
| Clover and (Anything) | concept_clover_and_anything | →Plus |
| Turn and Deal (ocean waves & other lines) | call_turn_and_deal | *(Re-Teach)* |
| Quarter In / Out | call_quarter_in<br>call_quarter_out | |
| Cross Over Circulate (two-faced lines) | call_cross_over_circulate | |
| Partner Tag | call_partner_tag | →Plus |
| Partner Hinge | call_partner_hinge | →Plus |
| Horseshoe Turn | call_horseshoe_turn | |
| Pass the Sea | call_pass_the_sea | →Plus |
| Split Square Thru | call_split_square_thru | |
| Step and Slide | call_step_and_slide | |
| Transfer the Column | call_transfer_the_column | |
| Cross Over Circulate (ocean waves & other lines) | call_cross_over_circulate | *(Re-Teach)* |
| Swap Around | call_swap_around | |
| Explode the Line | call_explode_the_line | |
| As Couples Concept | concept_as_couples | |
| Ends Bend | call_ends_bend | |
| Square Chain Thru | call_square_chain_thru | |
| Scoot and Dodge | call_scoot_and_dodge | →Plus |
| Double Star Thru | call_double_star_thru | |
| Left Wheel Thru | call_left_wheel_thru | |
| (Anything) and Cross | call_anything_and_cross | |
| (Named Dancers) Cross | call_named_dancers_cross | |
| Fractional Tops | call_fractional_tops | |
| Three-Quarter Thru | call_three_quarter_thru | →Plus |
| Triple Star Thru | call_triple_star_thru | |
| Cycle and Wheel | call_cycle_and_wheel | |
| Grand Quarter Thru | call_grand_quarter_thru | →Plus |
| Grand Three-Quarter Thru | call_grand_three_quarter_thru | →Plus |
| Explode and (Anything) | concept_explode_and_anything | →Plus |
| Pair Off | call_pair_off | →Plus |
| Reverse Swap Around | call_reverse_swap_around | |
| Cross Clover and (Anything) | call_cross_clover_and_anything | |
| Any Hand Concept | concept_any_hand | |
| Split Square Chain Thru | call_split_square_chain_thru | |
| Triple Cross / Double Cross | call_triple_cross<br>call_double_cross | |

### A1 (2026) — Band `50` — abgeleitet (schon da)

> **Keine eigene Quell-Liste** — A1 2026 = A1 alt **minus** die 12 →Plus-Wanderer.
> Band 50 enthält das bereits genau so (verifiziert). Die 12 entfernten Calls:
> Triple Trade, Quarter Thru, Clover and (Anything), Partner Tag, Partner Hinge,
> Pass the Sea, Scoot and Dodge, Three-Quarter Thru, Grand Quarter Thru,
> Grand Three-Quarter Thru, Explode and (Anything), Pair Off.
> **Offen:** sobald CALLERLAB eine offizielle A1-2026-Teaching-Order veröffentlicht,
> Reihenfolge gegenprüfen.

## Verteilung an Bestandsnutzer (Paket 5)

**Problem:** Referenzdaten (Calls, Programme, Referenz-Sequenzen) liegen in derselben
`callers_caddy.db` wie die Nutzerdaten. `_migrate()` bringt nur **Schema** zu Bestandsnutzern,
der Update-ZIP schließt die **DB** aus → geänderte Referenzdaten erreichen Altinstallationen
heute nicht.

**Termin:** Neues Programm gilt ab 01.09.2026 (in wenigen Tagen), mit Übergangsfrist.

**Vorschlag — versionierter Referenzdaten-Reseed beim Start (code-gebündelt):**
1. Referenzdaten als Datei **beim Code** bündeln (wie `reference_sequences.json`), z.B.
   `installer/reference_calls.json` (calls + call_programs + dance_programs). Reist im
   Update-ZIP mit, funktioniert offline.
2. `REFERENCE_DATA_VERSION` (Integer) im Code + gespeicherte Version in der DB
   (kleine `app_meta`-Tabelle).
3. Beim Start nach `_migrate()`: wenn Code-Version > DB-Version →
   - **ZUERST Pflicht-Backup** der DB (siehe unten).
   - Referenz-Only-Zeilen ersetzen: `calls`, `call_programs`, `dance_programs` (Builtin-Teil),
     Referenz-Sequenzen (`source='ceder'`).
   - **Nutzerdaten erhalten:** `call_text_mappings` mit `mapped_by='manual'`, eigene
     Sequenzen (`source!='ceder'`), Lokations-Identität.
   - Abgeleitetes neu berechnen (Sequenz-Level), Version hochsetzen.
4. Läuft genau einmal pro neuer Referenzversion; idempotent.

**Pflicht-Backup vor der Migration (entschieden):** Vor dem ersten Reseed/der Schema-
Migration eine Kopie der DB anlegen, z.B. `callers_caddy.db.bak_pre_ms50_<timestamp>`
im App-Verzeichnis (analog zur `_fallback`-Kultur des Projekts). Gibt dem Nutzer einen
Wiederherstellungspunkt, falls etwas schiefgeht. Muss VOR jeder schreibenden Aktion laufen.

**Entscheidungen:**
- **A) Kanal (akzeptiert):** Reine Code-Bündelung + Versionscheck (robust, offline) — der
  bestehende Online-Update liefert den neuen Code inkl. Referenzdatei wie gewohnt.
- **B) Nutzer-editierte `dance_programs` (akzeptiert):** Herkunfts-Flag
  `origin='builtin'|'user'`; nur Builtin wird reseedet, User-Programme bleiben erhalten.
- **C) Lokations-Programmwahl (ENTSCHIEDEN → Default NEU):** Alle Bestandsnutzer werden
  standardmäßig auf das **2026er-Programm** gestellt. Die **alten Listen bleiben wählbar**
  (Mehrfach-Programm-Auswahl aus Paket 2), sodass der Anwender **jederzeit selbst** auf die
  alte Liste zurückstellen kann. Kein Auto-Mapping auf alt nötig — Band 40/50 sind ja schon
  das Neue. Voraussetzung: die Rückstell-UI (Paket 2) muss klar und einfach bedienbar sein,
  BEVOR der Reseed ausgerollt wird.

## Offene Punkte

- Reihenfolge/SLOT-Nummern erst final, wenn Basics eingeordnet sind.
- Genaues Filter-Verhalten bei Mehrfach-Programmwahl (Vereinigungsmenge) in Paket 3.
- Migration: bestehende `locations.dance_program_id` → `location_programs` überführen.

## Verwandte Backlog-Einträge — Rule-Actions (David, 2026-08-28)

Neue Regel-Aktionen, die direkt auf diesem Umbau aufsetzen (Volltext in `backlog.md`):

- **BL-192 — Rule-Action „Setze Tanzprogramm" (Mehrfachauswahl).** Setzt das aktive
  Programm-Set per Regel. Dockt am **session-globalen** Programm-Modell an (siehe „DESIGN —
  Programmwahl ohne Lokation" unten): sollte über `_set_session_program_ids` /
  `_apply_program_setting` gehen, Mehrfachauswahl analog `_MultiProgramPickerDialog`,
  Persistenz INI-Key `sequences/dance_programs`. Bänder daraus via `_bands_for_program_ids`.
- **BL-193…BL-197 — Sequence-Filter-Actions** (Contains / Limit / Only / Difficulty / Tags).
  Setzen die Sequenz-Filter per Regel. Bauen auf der Filter-Mechanik aus Paket 3 +
  „Filter-Listen an Bänder + Limit-Filter" auf: Contains/Limit über die pro-Band gepflegten
  Listen (`_calls_for_current_bands`, `_rebuild_limit_items`, `cover_max_to`), Only über
  `bands_below_filter`, gemeinsame Ableitung in `_current_filter_args`. Interne Filter-/
  Rule-Namen bleiben englisch.

## Zu klären / Testen (nach 1. Fix-Runde, 2026-08-27)

- **DESIGN — Programmwahl ohne Lokation: ✅ ERLEDIGT (2026-08-28), noch nicht im App-Lauf getestet.**
  Tanzprogramm ist jetzt **session-global und von der Lokation entkoppelt**. Entscheidungen
  mit David: (1) Persistenz in der INI — Key `sequences/dance_programs` (Programm-IDs
  kommagetrennt), beim Start geladen. (2) Wählt man eine Lokation, **überschreibt** deren
  Programm-Set das Setting (Lokation „füttert" nur bei Auswahl). (3) Das **oberste** gewählte
  Programm (höchstes Band) liefert die Ziel-Tanzdauer.
  Umsetzung: `MainWindow._session_program_ids` + Helfer `_parse_program_ids`,
  `_bands_for_program_ids`, `_location_program_ids`, `_top_program`, `_apply_program_setting`,
  `_set_session_program_ids`, `_pick_session_programs`. Player-Button-Sperre („braucht
  Lokation") entfernt → Button ruft `on_pick_programs` (session-global). `_set_current_location`
  füttert das Setting aus der Lokation. Settings-Fenster: neuer Zeilentyp `program_picker` in
  `settings_dialog.py` (read-only Anzeige der Codes + Button, der den **bestehenden**
  `_MultiProgramPickerDialog` via Callback öffnet — kein Zirkelimport), i18n de/en/ja
  (`setting_label/tip_sequences_dance_programs`, `settings_program_pick_btn`).
  Beide Dateien py_compile-grün. Fallbacks: `_fallback/main.py.bak_ms50_session_programs_20260828`,
  `_fallback/settings_dialog.py.bak_ms50_session_programs_20260828`.
- **TEST — Upgrade über Bestandsinstallation:** David testet morgen den Reseed auf einer
  echten Altinstallation (nicht nur Dev-DB): Backup entsteht, Referenzdaten kommen an,
  Nutzerdaten/eigene Sequenzen/manuelle Mappings bleiben, Lokationen korrekt auf 2026,
  Trenner + Namen da. Auch: Update-ZIP muss `reference_calls.json` + neuen Code enthalten
  (EXE-Build: in PyInstaller-Spec aufnehmen).
