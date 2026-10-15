"""Loop-Finder-UI fuer Callers Caddy (BL-201, Stufe 9, aus main.py).

LoopFinderWidget (Loop-Suche/-Feinjustierung) samt Wellenform-Anzeige und
Hintergrund-Worker. Zirkelfrei: keine Rueckbezuege auf main.py.
"""

import os

import re

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QSpinBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QCursor, QValidator

import loop_windows as lw
from i18n import _t
from ui_helpers import fmt_time, SectionBarWidget


class _WindowSpinBox(QSpinBox):
    """Spinbox fuer eine Suchfenster-Grenze: Prozent oder Zeit (intern#207).

    Im Zeitmodus ist der Wert in ganzen Sekunden und wird als ``+m:ss``
    (Loop-In, ab Songbeginn) bzw. ``-m:ss`` (Loop-Out, vor Songende) gezeigt.
    Eingabe als ``m:ss`` oder als Sekunden, das Vorzeichen ist optional.
    """

    _TIME_MAX = 3600
    _SIGNS = "+-\u2212"
    _TIME_RE = re.compile(r"^\s*[+\-\u2212]?\s*\d{0,4}(:\d{0,2})?\s*$")

    def __init__(self, sign: str, parent=None):
        super().__init__(parent)
        self._sign = sign
        self._time_mode = False
        self.set_time_mode(False)

    def set_time_mode(self, on: bool):
        self._time_mode = bool(on)
        if self._time_mode:
            self.setRange(0, self._TIME_MAX)
            self.setSuffix("")
        else:
            self.setRange(0, 100)
            self.setSuffix(" %")
        self.lineEdit().setText(self.textFromValue(self.value()) + self.suffix())

    def textFromValue(self, value):
        if not self._time_mode:
            return super().textFromValue(value)
        return f"{self._sign}{value // 60}:{value % 60:02d}"

    def valueFromText(self, text):
        if not self._time_mode:
            return super().valueFromText(text)
        t = text.strip().lstrip(self._SIGNS).strip()
        try:
            if ":" in t:
                m, sec = t.split(":", 1)
                return int(m or 0) * 60 + int(sec or 0)
            return int(t or 0)
        except ValueError:
            return self.value()

    def validate(self, text, pos):
        if not self._time_mode:
            return super().validate(text, pos)
        if not self._TIME_RE.match(text):
            return QValidator.Invalid, text, pos
        t = text.strip().lstrip(self._SIGNS).strip()
        if not t or t.endswith(":"):
            return QValidator.Intermediate, text, pos
        if ":" in t and len(t.split(":", 1)[1]) != 2:
            return QValidator.Intermediate, text, pos
        if self.valueFromText(text) > self.maximum():
            return QValidator.Invalid, text, pos
        return QValidator.Acceptable, text, pos


class LoopFinderWaveform(QWidget):
    """Vereinfachte Song-Waveform mit zwei verschiebbaren Suchbereichen.

    Gruener Bereich = Loop-In-Suchbereich, Oranger Bereich = Loop-Out-Suchbereich.
    Jeder Bereich hat 2 Handles (links + rechts) zum Verschieben.
    Weisse Linien zeigen den aktuell selektierten Loop-In/Loop-Out Vorschlag.
    """

    regions_changed = Signal(float, float, float, float)
    _HANDLE_WIDTH = 10  # Pixel-Breite des Anfassers

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(60)
        self.setMaximumHeight(80)

        self._samples = None
        self._duration = 0.0

        # Suchbereiche (Sekunden)
        self._in_start = 0.0
        self._in_end = 0.0
        self._out_start = 0.0
        self._out_end = 0.0

        # Selektierter Vorschlag (weisse Marken)
        self._sel_loop_in = None   # Sekunden oder None
        self._sel_loop_out = None

        # Vorhandene Marken des Songs (schwarze Balken)
        self._existing_loop_in = None
        self._existing_loop_out = None

        # Drag-State: "in_start", "in_end", "out_start", "out_end" oder None
        self._dragging = None
        self.setMouseTracking(True)

        # Farben
        self._bg_color = QColor("#2b2b2b")
        self._wave_color = QColor("#615f8b")
        self._in_color = QColor(34, 197, 94, 50)
        self._out_color = QColor(249, 115, 22, 50)
        self._in_border = QColor(34, 197, 94, 200)
        self._out_border = QColor(249, 115, 22, 200)
        self._text_color = QColor("#f0f0f0")
        self._marker_color = QColor(255, 255, 255, 220)

    def set_colors(self, skin_mgr):
        colors = skin_mgr.colors()
        self._bg_color = QColor(colors.get("widget_bg", "#2b2b2b"))
        self._wave_color = QColor(colors.get("waveform", "#615f8b"))
        self._text_color = QColor(colors.get("text", "#f0f0f0"))
        self.update()

    def set_data(self, samples, sr, real_duration=None):
        """Song-Waveform setzen. real_duration = echte Songdauer in Sekunden."""
        self._samples = samples
        self._sr = sr
        # Echte Songdauer verwenden (nicht die aus Peaks errechnete)
        if real_duration is not None and real_duration > 0:
            self._duration = real_duration
        else:
            self._duration = len(samples) / sr if sr > 0 else 0.0
        self._in_start = 0.0
        self._in_end = self._duration * 0.25
        self._out_start = self._duration * 0.75
        self._out_end = self._duration
        self._sel_loop_in = None
        self._sel_loop_out = None
        self.update()

    def get_regions(self):
        return (self._in_start, self._in_end,
                self._out_start, self._out_end)

    def set_selected_loop(self, loop_in, loop_out):
        """Zeigt den selektierten Vorschlag als weisse Linien."""
        self._sel_loop_in = loop_in
        self._sel_loop_out = loop_out
        self.update()

    def clear_selection(self):
        self._sel_loop_in = None
        self._sel_loop_out = None
        self.update()

    def set_existing_marks(self, loop_in, loop_out):
        """Zeigt vorhandene Sprungmarken als schwarze Balken (None = keine)."""
        self._existing_loop_in = loop_in
        self._existing_loop_out = loop_out
        self.update()

    # --- Koordinaten ---

    def _sec_to_x(self, sec):
        if self._duration <= 0:
            return 0
        return int((sec / self._duration) * self.width())

    def _x_to_sec(self, x):
        if self.width() <= 0:
            return 0.0
        return max(0.0, min((x / self.width()) * self._duration, self._duration))

    # --- Handle-Erkennung (4 Handles) ---

    def _hit_test(self, x):
        hw = self._HANDLE_WIDTH // 2
        # Reihenfolge: innere Handles zuerst (hoehere Prioritaet)
        for name, sec in [("in_end", self._in_end),
                          ("out_start", self._out_start),
                          ("in_start", self._in_start),
                          ("out_end", self._out_end)]:
            hx = self._sec_to_x(sec)
            if hx - hw <= x <= hx + hw:
                return name
        return None

    # --- Maus-Events ---

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            handle = self._hit_test(int(event.position().x()))
            if handle:
                self._dragging = handle
                self.setCursor(QCursor(Qt.SizeHorCursor))
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        x = int(event.position().x())
        if self._dragging:
            sec = self._x_to_sec(x)
            min_w = self._duration * 0.03  # Mindestbreite 3%
            min_gap = self._duration * 0.05  # Mindestabstand zwischen Regionen

            if self._dragging == "in_start":
                sec = max(0.0, min(sec, self._in_end - min_w))
                self._in_start = sec
            elif self._dragging == "in_end":
                sec = max(self._in_start + min_w,
                          min(sec, self._out_start - min_gap))
                self._in_end = sec
            elif self._dragging == "out_start":
                sec = max(self._in_end + min_gap,
                          min(sec, self._out_end - min_w))
                self._out_start = sec
            elif self._dragging == "out_end":
                sec = max(self._out_start + min_w,
                          min(sec, self._duration))
                self._out_end = sec

            self.update()
            self.regions_changed.emit(self._in_start, self._in_end,
                                      self._out_start, self._out_end)
            event.accept()
            return

        # Hover-Cursor
        if self._hit_test(x):
            self.setCursor(QCursor(Qt.SizeHorCursor))
        else:
            self.setCursor(QCursor(Qt.ArrowCursor))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = None
            self.setCursor(QCursor(Qt.ArrowCursor))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # --- Paint ---

    def paintEvent(self, event):
        import numpy as np
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        mid_y = h // 2

        p.fillRect(0, 0, w, h, self._bg_color)

        # Waveform (vereinfacht, niedrige Aufloesung)
        if self._samples is not None and len(self._samples) > 0:
            samples = self._samples
            n = len(samples)
            pen = QPen(self._wave_color)
            pen.setWidth(1)
            p.setPen(pen)
            for px in range(w):
                s = int(px * n / w)
                e = min(int((px + 1) * n / w), n)
                if s >= e:
                    continue
                chunk = samples[s:e]
                mx = float(np.max(chunk))
                mn = float(np.min(chunk))
                top = mid_y - int(mx * mid_y * 0.85)
                bot = mid_y - int(mn * mid_y * 0.85)
                p.drawLine(px, top, px, bot)

        # Suchbereiche
        self._draw_region(p, h, self._in_start, self._in_end,
                          self._in_color, self._in_border, "Loop-In")
        self._draw_region(p, h, self._out_start, self._out_end,
                          self._out_color, self._out_border, "Loop-Out")

        # Handles an allen 4 Grenzen
        self._draw_handle(p, h, self._in_start, self._in_border)
        self._draw_handle(p, h, self._in_end, self._in_border)
        self._draw_handle(p, h, self._out_start, self._out_border)
        self._draw_handle(p, h, self._out_end, self._out_border)

        # Vorhandene Marken: schwarze Balken (wie ueberall in der App)
        if self._existing_loop_in is not None:
            self._draw_existing_marker(p, h, self._existing_loop_in)
        if self._existing_loop_out is not None:
            self._draw_existing_marker(p, h, self._existing_loop_out)

        # Selektierter Vorschlag: weisse Linien
        if self._sel_loop_in is not None:
            self._draw_marker(p, h, self._sel_loop_in, "IN")
        if self._sel_loop_out is not None:
            self._draw_marker(p, h, self._sel_loop_out, "OUT")

        p.end()

    def _draw_region(self, p, h, start_sec, end_sec, fill_color, border_color, label):
        x1 = self._sec_to_x(start_sec)
        x2 = self._sec_to_x(end_sec)
        if x2 <= x1:
            return
        p.fillRect(x1, 0, x2 - x1, h, fill_color)
        p.setPen(QPen(self._text_color))
        # Label mittig im Bereich
        text_x = x1 + (x2 - x1) // 2 - 20
        p.drawText(max(x1 + 2, text_x), 14, label)

    def _draw_handle(self, p, h, sec, color):
        x = self._sec_to_x(sec)
        # Dicke farbige Linie
        pen = QPen(color)
        pen.setWidth(3)
        p.setPen(pen)
        p.drawLine(x, 0, x, h)
        # Dreiecke oben und unten
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawPolygon([
            QPoint(x - 5, 0), QPoint(x + 5, 0), QPoint(x, 8)
        ])
        p.drawPolygon([
            QPoint(x - 5, h), QPoint(x + 5, h), QPoint(x, h - 8)
        ])

    def _draw_existing_marker(self, p, h, sec):
        """Schwarzer, durchgezogener Balken fuer eine vorhandene Sprungmarke."""
        x = self._sec_to_x(sec)
        pen = QPen(QColor(0, 0, 0, 230))
        pen.setWidth(3)
        pen.setStyle(Qt.SolidLine)
        p.setPen(pen)
        p.drawLine(x, 0, x, h)

    def _draw_marker(self, p, h, sec, label):
        """Weisse Linie fuer selektierten Loop-Punkt."""
        x = self._sec_to_x(sec)
        pen = QPen(self._marker_color)
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.drawLine(x, 0, x, h)
        # Label
        p.setPen(QPen(self._marker_color))
        p.drawText(x + 3, h - 4, label)


class LoopFinderWorker(QThread):
    """Worker-Thread fuer Loop-Analyse (blockiert UI nicht)."""
    # TIC-0029: 'done' statt 'finished' — sonst wird das eingebaute QThread.finished
    # (echtes Thread-Ende) ueberschattet und das Cleanup kann nicht sicher greifen.
    done = Signal(object)      # Liste von LoopCandidate
    error = Signal(str)

    def __init__(self, filepath: str, bpm: float = None,
                 compare_beats: int = 16,
                 in_start: float = None, in_end: float = None,
                 out_start: float = None, out_end: float = None):
        super().__init__()
        self._filepath = filepath
        self._bpm = bpm
        self._compare_beats = compare_beats
        self._in_start = in_start
        self._in_end = in_end
        self._out_start = out_start
        self._out_end = out_end

    def run(self):
        try:
            from loop_finder import find_loop_candidates
            candidates = find_loop_candidates(
                self._filepath, bpm=self._bpm,
                compare_beats=self._compare_beats,
                in_start=self._in_start, in_end=self._in_end,
                out_start=self._out_start, out_end=self._out_end
            )
            self.done.emit(candidates)
        except Exception as e:
            self.error.emit(str(e))


class LoopFinderWidget(QWidget):
    """Auto-Loop-Finder: Sucht gute Loop-Kandidaten und bietet sie zur Auswahl an."""

    # Callbacks (werden von MainWindow gesetzt)
    on_apply = None          # fn(loop_in, loop_out) — Loop uebernehmen
    on_audition = None       # fn(loop_in, loop_out) — Loop vorhoeren
    on_stop = None           # fn() — Wiedergabe stoppen
    on_window_mode_changed = None  # fn(mode) — Prozent/Zeit gewechselt (merken)

    # Namen der unveraenderbaren Built-in-Presets
    SINGING_PRESET_NAME = lw.SINGING_PRESET_NAME  # feste Prozentwerte (frueher "Standard")
    # Optimize-Stufen: Anzeigename -> +-Abstand in Prozent der Songdauer.
    # Dynamisch: Fenster = vorhandene Marken +-Abstand. >5% lohnt nicht
    # (dann lieber Singing nutzen), darum nur diese zwei Stufen.
    OPTIMIZE_PRESETS = {"Optimize 2%": 2, "Optimize 5%": 5}

    # Abwaertskompatibilitaet: alte Preset-Namen -> aktueller Name.
    # Rules, die noch auf "Standard" verweisen, laufen damit weiter.
    PRESET_ALIASES = lw.PRESET_ALIASES

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filepath = None
        self._bpm = None
        self._song_duration = 0.0
        self._candidates = []
        self._worker = None
        self._audition_timer = None  # Auto-Stop nach 2s
        self._waveform_loaded = False  # Lazy: erst bei Bedarf laden
        self._presets_dir = None      # wird von MainWindow gesetzt
        self._existing_loop_in = 0.0   # vorhandene Marken des aktuellen Songs (Sek.)
        self._existing_loop_out = 0.0
        self._window_mode = lw.MODE_PCT
        self._build_ui()

    def set_presets_dir(self, path: str):
        """Wird von MainWindow nach dem Init gesetzt."""
        self._presets_dir = path
        self._refresh_preset_combo()

    # ---- Preset-Verwaltung ----

    def _singing_preset(self) -> dict:
        """Gibt das unveraenderbare Singing-Preset (feste Prozentwerte) zurueck."""
        return lw.singing_preset()

    def _is_builtin_preset(self, name: str) -> bool:
        """True fuer geschuetzte Namen: Singing, Optimize-Stufen und alte Aliase.

        Aliase werden mitgeschuetzt, damit kein gespeichertes Preset den alten
        "Standard"-Namen ueberschattet und den Rule-Alias aushebelt.
        """
        return (name == self.SINGING_PRESET_NAME
                or name in self.OPTIMIZE_PRESETS
                or name in self.PRESET_ALIASES)

    def _has_existing_marks(self) -> bool:
        """True wenn der aktuelle Song bereits Sprungmarken hat."""
        return (self._existing_loop_out > self._existing_loop_in
                and self._existing_loop_out > 0)

    def _optimize_preset(self, margin: int) -> dict:
        """Berechnet ein Optimize-Preset dynamisch aus den vorhandenen Marken.

        Fenster = vorhandene Marke +-margin (Prozent der Songdauer).
        Fallback auf Singing-Werte, wenn keine Marken oder Dauer bekannt sind.
        """
        base = self._singing_preset()
        self._ensure_waveform()  # stellt _song_duration sicher
        dur = self._song_duration
        if dur <= 0 or not self._has_existing_marks():
            return base
        in_pct = self._existing_loop_in / dur * 100.0
        out_pct = self._existing_loop_out / dur * 100.0
        data = dict(base)
        data["in_start"] = int(max(0, round(in_pct - margin)))
        data["in_end"] = int(round(in_pct + margin))
        data["out_start"] = int(round(out_pct - margin))
        data["out_end"] = int(min(100, round(out_pct + margin)))
        return data

    @classmethod
    def list_preset_names(cls, presets_dir=None) -> list:
        """Gibt alle Preset-Namen zurueck (Built-ins zuerst, dann alphabetisch).

        Klassenmethode, damit der Rules-Editor die Preset-Combo auch dann
        befuellen kann, wenn der Loop-Finder-Dock noch nie geoeffnet wurde
        (Lazy-Init). EINE Quelle der Wahrheit — kein zweiter Enumerations-Pfad.
        """
        names = [cls.SINGING_PRESET_NAME] + list(cls.OPTIMIZE_PRESETS.keys())
        if presets_dir and os.path.isdir(presets_dir):
            builtin = ({cls.SINGING_PRESET_NAME}
                       | set(cls.OPTIMIZE_PRESETS) | set(cls.PRESET_ALIASES))
            for f in sorted(os.listdir(presets_dir)):
                if f.endswith(".json"):
                    name = f[:-5]
                    if name not in builtin:
                        names.append(name)
        return names

    def _list_preset_names(self) -> list:
        return self.list_preset_names(self._presets_dir)

    def _load_preset(self, name: str) -> dict:
        """Laedt ein Preset per Name. Built-in-Presets kommen aus dem Code.

        Alte Namen (z.B. "Standard") werden vorab auf den aktuellen Namen
        gemappt, damit bestehende Rules weiter funktionieren.
        """
        name = self.PRESET_ALIASES.get(name, name)
        if name in self.OPTIMIZE_PRESETS:
            return self._optimize_preset(self.OPTIMIZE_PRESETS[name])
        return lw.load_preset_file(name, self._presets_dir)

    def _save_preset(self, name: str, data: dict):
        """Speichert ein Preset als JSON-Datei. Built-in-Presets sind geschuetzt."""
        if self._is_builtin_preset(name) or not self._presets_dir:
            return False
        os.makedirs(self._presets_dir, exist_ok=True)
        path = os.path.join(self._presets_dir, f"{name}.json")
        try:
            import json as _json
            with open(path, "w", encoding="utf-8") as fh:
                _json.dump(data, fh, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    def _refresh_preset_combo(self):
        """Fueltt die Preset-ComboBox neu."""
        current = self._combo_preset.currentText()
        self._combo_preset.blockSignals(True)
        self._combo_preset.clear()
        for name in self._list_preset_names():
            self._combo_preset.addItem(name)
        idx = self._combo_preset.findText(current)
        self._combo_preset.setCurrentIndex(max(0, idx))
        self._combo_preset.blockSignals(False)
        self._update_optimize_enabled()
        # Laden-Button: Standard-Preset immer ladbar
        self._update_preset_buttons()

    def _update_optimize_enabled(self):
        """Graut die Optimize-Eintraege aus, solange der Song keine Marken hat."""
        enabled = self._has_existing_marks()
        switch_to_singing = False
        for opt_name in self.OPTIMIZE_PRESETS:
            idx = self._combo_preset.findText(opt_name)
            if idx < 0:
                continue
            item = self._combo_preset.model().item(idx)
            if item is not None:
                item.setEnabled(enabled)
                item.setToolTip("" if enabled
                                else _t("lf_preset_optimize_needs_marks"))
            # Falls eine Optimize-Stufe gerade gewaehlt, aber nicht erlaubt ist
            if not enabled and self._combo_preset.currentIndex() == idx:
                switch_to_singing = True
        if switch_to_singing:
            self._combo_preset.setCurrentIndex(
                self._combo_preset.findText(self.SINGING_PRESET_NAME))

    def _apply_preset_to_ui(self, data: dict):
        """Wendet Preset-Daten auf die Spinboxes, Compare-ComboBox und Strategie an.

        Der Modus des Presets (Prozent/Zeit) wird zuerst gesetzt, ohne
        Umrechnung, weil die Werte des Presets schon in diesem Modus sind.
        """
        self.set_window_mode(lw.preset_mode(data), convert=False)
        defaults = lw.default_values(self._window_mode)
        keys = ("in_start", "in_end", "out_start", "out_end")
        for spin, key, default in zip(self._window_spins(), keys, defaults):
            spin.blockSignals(True)
            spin.setValue(int(data.get(key, default)))
            spin.blockSignals(False)
        self._on_pct_changed()
        cb = int(data.get("compare_beats", 16))
        idx = self._combo_window.findData(cb)
        if idx >= 0:
            self._combo_window.setCurrentIndex(idx)
        strat = str(data.get("selection_strategy", "best_64"))
        idx2 = self._combo_strategy.findData(strat)
        if idx2 >= 0:
            self._combo_strategy.setCurrentIndex(idx2)

    def _current_settings_as_preset(self) -> dict:
        """Liest aktuelle UI-Einstellungen als Preset-Dict."""
        return {
            "mode": self._window_mode,
            "in_start": self._spin_in_start.value(),
            "in_end": self._spin_in_end.value(),
            "out_start": self._spin_out_start.value(),
            "out_end": self._spin_out_end.value(),
            "compare_beats": self._combo_window.currentData(),
            "selection_strategy": self._combo_strategy.currentData() or "best_64",
        }

    def _update_preset_buttons(self):
        """Speichern ist immer aktiv — bei Standard-Preset wird nach neuem Namen gefragt."""
        self._btn_preset_save.setEnabled(True)

    def _on_preset_load(self):
        name = self._combo_preset.currentText()
        data = self._load_preset(name)
        self._apply_preset_to_ui(data)

    def _on_preset_save(self):
        name = self._combo_preset.currentText()
        data = self._current_settings_as_preset()
        if self._is_builtin_preset(name):
            # Built-in (Singing/Optimize) ist unveraenderbar — als neues Preset speichern
            from PySide6.QtWidgets import QInputDialog
            new_name, ok = QInputDialog.getText(
                self, _t("lf_preset_save_title"), _t("lf_preset_save_prompt"), text="")
            if not ok or not new_name.strip():
                return
            new_name = new_name.strip()
            if self._is_builtin_preset(new_name):
                return
            if self._save_preset(new_name, data):
                self._refresh_preset_combo()
                self._combo_preset.setCurrentText(new_name)
            return
        # Bestehendes Preset ueberschreiben
        if self._save_preset(name, data):
            return
        # Name existiert noch nicht als Datei — nach neuem Namen fragen
        from PySide6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, _t("lf_preset_save_title"), _t("lf_preset_save_prompt"), text=name)
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()
        if self._is_builtin_preset(new_name):
            return
        if self._save_preset(new_name, data):
            self._refresh_preset_combo()
            self._combo_preset.setCurrentText(new_name)

    # Default-Bereiche fuer Singing Calls (Prozent)
    _DEFAULT_IN_START = lw.DEFAULT_IN_START
    _DEFAULT_IN_END = lw.DEFAULT_IN_END
    _DEFAULT_OUT_START = lw.DEFAULT_OUT_START
    _DEFAULT_OUT_END = lw.DEFAULT_OUT_END

    # ---- Prozent/Zeit (intern#207) ----

    def _window_spins(self):
        return (self._spin_in_start, self._spin_in_end,
                self._spin_out_start, self._spin_out_end)

    def window_mode(self) -> str:
        return self._window_mode

    def set_window_mode(self, mode: str, convert: bool = True):
        """Schaltet zwischen Prozent und Zeit um.

        convert=True rechnet die aktuellen Werte anhand der Dauer des
        geladenen Songs in den neuen Modus um. Ohne Umrechnung (oder ohne
        Song) gelten die Standardfenster des neuen Modus - Prozentwerte als
        Sekunden zu lesen ergaebe unsinnige Fenster (Review PR #132).
        """
        mode = mode if mode in lw.MODES else lw.MODE_PCT
        if mode == self._window_mode:
            return
        values = lw.default_values(mode)
        if convert:
            self._ensure_waveform()
            dur = self._song_duration
            if dur > 0:
                current = tuple(s.value() for s in self._window_spins())
                if mode == lw.MODE_TIME:
                    values = lw.pct_to_time(current, dur)
                else:
                    values = lw.time_to_pct(current, dur)
        self._window_mode = mode
        time_mode = mode == lw.MODE_TIME
        for spin, val in zip(self._window_spins(), values):
            spin.blockSignals(True)
            spin.set_time_mode(time_mode)
            spin.setValue(int(val))
            spin.blockSignals(False)
        self._update_window_tooltips()
        idx = self._combo_mode.findData(mode)
        if idx >= 0 and idx != self._combo_mode.currentIndex():
            self._combo_mode.blockSignals(True)
            self._combo_mode.setCurrentIndex(idx)
            self._combo_mode.blockSignals(False)
        self._on_pct_changed()
        if self.on_window_mode_changed:
            self.on_window_mode_changed(mode)

    def _on_mode_combo_changed(self, _idx):
        self.set_window_mode(self._combo_mode.currentData(), convert=True)

    def _update_window_tooltips(self):
        if self._window_mode == lw.MODE_TIME:
            tips = (_t("lf_tip_in_time"),) * 2 + (_t("lf_tip_out_time"),) * 2
        else:
            tips = ("Loop-In Start %", "Loop-In Ende %",
                    "Loop-Out Start %", "Loop-Out Ende %")
        for spin, tip in zip(self._window_spins(), tips):
            spin.setToolTip(tip)

    def _current_windows(self):
        """Absolute Suchfenster (Sekunden) aus den Feldern oder None."""
        return lw.resolve_windows(self._current_settings_as_preset(),
                                  self._song_duration)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)

        # Singing-Call-Segmentleiste (O, 1, 2, M, 3, 4, C)
        self._section_bar = SectionBarWidget()
        self._section_bar.setFixedHeight(28)
        layout.addWidget(self._section_bar)

        # Waveform mit Suchbereichen
        self._waveform = LoopFinderWaveform()
        self._waveform.regions_changed.connect(self._on_waveform_regions_changed)
        layout.addWidget(self._waveform)

        # Prozent-Felder unter Waveform: [In-Start] [In-End]  ....  [Out-Start] [Out-End]
        pct_layout = QHBoxLayout()
        pct_layout.setSpacing(4)
        pct_layout.setContentsMargins(0, 0, 0, 0)

        self._spin_in_start = _WindowSpinBox("+")
        self._spin_in_end = _WindowSpinBox("+")
        self._spin_out_start = _WindowSpinBox("\u2212")
        self._spin_out_end = _WindowSpinBox("\u2212")
        # Zeit-Labels (informatorisch, zeigen Spielzeiten fuer die 4 Prozentwerte)
        self._lbl_t_in_start = QLabel("–")
        self._lbl_t_in_end   = QLabel("–")
        self._lbl_t_out_start = QLabel("–")
        self._lbl_t_out_end  = QLabel("–")
        for spin, default, tooltip in [
            (self._spin_in_start, self._DEFAULT_IN_START, "Loop-In Start %"),
            (self._spin_in_end, self._DEFAULT_IN_END, "Loop-In Ende %"),
            (self._spin_out_start, self._DEFAULT_OUT_START, "Loop-Out Start %"),
            (self._spin_out_end, self._DEFAULT_OUT_END, "Loop-Out Ende %"),
        ]:
            spin.setValue(default)
            spin.setFixedWidth(90)
            spin.setToolTip(tooltip)
            spin.valueChanged.connect(self._on_pct_changed)
        for lbl in (self._lbl_t_in_start, self._lbl_t_in_end,
                    self._lbl_t_out_start, self._lbl_t_out_end):
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedWidth(90)
            f = lbl.font()
            f.setPointSizeF(max(7.0, f.pointSizeF() - 1))
            lbl.setFont(f)
            lbl.setStyleSheet("color: gray;")

        def _make_pct_col(spin, lbl):
            col = QVBoxLayout()
            col.setSpacing(2)
            col.setContentsMargins(0, 0, 0, 0)
            col.addWidget(spin)
            col.addWidget(lbl)
            return col

        # Einheitliche Hoehe fuer ComboBox + Buttons: gleich wie die SpinBox
        _row_h = self._spin_in_start.sizeHint().height()

        pct_layout.addLayout(_make_pct_col(self._spin_in_start, self._lbl_t_in_start))
        pct_layout.addLayout(_make_pct_col(self._spin_in_end, self._lbl_t_in_end))
        pct_layout.addStretch()
        # intern#207: Suchfenster in Prozent oder Zeit (+ab Beginn / -vor Ende)
        self._combo_mode = QComboBox()
        self._combo_mode.addItem("%", lw.MODE_PCT)
        self._combo_mode.addItem(_t("lf_mode_time"), lw.MODE_TIME)
        self._combo_mode.setToolTip(_t("lf_mode_tooltip"))
        self._combo_mode.setFixedHeight(_row_h)
        self._combo_mode.currentIndexChanged.connect(self._on_mode_combo_changed)
        pct_layout.addWidget(self._combo_mode, 0, Qt.AlignTop)
        self._combo_preset = QComboBox()
        self._combo_preset.setToolTip(_t("lf_preset_combo_tooltip"))
        self._combo_preset.setMinimumWidth(90)
        self._combo_preset.setFixedHeight(_row_h)
        self._combo_preset.currentIndexChanged.connect(self._update_preset_buttons)
        pct_layout.addWidget(self._combo_preset, 0, Qt.AlignTop)
        self._btn_preset_load = QPushButton(_t("lf_preset_load_btn"))
        self._btn_preset_load.setToolTip(_t("lf_preset_load_tooltip"))
        self._btn_preset_load.setFixedHeight(_row_h)
        self._btn_preset_load.setStyleSheet("padding: 0px 8px;")
        self._btn_preset_load.clicked.connect(self._on_preset_load)
        pct_layout.addWidget(self._btn_preset_load, 0, Qt.AlignTop)
        self._btn_preset_save = QPushButton(_t("lf_preset_save_btn"))
        self._btn_preset_save.setToolTip(_t("lf_preset_save_tooltip"))
        self._btn_preset_save.setFixedHeight(_row_h)
        self._btn_preset_save.setStyleSheet("padding: 0px 8px;")
        self._btn_preset_save.clicked.connect(self._on_preset_save)
        pct_layout.addWidget(self._btn_preset_save, 0, Qt.AlignTop)
        pct_layout.addStretch()
        pct_layout.addLayout(_make_pct_col(self._spin_out_start, self._lbl_t_out_start))
        pct_layout.addLayout(_make_pct_col(self._spin_out_end, self._lbl_t_out_end))
        layout.addLayout(pct_layout)
        # Preset-ComboBox initial befuellen (Standard zuerst)
        self._combo_preset.addItem(self.SINGING_PRESET_NAME)
        self._update_preset_buttons()

        # Obere Zeile: Analyse-Button + Vergleichsfenster + Status
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        self._btn_analyze = QPushButton(_t("lf_analyze"))
        self._btn_analyze.setEnabled(False)
        self._btn_analyze.clicked.connect(self._on_analyze)
        top_layout.addWidget(self._btn_analyze)

        self._combo_window = QComboBox()
        self._combo_window.setToolTip(_t("lf_window_tooltip"))
        for val in [4, 8, 16, 32, 64]:
            self._combo_window.addItem(f"{val} Beats", val)
        self._combo_window.setCurrentIndex(2)  # Default: 16
        self._combo_window.setFixedWidth(90)
        top_layout.addWidget(self._combo_window)

        from loop_finder import SELECTION_STRATEGIES
        self._combo_strategy = QComboBox()
        self._combo_strategy.setToolTip(_t("lf_strategy_tooltip"))
        for key, label in SELECTION_STRATEGIES.items():
            self._combo_strategy.addItem(_t(f"lf_strategy_{key}"), key)
        top_layout.addWidget(self._combo_strategy)

        self._lbl_status = QLabel(_t("lf_status_ready"))
        top_layout.addWidget(self._lbl_status, 1)
        layout.addLayout(top_layout)

        # Ergebnis-Tabelle (sortierbar per Klick auf Spaltenheader)
        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "#", _t("lf_col_score"), _t("lf_col_loop_in"),
            _t("lf_col_loop_out"), _t("lf_col_beat"), _t("lf_col_beats")
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 30)
        self._table.setSortingEnabled(True)
        self._table.doubleClicked.connect(self._on_audition_clicked)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table, 1)

        # Untere Zeile: Audition + Uebernehmen
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)

        self._btn_audition = QPushButton(_t("lf_audition"))
        self._btn_audition.setEnabled(False)
        self._btn_audition.clicked.connect(self._on_audition_clicked)
        bottom_layout.addWidget(self._btn_audition)

        self._btn_apply = QPushButton(_t("lf_apply"))
        self._btn_apply.setEnabled(False)
        self._btn_apply.clicked.connect(self._on_apply_clicked)
        self._btn_apply.setProperty("confirm", True)
        bottom_layout.addWidget(self._btn_apply)

        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)

    def set_song_info(self, filepath: str, bpm: float = None,
                      loop_in: float = 0.0, loop_out: float = 0.0):
        """Wird aufgerufen wenn ein neuer Song geladen wird.

        loop_in/loop_out: vorhandene Sprungmarken des Songs (Sekunden, 0 = keine).
        Sie werden als schwarze Balken in der Waveform gezeigt und sind die
        Basis fuer das Optimize-Preset.
        """
        self._filepath = filepath
        self._bpm = bpm
        self._existing_loop_in = float(loop_in or 0.0)
        self._existing_loop_out = float(loop_out or 0.0)
        self._candidates = []
        self._table.setRowCount(0)
        self._btn_analyze.setEnabled(filepath is not None)
        self._btn_audition.setEnabled(False)
        self._btn_apply.setEnabled(False)
        self._lbl_status.setText(_t("lf_status_ready"))
        self._stop_audition_timer()
        self._song_duration = 0.0
        self._waveform_loaded = False  # Lazy: erst bei Bedarf laden
        # Vorhandene Marken als schwarze Balken (immer sichtbar, wenn vorhanden)
        self._waveform.set_existing_marks(
            self._existing_loop_in if self._has_existing_marks() else None,
            self._existing_loop_out if self._has_existing_marks() else None)
        self._update_optimize_enabled()
        self._update_time_labels()

    def update_existing_marks(self, loop_in: float, loop_out: float):
        """Aktualisiert die vorhandenen Marken (schwarze Balken) ohne Neuladen.

        Wird nach dem Uebernehmen eines Loops aufgerufen, damit die schwarzen
        Balken auf die neuen Stellen springen und Optimize sich neu darauf bezieht.
        """
        self._existing_loop_in = float(loop_in or 0.0)
        self._existing_loop_out = float(loop_out or 0.0)
        self._waveform.set_existing_marks(
            self._existing_loop_in if self._has_existing_marks() else None,
            self._existing_loop_out if self._has_existing_marks() else None)
        self._update_optimize_enabled()

    def _ensure_waveform(self):
        """Laedt Waveform-Daten bei Bedarf (Lazy Load)."""
        if self._waveform_loaded or not self._filepath:
            return
        self._waveform_loaded = True
        try:
            import numpy as np
            import soundfile as sf
            data, sr = sf.read(self._filepath, dtype='float32')
            if data.ndim > 1:
                mono = np.mean(data, axis=1)
            else:
                mono = data
            self._song_duration = len(mono) / sr
            target = 1000
            if len(mono) > target:
                step = len(mono) // target
                blocks = len(mono) // step
                trimmed = mono[:blocks * step].reshape(blocks, step)
                peaks = np.column_stack([trimmed.max(axis=1),
                                         trimmed.min(axis=1)]).flatten()
                self._waveform.set_data(peaks, sr // step * 2,
                                         real_duration=self._song_duration)
            else:
                self._waveform.set_data(mono, sr,
                                         real_duration=self._song_duration)
            self._apply_pct_to_waveform()
        except Exception:
            pass

    def _on_analyze(self):
        """Startet die Loop-Analyse in einem Worker-Thread."""
        if not self._filepath:
            return
        self._ensure_waveform()
        if self._current_windows() is None:
            # intern#207: Fenster passen nicht zur Songlaenge -> keine Analyse
            self._lbl_status.setText(_t("lf_status_windows_mismatch"))
            return

        self._btn_analyze.setEnabled(False)
        self._lbl_status.setText(_t("lf_status_analyzing"))
        self._table.setRowCount(0)

        compare = self._combo_window.currentData()
        in_start, in_end, out_start, out_end = self._waveform.get_regions()
        self._worker = LoopFinderWorker(
            self._filepath, bpm=self._bpm,
            compare_beats=compare,
            in_start=in_start, in_end=in_end,
            out_start=out_start, out_end=out_end
        )
        self._worker.done.connect(self._on_analysis_done)
        self._worker.error.connect(self._on_analysis_error)
        # TIC-0029: Referenz erst beim echten Thread-Ende freigeben.
        self._worker.finished.connect(self._release_worker)
        self._worker.start()

    def _release_worker(self):
        """Gibt den Loop-Analyse-Worker erst nach echtem Thread-Ende frei (TIC-0029)."""
        w = self._worker
        self._worker = None
        if w is not None:
            w.deleteLater()

    def _on_analysis_done(self, candidates):
        """Ergebnisse der Analyse anzeigen."""
        self._candidates = candidates
        self._btn_analyze.setEnabled(True)

        if not candidates:
            self._lbl_status.setText(_t("lf_status_no_results"))
            return

        self._lbl_status.setText(
            _t("lf_status_found", count=len(candidates))
        )

        # Sortierung kurz deaktivieren (sonst verschiebt Qt Zeilen
        # waehrend des Befuellens)
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._table.setRowCount(len(candidates))

        for i, c in enumerate(candidates):
            # Nr (Rang nach Score) — UserRole speichert Index fuer Zugriff
            item_nr = QTableWidgetItem()
            item_nr.setData(Qt.DisplayRole, i + 1)
            item_nr.setData(Qt.UserRole, i)  # Original-Index
            item_nr.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(i, 0, item_nr)

            # Score (Prozent, numerisch sortierbar)
            item_score = QTableWidgetItem()
            item_score.setData(Qt.DisplayRole, int(c.score * 100))
            item_score.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(i, 1, item_score)

            # Loop-In (sortierbar nach Sekunden)
            item_in = QTableWidgetItem(self._format_time(c.loop_in))
            item_in.setData(Qt.UserRole, c.loop_in)
            item_in.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(i, 2, item_in)

            # Loop-Out
            item_out = QTableWidgetItem(self._format_time(c.loop_out))
            item_out.setData(Qt.UserRole, c.loop_out)
            item_out.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(i, 3, item_out)

            # Beat-Position (1-8), Stern wenn Downbeat
            beat_text = str(c.beat_pos)
            if c.downbeat > 0 and c.beat_pos == c.downbeat:
                beat_text = f"{c.beat_pos} \u2605"
            item_beat = QTableWidgetItem()
            item_beat.setData(Qt.DisplayRole, c.beat_pos)
            item_beat.setText(beat_text)
            item_beat.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(i, 4, item_beat)

            # Beats (Gesamtlaenge) mit 64er-Vielfachen-Info
            beats_text = str(c.loop_beats)
            is_64_multiple = False
            if c.loop_beats > 0:
                # Groesste passende Zweierpotenz (4, 8, 16, 32, 64)
                for p in (64, 32, 16, 8, 4):
                    if c.loop_beats % p == 0:
                        n = c.loop_beats // p
                        beats_text = f"{c.loop_beats} ({n}×{p})"
                        if p == 64:
                            is_64_multiple = True
                        break
            if is_64_multiple:
                beats_text += " ★"
            item_beats = QTableWidgetItem()
            item_beats.setData(Qt.DisplayRole, c.loop_beats)
            item_beats.setText(beats_text)
            item_beats.setTextAlignment(Qt.AlignCenter)
            if is_64_multiple:
                item_beats.setForeground(QColor("#00CC00"))
            self._table.setItem(i, 5, item_beats)

        # Sortierung wieder aktivieren, initial nach Score absteigend
        self._table.setSortingEnabled(True)
        self._table.sortByColumn(1, Qt.DescendingOrder)
        self._table.selectRow(0)

    def _on_analysis_error(self, msg):
        """Fehler bei der Analyse."""
        # TIC-0029: Referenz-Freigabe via _release_worker am echten Thread-Ende.
        self._btn_analyze.setEnabled(True)
        self._lbl_status.setText(_t("lf_status_error", msg=msg))

    def _on_selection_changed(self):
        """Aktiviert/deaktiviert Buttons + aktualisiert Waveform-Marken."""
        has_sel = len(self._table.selectedItems()) > 0
        self._btn_audition.setEnabled(has_sel)
        self._btn_apply.setEnabled(has_sel)
        # Weisse Marken in der Waveform aktualisieren
        c = self._get_selected_candidate()
        if c:
            self._waveform.set_selected_loop(c.loop_in, c.loop_out)
        else:
            self._waveform.clear_selection()

    def _on_reset_pct(self):
        """Setzt die 4 Suchbereich-Felder auf Standardwerte zurueck."""
        for spin, default in [(self._spin_in_start, self._DEFAULT_IN_START),
                              (self._spin_in_end, self._DEFAULT_IN_END),
                              (self._spin_out_start, self._DEFAULT_OUT_START),
                              (self._spin_out_end, self._DEFAULT_OUT_END)]:
            spin.blockSignals(True)
            spin.setValue(default)
            spin.blockSignals(False)
        self._apply_pct_to_waveform()

    def _on_pct_changed(self):
        """SpinBox-Werte haben sich geaendert → Waveform-Regionen aktualisieren."""
        self._ensure_waveform()
        # Validierung: in_start < in_end < out_start < out_end
        s_is = self._spin_in_start
        s_ie = self._spin_in_end
        s_os = self._spin_out_start
        s_oe = self._spin_out_end
        if self._window_mode == lw.MODE_TIME:
            # Zeitmodus: Reihenfolge nur innerhalb eines Fensters (Loop-Out
            # zaehlt vor Ende, Start liegt also weiter davor). Ob die Fenster
            # zur Songlaenge passen, prueft _apply_pct_to_waveform.
            if s_ie.value() <= s_is.value():
                s_ie.blockSignals(True)
                s_ie.setValue(s_is.value() + 1)
                s_ie.blockSignals(False)
            if s_os.value() <= s_oe.value():
                s_os.blockSignals(True)
                s_os.setValue(s_oe.value() + 1)
                s_os.blockSignals(False)
            self._apply_pct_to_waveform()
            return
        # Mindestabstand 1%
        if s_ie.value() <= s_is.value():
            s_ie.blockSignals(True)
            s_ie.setValue(s_is.value() + 1)
            s_ie.blockSignals(False)
        if s_os.value() <= s_ie.value():
            s_os.blockSignals(True)
            s_os.setValue(s_ie.value() + 1)
            s_os.blockSignals(False)
        if s_oe.value() <= s_os.value():
            s_oe.blockSignals(True)
            s_oe.setValue(s_os.value() + 1)
            s_oe.blockSignals(False)
        self._apply_pct_to_waveform()

    def _on_waveform_regions_changed(self, in_start, in_end, out_start, out_end):
        """Waveform-Handles wurden per Maus verschoben → SpinBoxen aktualisieren."""
        dur = self._song_duration
        if dur <= 0:
            return
        if self._window_mode == lw.MODE_TIME:
            values = (in_start, in_end, dur - out_start, dur - out_end)
        else:
            values = tuple(v / dur * 100 for v in (in_start, in_end, out_start, out_end))
        for spin, val in zip(self._window_spins(), values):
            spin.blockSignals(True)
            spin.setValue(int(round(val)))
            spin.blockSignals(False)
        self._update_time_labels()

    def _apply_pct_to_waveform(self):
        """Uebertraegt die SpinBox-Werte (Prozent oder Zeit) auf die Waveform-Regionen."""
        dur = self._song_duration
        if dur <= 0:
            self._update_time_labels()
            return
        windows = self._current_windows()
        if windows is None:
            # Passt nicht zur Songlaenge: Waveform bleibt, Hinweis statt Analyse
            self._lbl_status.setText(_t("lf_status_windows_mismatch"))
            self._update_time_labels()
            return
        if self._lbl_status.text() == _t("lf_status_windows_mismatch"):
            self._lbl_status.setText(_t("lf_status_ready"))
        in_start, in_end, out_start, out_end = windows
        self._waveform._in_start = in_start
        self._waveform._in_end = in_end
        self._waveform._out_start = out_start
        self._waveform._out_end = out_end
        self._waveform.update()
        self._update_time_labels()

    def _update_time_labels(self):
        """Aktualisiert die Zeit-Labels unter den Prozent-Feldern."""
        dur = self._song_duration
        labels = (self._lbl_t_in_start, self._lbl_t_in_end,
                  self._lbl_t_out_start, self._lbl_t_out_end)
        values = [s.value() for s in self._window_spins()]
        # Beide Modi zeigen die absolute Songposition
        if not dur or dur <= 0:
            secs = [None] * 4
        elif self._window_mode == lw.MODE_TIME:
            secs = [values[0], values[1], dur - values[2], dur - values[3]]
        else:
            secs = [dur * v / 100.0 for v in values]
        for lbl, sec in zip(labels, secs):
            if sec is not None and 0 <= sec <= dur:
                lbl.setText(fmt_time(sec))
            else:
                lbl.setText("–")

    def _get_selected_candidate(self):
        """Gibt den aktuell ausgewaehlten Kandidaten zurueck."""
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        visual_row = rows[0].row()
        # Original-Index aus UserRole der ersten Spalte lesen
        # (Tabelle kann umsortiert sein)
        item = self._table.item(visual_row, 0)
        if not item:
            return None
        idx = item.data(Qt.UserRole)
        if idx is not None and 0 <= idx < len(self._candidates):
            return self._candidates[idx]
        return None

    def _on_audition_clicked(self):
        """Audition: 5s vor Loop-Out starten, nach Sprung 5s weiterlaufen, stoppen."""
        c = self._get_selected_candidate()
        if c and self.on_audition:
            self.on_audition(c.loop_in, c.loop_out)
            # Auto-Stop: 5s Vorlauf + 5s nach Sprung = 10s gesamt
            self._stop_audition_timer()
            self._audition_timer = QTimer()
            self._audition_timer.setSingleShot(True)
            self._audition_timer.timeout.connect(self._on_audition_stop)
            self._audition_timer.start(10000)

    def _on_audition_stop(self):
        """Stoppt die Audition-Wiedergabe."""
        if self.on_stop:
            self.on_stop()
        self._audition_timer = None

    def _stop_audition_timer(self):
        """Bricht laufenden Audition-Timer ab."""
        if self._audition_timer:
            self._audition_timer.stop()
            self._audition_timer = None

    def _on_apply_clicked(self):
        """Uebernimmt den ausgewaehlten Loop-Kandidaten."""
        c = self._get_selected_candidate()
        if c and self.on_apply:
            self._stop_audition_timer()
            self.on_apply(c.loop_in, c.loop_out)
            self._lbl_status.setText(
                _t("lf_status_applied",
                   loop_in=self._format_time(c.loop_in),
                   loop_out=self._format_time(c.loop_out))
            )

    def showEvent(self, event):
        """Lazy Load: Waveform erst laden wenn Widget sichtbar wird."""
        super().showEvent(event)
        self._ensure_waveform()

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Formatiert Sekunden als m:ss.s"""
        m = int(seconds) // 60
        s = seconds - m * 60
        return f"{m}:{s:04.1f}"
