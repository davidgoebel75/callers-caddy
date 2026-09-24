"""
Skin-Manager fuer Callers Caddy
================================
Laedt Skins aus dem skins/ Ordner und wendet sie auf die QApplication an.

Ordnerstruktur:
  skins/
    default/
      skin.json     Farbdefinitionen als Variablen
      skin.qss      Qt StyleSheet mit {{platzhaltern}}
    mein_skin/
      skin.json
      skin.qss

Ablauf:
  1. skin.json laden → Farb-Dictionary
  2. skin.qss laden → Template-String
  3. Platzhalter {{key}} durch Farbwerte ersetzen
  4. Fertiges QSS auf QApplication.setStyleSheet() anwenden

Spaetere Erweiterungen (Backlog):
  - Skin-Auswahl-Dialog
  - Live-Wechsel zur Laufzeit
  - Skin-Preview
  - User-definierte Skins aus externem Ordner
"""

import os
import json
import re
import tempfile


class SkinManager:
    """Laedt und verwaltet Skins (Qt StyleSheets + Farbvariablen).

    Verwendung:
        skin_mgr = SkinManager(app_dir)
        skin_mgr.load("default")
        app.setStyleSheet(skin_mgr.get_stylesheet())

        # Einzelne Farbe abfragen (z.B. fuer dynamische Styles):
        warning_color = skin_mgr.color("warning")
    """

    def __init__(self, app_dir: str):
        """
        Args:
            app_dir: Verzeichnis in dem der skins/ Ordner liegt
                     (typischerweise das Verzeichnis von main.py)
        """
        self._app_dir = app_dir
        self._skins_dir = os.path.join(app_dir, "skins")
        # Zentraler Bilderordner: alle Icons liegen EINMAL hier als Template-SVGs
        # mit Farbplatzhaltern ({{icon_color}}, {{title_icon}}).
        # Die Einfaerbung kommt ausschliesslich aus den Theme-Werten (skin.json).
        self._images_dir = os.path.join(app_dir, "images")
        self._current_skin: str = ""
        self._colors: dict = {}
        self._font_size: str = "13px"
        self._skin_dir: str = ""
        self._icon_dir: str = ""   # Cache-Ordner mit eingefaerbten Icons des aktiven Themes
        self._stylesheet: str = ""

    @property
    def skins_dir(self) -> str:
        """Absoluter Pfad zum skins/ Ordner."""
        return self._skins_dir

    @property
    def current_skin(self) -> str:
        """Name des aktuell geladenen Skins."""
        return self._current_skin

    def list_skins(self) -> list:
        """Gibt alle verfuegbaren Skin-Namen zurueck.

        Ein gueltiger Skin ist ein Ordner in skins/ der
        mindestens eine skin.json enthaelt.
        """
        if not os.path.isdir(self._skins_dir):
            return []

        skins = []
        for name in sorted(os.listdir(self._skins_dir)):
            skin_dir = os.path.join(self._skins_dir, name)
            json_path = os.path.join(skin_dir, "skin.json")
            if os.path.isdir(skin_dir) and os.path.isfile(json_path):
                skins.append(name)
        return skins

    def load(self, skin_name: str) -> bool:
        """Laedt einen Skin und erstellt das fertige StyleSheet.

        Args:
            skin_name: Name des Skin-Ordners (z.B. "default")

        Returns:
            True bei Erfolg, False wenn Skin nicht gefunden.
        """
        skin_dir = os.path.join(self._skins_dir, skin_name)
        json_path = os.path.join(skin_dir, "skin.json")
        qss_path = os.path.join(skin_dir, "skin.qss")

        # JSON laden (Pflicht)
        if not os.path.isfile(json_path):
            print(f"[SkinManager] skin.json nicht gefunden: {json_path}")
            return False

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Basis = default-Skin: eigene Skins mit aelterer skin.json bekommen
            # neu eingefuehrte Schluessel von dort, statt dass {{key}} woertlich
            # im QSS stehen bleibt und Qt die Regel verwirft.
            base = self._load_default_data() if skin_name != "default" else {}
            skin_colors = data.get("colors", {})
            self._colors = {**base.get("colors", {}), **skin_colors}
            filled = sorted(set(self._colors) - set(skin_colors))
            if filled:
                print(f"[SkinManager] '{skin_name}': {len(filled)} Schluessel "
                      f"aus default ergaenzt: {', '.join(filled)}")
            self._font_size = data.get("font_size",
                                       base.get("font_size", "13px"))
            self._skin_dir = skin_dir
            print(f"[SkinManager] {len(self._colors)} Farbvariablen geladen "
                  f"aus '{skin_name}', font_size={self._font_size}")
        except (json.JSONDecodeError, OSError) as e:
            print(f"[SkinManager] Fehler beim Laden von skin.json: {e}")
            return False

        # Icon-Cache erzeugen: zentrale Template-SVGs aus images/ mit den
        # Theme-Farben einfaerben und in einen Cache-Ordner schreiben. Muss VOR
        # der QSS-Aufloesung laufen, damit {{icon_path}} verfuegbar ist.
        self._build_icon_cache()

        # QSS laden (optional — ohne QSS gibt es nur die Farbvariablen)
        if os.path.isfile(qss_path):
            try:
                with open(qss_path, "r", encoding="utf-8") as f:
                    template = f.read()
                self._stylesheet = self._resolve_placeholders(template)
                unresolved = sorted(set(re.findall(r"\{\{(\w+)\}\}",
                                                   self._stylesheet)))
                if unresolved:
                    print(f"[SkinManager] Unbekannte Platzhalter in skin.qss: "
                          f"{', '.join(unresolved)}")
                print(f"[SkinManager] StyleSheet geladen: "
                      f"{len(self._stylesheet)} Zeichen")
            except OSError as e:
                print(f"[SkinManager] Fehler beim Laden von skin.qss: {e}")
                self._stylesheet = ""
        else:
            self._stylesheet = ""
            print(f"[SkinManager] Kein skin.qss gefunden, "
                  f"nur Farbvariablen verfuegbar")

        self._current_skin = skin_name
        return True

    def _load_default_data(self) -> dict:
        """Liest skins/default/skin.json als Fallback-Basis (leer bei Fehler)."""
        path = os.path.join(self._skins_dir, "default", "skin.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[SkinManager] default/skin.json als Fallback nicht "
                  f"lesbar: {e}")
            return {}

    def _build_icon_cache(self):
        """Faerbt die zentralen Template-SVGs aus images/ mit den Theme-Farben ein.

        Alle Themes teilen sich EIN Icon-Set (images/). Pro geladenem Theme werden
        die Platzhalter ({{icon_color}}, {{title_icon}}, ...)
        durch die Werte aus skin.json ersetzt und die fertigen SVGs in einen
        Cache-Ordner geschrieben. Semantische Akzentfarben (z.B. Highlight-Gelb,
        Text-Color-Rot) stehen literal in den Templates und bleiben unveraendert.

        Der Cache liegt im Temp-Verzeichnis (nicht im Programm-/Quellordner), wird
        bei jedem Laden neu geschrieben und nicht ausgeliefert.
        """
        self._icon_dir = ""
        if not os.path.isdir(self._images_dir):
            print(f"[SkinManager] images/ nicht gefunden: {self._images_dir}")
            return
        cache_dir = os.path.join(tempfile.gettempdir(), "callers_caddy_icons")
        try:
            os.makedirs(cache_dir, exist_ok=True)
            count = 0
            for name in os.listdir(self._images_dir):
                if not name.lower().endswith(".svg"):
                    continue
                src = os.path.join(self._images_dir, name)
                try:
                    with open(src, "r", encoding="utf-8") as f:
                        svg = f.read()
                    svg = self._resolve_placeholders(svg)
                    with open(os.path.join(cache_dir, name), "w", encoding="utf-8") as f:
                        f.write(svg)
                    count += 1
                except OSError as e:
                    print(f"[SkinManager] Icon '{name}' uebersprungen: {e}")
            self._icon_dir = cache_dir
            print(f"[SkinManager] {count} Icons eingefaerbt -> {cache_dir}")
        except OSError as e:
            print(f"[SkinManager] Icon-Cache fehlgeschlagen: {e}")
            self._icon_dir = ""

    @property
    def icon_dir(self) -> str:
        """Cache-Ordner mit den eingefaerbten Icons des aktiven Themes.

        Code-seitig fuer QIcon(...) zu verwenden; in QSS via {{icon_path}}.
        """
        return self._icon_dir

    def image_names(self) -> list[str]:
        """Sortierte Liste der SVG-Dateinamen im images/-Ordner fuer die
        Icon-Auswahl (z.B. Stream Deck).

        Titelleisten-Icons (Platzhalter {{title_icon}}) werden ausgeschlossen:
        sie sind auf die Titelleisten-Farbe eingefaerbt (in hellen Themes fast
        schwarz) und wuerden auf einem farbigen Deck-Button falsch aussehen.
        """
        if not os.path.isdir(self._images_dir):
            return []
        names = []
        for n in os.listdir(self._images_dir):
            if not n.lower().endswith(".svg"):
                continue
            try:
                with open(os.path.join(self._images_dir, n),
                          "r", encoding="utf-8") as f:
                    if "{{title_icon}}" in f.read():
                        continue  # Titelleisten-Icon — nicht fuers Deck
            except OSError:
                continue
            names.append(n)
        names.sort(key=str.lower)
        return names

    def get_stylesheet(self) -> str:
        """Gibt das fertige StyleSheet zurueck (mit aufgeloesten Platzhaltern)."""
        return self._stylesheet

    def color(self, key: str, fallback: str = "#ff00ff") -> str:
        """Gibt eine einzelne Farbe zurueck.

        Nuetzlich fuer dynamische Styles die per Code gesetzt werden
        (z.B. Club-Button Warnzustand).

        Args:
            key: Farbname aus skin.json (z.B. "warning", "button_bg")
            fallback: Fallback-Farbe wenn key nicht gefunden (Magenta = auffaellig)

        Returns:
            Farbwert als Hex-String (z.B. "#ef4444")
        """
        return self._colors.get(key, fallback)

    def colors(self) -> dict:
        """Gibt das komplette Farb-Dictionary zurueck (Kopie)."""
        return dict(self._colors)

    @property
    def font_size(self) -> str:
        """Aktuelle Schriftgroesse (z.B. '13px')."""
        return self._font_size

    def _resolve_placeholders(self, template: str) -> str:
        """Ersetzt alle Platzhalter im Template.

        Aufgeloeste Platzhalter:
          {{key}}        — Farbwerte aus skin.json "colors"
          {{font_size}}  — Schriftgroesse aus skin.json "font_size"
          {{skin_path}}  — Absoluter Pfad zum Skin-Ordner (fuer Bilder)
        """
        result = template

        # Farben
        for key, value in self._colors.items():
            result = result.replace("{{" + key + "}}", value)

        # Schriftgroesse
        result = result.replace("{{font_size}}", self._font_size)

        # Skin-Pfad (Forward-Slashes fuer Qt QSS, auch auf Windows)
        skin_path = self._skin_dir.replace("\\", "/")
        result = result.replace("{{skin_path}}", skin_path)

        # Icon-Pfad: zentraler Cache mit eingefaerbten Icons (fuer QSS-url())
        icon_path = self._icon_dir.replace("\\", "/")
        result = result.replace("{{icon_path}}", icon_path)

        return result
