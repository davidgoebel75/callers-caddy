# Theming: Icons & Bilder

## Grundprinzip (ab P0.106)

**Es gibt ein einziges, gemeinsames Icon-Set für alle Themes.** Alle Grafiken
liegen genau einmal zentral in `src/images/` (vorher: pro Theme dupliziert).
Geometrie und Design werden zentral gepflegt — **die Farbe kommt ausschließlich aus
den Theme-Werten** in `skins/<theme>/skin.json`.

Damit:
- keine redundanten SVG-Kopien je Theme mehr,
- ein neues/geändertes Icon-Design wirkt sofort in allen Themes,
- Anwender gestalten ein Theme rein über Farbwerte (keine Bilddateien nötig).

## Farb-Keys (skin.json)

| Key | steuert |
|---|---|
| `icon_color` | Haupt-Iconfarbe — alle Icons auf farbiger Button-Fläche (Toolbar-Icons, check, Spinbox-/Combobox-Pfeile) |
| `title_icon` | Titelleisten-Icons (close, float) — sitzen auf `title_bg` |

Zwei Keys, weil Icons auf zwei Flächen sitzen: fast alles auf `button_bg`
(→ `icon_color`), nur die Titelleisten-Icons auf `title_bg` (→ `title_icon`).
Wichtig: Auch die Spinbox-/Combobox-Pfeile sitzen auf der farbigen Button-Fläche
(`QSpinBox::up-button`/`QComboBox::drop-down` = `button_bg`), daher `icon_color` —
nicht die Eingabefeld-Farbe.

## Semantische Akzentfarben

Farben mit fester Bedeutung bleiben literal in der SVG und werden vom Theme nicht
übersteuert: Highlight-Gelb `#fde047`, Text-Color-Rot `#ef4444`.

## Mechanik

`SkinManager._build_icon_cache()` ersetzt beim Theme-Laden die Platzhalter
(`{{icon_color}}`, `{{title_icon}}`, …) durch die Werte aus
`skin.json` und schreibt die eingefärbten SVGs in einen Temp-Cache.
- QSS referenziert sie über `url({{icon_path}}/<name>.svg)`.
- Code über `QIcon(f"{skin_mgr.icon_dir}/<name>.svg")`.

Der Cache wird bei jedem Laden neu erzeugt und nicht ausgeliefert. Praktische
Pflegehinweise direkt bei den Dateien: `src/images/README.md`.

## Build

`images/` wird wie `skins/` ausgeliefert (siehe `installer/callers_caddy.spec`
`datas` und `build.py` `move_to_root`) und landet neben der EXE.
