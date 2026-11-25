# Zentrale Icons / Bilder

**Ein einziges Icon-Set für ALLE Themes.** Jede Grafik liegt genau **einmal** hier
(nicht mehr pro Theme dupliziert). Geometrie/Design wird hier zentral gepflegt;
die **Farbe kommt ausschließlich aus dem Theme** (`skins/<theme>/skin.json`).

## Farb-Platzhalter

Die SVGs enthalten keine festen Iconfarben, sondern Platzhalter, die beim Laden
eines Themes durch die Theme-Werte ersetzt werden:

| Platzhalter | Bedeutung | Icons |
|---|---|---|
| `{{icon_color}}` | Haupt-Iconfarbe — alle Icons auf farbiger Button-Fläche | zoom-in/out, gear, pencil, save, bold, italic, underline, arrow-up/down (Spinbox/Combobox sitzen auf `button_bg`) + neutrale Teile von highlight/text-color |
| `{{button_text}}` | Schriftfarbe der Buttons — Haken der Checkbox (sitzt auf `indicator_check`, wie Text auf einem Button) | check |
| `{{title_icon}}` | Titelleisten-Icons (auf `title_bg`) | close, float |

Fast alle Icons sitzen auf `button_bg` → `icon_color`. Die Titelleisten-Icons sitzen auf
`title_bg` → `title_icon`. Der Checkbox-Haken nimmt `button_text`, damit er wie
Button-Schrift lesbar ist (in Winter ist `icon_color` hell auf hellem Grund). (Die Spinbox-/Combobox-Pfeile
sitzen ebenfalls auf der farbigen Button-Fläche, daher `icon_color` — nicht die
Eingabefeld-Farbe.)

Grundsätzlich ist **jeder** Farb-Key aus `skin.json` als `{{key}}` nutzbar.

## Semantische Akzentfarben bleiben literal

Farben mit fester Bedeutung stehen direkt als Hex-Wert in der SVG und werden vom
Theme **nicht** übersteuert:

- `#fde047` (Gelb) — Highlight-Marker in `highlight.svg`
- `#ef4444` (Rot) — Linie in `text-color.svg`

## Wie es funktioniert (Mechanik)

`SkinManager._build_icon_cache()` (in `skin_manager.py`) ersetzt beim Theme-Laden
die Platzhalter mit den Werten aus `skin.json` und schreibt die fertigen SVGs in
einen Temp-Cache. Verwendung der eingefärbten Icons:

- **QSS:** `url({{icon_path}}/<name>.svg)` — `{{icon_path}}` zeigt auf den Cache.
- **Code:** `QIcon(f"{skin_mgr.icon_dir}/<name>.svg")`.

## Aufgaben

- **Iconfarbe eines Themes ändern:** nur `skin.json` anpassen
  (`icon_color`, `title_icon`) — keine SVG anfassen.
- **Neues Icon hinzufügen:** SVG hier ablegen, neutrale Farben als Platzhalter
  setzen, dann in QSS (`{{icon_path}}/…`) bzw. Code (`skin_mgr.icon_dir`) referenzieren.
- **Icon-Design ändern:** SVG hier bearbeiten — gilt automatisch für alle Themes.
