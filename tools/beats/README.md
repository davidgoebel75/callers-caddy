# Beats je Call (intern#164)

Pflegedatei im CC-Repo (seit 2026-11-23, vorher Branch `beats-callerlab` im intern-Repo). Sie wird **nicht** ausgeliefert: Ein Build-Werkzeug prüft sie und erzeugt daraus die Referenzdaten, die die App beim Start in die DB übernimmt. `zuordnung_vorschlag.py` hat die Spalten `entity_ids` und `standard` einmalig vorbelegt.

`callerlab_timing.csv` ist die **Quelle der Wahrheit** für die Beatzählung im Callers Caddy
(Entscheidung David, 2026-11-14). Wenn Caller die Werte kritisieren, verweisen wir auf CALLERLAB.
Calls, deren Dauer von der Position abhängt (vor allem Promenade), ergänzt die Choreo-Engine
Taminations (intern#163). Deren Mediane je Call dienen nur als Plausibilitätsprüfung.

Reprinted with permission of CALLERLAB.

## Quellen

| `quelle` | Dokument | Stand |
|---|---|---|
| `MS 2026-07-05` | Timing – CALLERLAB (New) Mainstream Program | revised 2026-07-05, effective 2026-09-01 |
| `Plus 2026-07-05` | Timing – The CALLERLAB (New) Plus Program | revised 2026-07-05, effective 2026-09-01 |
| `A1 2025-06-12`, `A2 2025-06-12` | Timing – The CALLERLAB Advanced 1 / Advanced 2 Program | revised 2025-06-12 |
| `abgeleitet` | aus den Charts zusammengesetzt (Promenade Home, Swing and Promenade) | |

Regeln aus „Additional Details for Square Dance Definitions“ (CALLERLAB, Oktober 2025, S. 66–67, 89).
Die PDFs liegen lokal unter `E:\SquareDance\CallerLab\` (nicht im Repo). Challenge-Programme (C1 ff.)
fehlen noch.

## Spalten

| Spalte | Inhalt |
|---|---|
| `entity_ids` | App-Calls der Zeile (`calls.entity_id`). `a\|b` = einer davon, `a+b` = beide zusammen in einer Kartenzeile (Konzept + Call, z. B. All 4 Couples Pass Thru) |
| `standard` | `1` = Standard-Variante des Calls. Gilt ohne Square Flow, wenn der Kartentext die Variante nicht verrät. Genau eine je Call und Chart |
| `variante_regel` | Englische Kürzel, mit Komma getrennt: `number=N`, `odd`, `even`, `fraction=1/4\|1/2\|3/4\|full`, `ss`, `home`, `parts`, `minus_pass_thru`. Bedeutung und Auswahl in `src/caddy/beats/variant_rules.py`; Unbekanntes wird abgewiesen |
| `pruefen` | Grund für eine Prüfung durch David. Leer = geprüft. Das Build-Werkzeug nimmt die Tabelle nur an, wenn die Spalte überall leer ist |
| `programm` | Chart, aus der die Zeile stammt (MS, Plus, A1, A2). Manche Calls stehen in mehreren Charts. |
| `call` | Name wie in der Chart |
| `variante` | Bedingung der Chart, z. B. `FC`, `SS Heads or Sides`, `3/4 around`, `Line of Eight` |
| `typ` | `fest`, `bereich` (`beats` bis `beats_bis`), `call_plus` (Call + `beats`), `plus_call` (`beats` + Call), `max` (größer von `beats` und Call), `not_timed`, `dynamisch` (hängt von Position/Weg ab; `beats` = Mindest- bzw. Nennwert) |
| `beats`, `beats_bis` | Wert bzw. Bereich |
| `anything_ab` | Beat, auf dem der eingesetzte Call beginnt (Transfer and Anything: 5) |
| `quelle` | siehe oben |
| `bemerkung` | Wortlaut der Chart bei Sonderfällen, parallele Teile (`parallel: …`), Versionshinweise |

`;`-getrennt, UTF-8, in Excel bearbeitbar.

## Build: CSV → `src/callerlab_timing.json`

Nach jeder Änderung an der CSV:

```
python tools/beats/build_callerlab_timing.py
```

Das Werkzeug prüft streng und schreibt nur, wenn alles stimmt; sonst listet es alle Fehler mit
Zeilennummer (wie in Excel) auf. Geprüft werden: Spaltenkopf, `programm`, `typ`, `quelle`,
ganze Zahlen in `beats`/`beats_bis`/`anything_ab` passend zum `typ`, Kürzel in `variante_regel`,
jede Kennung in `entity_ids` gegen `src/reference_calls.json`, genau ein `standard` je App-Call
und Chart, keine doppelte Zeile und eine leere Spalte `pruefen`.

Das JSON trägt dieselben Spalten (ohne `pruefen`) als Text, eine Zeile je Datensatz, und eine
`version` = Inhalts-Hash der Zeilen. Die App befüllt die DB neu, sobald sich die Version ändert;
Hochzählen von Hand entfällt. `--check` meldet nur, ob das JSON zur CSV passt;
`tests/beats/test_build_timing.py` prüft dasselbe. Die Build-Spec (`installer/callers_caddy.spec`)
legt das JSON neben `reference_calls.json`.

## Regeln, die nicht in einzelnen Zeilen stehen

- **Timing ab Kontaktpunkt.** Schritte bis zum Kontaktpunkt kommen dazu. Aus dem Squared Set in die
  Mitte: **2 Beats** (Additional Details S. 89; z. B. Pass Thru SS 4 statt 2).
- **Parallele Teile:** Bewegen sich Gruppen gleichzeitig (Dive Thru, Pass to the Center, Spin Chain Thru),
  zählt die längere Bewegung.
- **Supercalls** (Explode and, Clover and, Cross Clover and, Transfer and, Chain Reaction But, Mini Busy But
  …) haben eine eigene Bewegung, die parallel oder versetzt zum eingesetzten Call läuft (S. 67).
- **Not Timed:** Any Hand, As Couples. In der Summe kennzeichnen („≥ 58 + ?“), nicht weglassen.
- **64-Beat-Figuren:** Die Summe ist ein Richtwert. CALLERLAB verlangt Zuschläge für Übergänge und
  Square Breathing; „only dancing a sequence with the music determines if the timing works“ (S. 89).
  Beat Math (Baker/Marriner 2009): rechnerisch 64 wurden in 60–61 getanzt. Prüfung gegen 64 deshalb
  mit Toleranz.
- **Versionsstand beachten:** Clover / Cross Clover and Anything war 2022 noch 4 + Call bzw. 10 + Call,
  seit 2025 das Maximum.

## Gegenprobe gegen Taminations

`gegenprobe_taminations.py` vergleicht die Chart mit den Taminations-Medianen eines Messlaufs aus
intern#163. Stand 2026-11-14 (Annahmen-Runde 5, `gegenprobe_taminations_2026-11-14.txt`):
126 Calls verglichen, 83 im Bereich der Chart, 31 bis 1 Beat daneben, 10 bis 2, 2 mehr
(Cross Run: Taminations 3, Chart 6). Taminations zählt nach Animation (z. B. Heads Square Thru 4 = 12
= Chart 10 + 2 aus dem Squared Set) und schwankt im Einzelfall stark; nur der Median ist brauchbar.
