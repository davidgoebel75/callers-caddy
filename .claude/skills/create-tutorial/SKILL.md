---
name: create-tutorial
description: Neues Tutorial-Video-Szenario anlegen - Thema und Umfang erfragen, die passenden Schritte im Code finden und abstimmen, scenarios/<name>/scenario.py schreiben, Drehbuch zeigen. Use when jemand ein Tutorial(-Video) anlegen, ein Szenario schreiben oder ein Feature im Video zeigen will.
---

# Tutorial anlegen

Ergebnis: ein drehfertiges Szenario `tools/tutorial_video/scenarios/<name>/scenario.py` und sein Drehbuch, vom Nutzer abgenommen. Gedreht wird nicht hier.

Fragen an den Nutzer **einzeln** stellen, nie als Fragenblock.

## Nachschlagen statt raten

- **Bedienung** (`point`, `click`, `double_click`, `context_menu`, `open_menu`, `type_text`, `keys`, `hide_dock`): Klasse `Stage` in `tools/tutorial_video/make_video.py`, je Methode der Docstring.
- **Schritt-Felder** (`say`, `point`, `do`, `hold`, `zoom`) und `SETUP`, `LAYOUT`, `SKIN`: Docstring von `scenarios/player/scenario.py`.
- **Vorbilder**: `scenarios/player/` (Song laden, abspielen), `scenarios/clock/` (Menue, Kontextmenue, Widget nicht registriert).

## 1. Basis

Der Branch enthaelt `tools/tutorial_video/make_video.py` mit `--drehbuch` (`python tools/tutorial_video/make_video.py selftest` gibt `ok`). Sonst den Nutzer fragen, auf welchem Branch das Szenario entstehen soll.

## 2. Thema

Fragen: Was soll das Video zeigen? **Fertig**, wenn ein Widget oder eine Funktion benannt ist, die es im Code gibt. `<name>` = englischer Begriff aus `GLOSSARY.md`, klein geschrieben (`clock`, `player`); den Namen bestaetigen lassen.

## 3. Umfang

Fragen, mit Faustregel ~15 s je Schritt:
- **kurz**: ~1 min, 4-7 Schritte, nur der Kernweg.
- **mittel**: ~2 min, 8-12 Schritte, Kernweg plus die wichtigsten Optionen.
- **ausfuehrlich**: 3-4 min, 13-18 Schritte, alle Optionen.

## 4. Analyse

Legwork im Code, bevor Schritte vorgeschlagen werden:

- **Widget-ID**: `register_widget(` in `src/main.py`. Fehlt das Widget dort, registriert es `SETUP` selbst (Muster: `scenarios/clock/`), und das gehoert als Befund in den Bericht.
- **Elemente**: Attribute der Widget-Klasse, die QWidgets sind (`self.btn_play = QPushButton(...)`). Pfad = `<id>.<attr>[.<attr>]`, wie in `src/tutorial_definitions.py`. Tabellenzeilen per `(pfad, zeile)`.
- **Fakten und Worte**: die bestehende Tour zum Widget in `src/tutorial_definitions.py` mit ihren Texten (`tutorial.<id>.*` in `src/translations.json`), die Beschriftungen und Tooltips der Elemente, der Abschnitt in `CHANGELOG.md`, wenn das Feature neu ist.
- **Menues**: Uebersetzungsschluessel der Eintraege (`_t("...")` in `addAction`/`QAction` des Widgets, Menueleiste in `src/main.py`) fuer `context_menu` und `open_menu`.
- **Ausgangslage**: INI-Optionen, die das Video umschaltet; `SETUP` setzt sie vorher auf einen festen Stand. Private Namen, die `SETUP` dabei benutzt, im Docstring nennen (Muster: `scenarios/clock/`).
- **Begriffe**: jedes Nomen der Sprechtexte steht in `GLOSSARY.md` als gewaehlter Begriff, de und `_EN_`.
- **Songs**: nur YRR-Songs (Open Source). Gebrauchte Songs im Docstring nennen.

**Fertig**, wenn jeder Kandidat-Schritt einen im Code gefundenen Elementpfad oder Menueschluessel hat und jede Bedienung eine `Stage`-Methode ist. Was sich nur mit App-Aenderung zeigen liesse, kommt als Befund in den Bericht, nicht ins Szenario.

## 5. Schritte abstimmen

Kandidaten als nummerierte Liste zeigen: je Schritt ein Satz Inhalt, Element, Bedienung; Kernweg zuerst, optionale Schritte markiert, Laenge passend zum Umfang aus Schritt 3. Der Nutzer waehlt, streicht, ordnet um. Wiederholen, bis er die Liste freigibt.

## 6. Szenario schreiben

`tools/tutorial_video/scenarios/<name>/scenario.py`:
- Docstring: Thema, verwendete Glossar-Begriffe, Voraussetzungen (Songs, Widgets), private Namen aus `SETUP`.
- `say` als dict mit `en` und `de` (`ja` nur auf Wunsch). Deutsch in Du-Form, Englisch mit _you_; kurze Saetze, ein Gedanke je Schritt. Der Satz kuendigt an, `do` fuehrt danach aus.
- Erster Schritt: worum es geht. Letzter Schritt: `zoom=None` und ein Satz Zusammenfassung.
- Elementpfade, die mehrfach vorkommen, als Konstanten oben (`CLOCK = "clock"`).

## 7. Pruefen

```bash
python tools/tutorial_video/make_video.py selftest
python tools/tutorial_video/make_video.py <name> --drehbuch
```

`selftest` gibt `ok`. Die Drehbuch-Tabelle vollstaendig im Chat zeigen. Der Nutzer liest Sprechtexte und Aktionen; Aenderungen einarbeiten und das Drehbuch neu zeigen, bis er es abnimmt.

## 8. Bericht

- Pfad des Szenarios, Zahl der Schritte, geschaetzte Laenge.
- Befunde aus Schritt 4 (nicht registriertes Widget, fehlende Elemente).
- Der Drehbefehl zum Selbststarten, weil die Aufnahme Maus und Bildschirm belegt:
  `python tools/tutorial_video/make_video.py <name> --app-dir <Testordner>` (`--size 1600x900` bei Bildschirmen mit 1920x1080).
