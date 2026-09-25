"""
Jump-Markers-Widget fuer Callers Caddy (BL-185, Teil 2).

Zeigt die Sprungziele des aktuellen Songs als gleichmaessig verteilte Buttons
mit dynamischem Zeilenumbruch (aehnlich dem Stream Deck). Immer dabei:
Start, Loop Start, Loop End, End. Dazu die vom Nutzer gesetzten Custom-Marker
(nach Zeit sortiert). Ein Klick springt an die jeweilige Position.

Datenquellen:
- Engine: loop_in_seconds / loop_out_seconds / get_original_duration()
- DB:     get_markers(song_id) fuer die Custom-Marker
Gesprungen wird ueber einen Callback ans Hauptfenster (dort mit Crossfade).
"""

from PySide6.QtWidgets import QWidget, QPushButton, QLabel
from PySide6.QtCore import Qt

from i18n import _t
from button_grid import compute_cells


def _fmt_time(s: float) -> str:
    """mm:ss (grob, fuer Fallback-Beschriftung)."""
    s = max(0.0, s)
    return f"{int(s) // 60:02d}:{int(s) % 60:02d}"


def _fmt_precise(s: float) -> str:
    """mm:ss.cs (fuer Tooltips)."""
    s = max(0.0, s)
    m = int(s) // 60
    sec = s - m * 60
    return f"{m:02d}:{sec:05.2f}"


class JumpMarkersWidget(QWidget):
    """Dock-Widget mit dynamisch angeordneten Sprungziel-Buttons."""

    _MARGIN = 8       # Rand um die Matrix
    _GAP = 6          # Abstand zwischen Buttons
    _MIN_W = 78       # Minimale Button-Breite (steuert die max. Spaltenzahl)
    _MIN_H = 30       # Minimale Button-Hoehe
    _MAX_H = 54       # Maximale Button-Hoehe (verhindert riesige Buttons bei wenigen)

    def __init__(self, engine, db, skin_mgr=None, jump_callback=None,
                 song_provider=None, parent=None,
                 perf_start=None, perf_log=None):
        super().__init__(parent)
        self._engine = engine
        self._db = db
        self._skin_mgr = skin_mgr
        self._jump_callback = jump_callback      # fn(time_seconds)
        self._song_provider = song_provider      # fn() -> Song|None
        # Perf-Instrumentierung per Callback hereingereicht (kein Zirkelimport von
        # main.py). No-ops, wenn nicht gesetzt oder Performance-Log deaktiviert.
        self._perf_start = perf_start or (lambda: 0)
        self._perf_log = perf_log or (lambda *a, **k: None)
        self._buttons: list[QPushButton] = []
        self.setMinimumSize(120, 90)

        self._empty_label = QLabel(_t("jumpmarkers_empty"), self)
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet("color: #888888;")
        self._empty_label.hide()

        self.refresh()

    # --- Skin ---

    def apply_skin(self, skin_mgr):
        self._skin_mgr = skin_mgr
        self.refresh()

    def _button_stylesheet(self) -> str:
        """Theme-konforme Button-Optik (wie Stream Deck: Icons/Text auf button_bg)."""
        if not self._skin_mgr:
            return ""
        c = self._skin_mgr.color
        bg = c("button_bg", "#615f8b")
        hover = c("button_hover", "#7a78a5")
        pressed = c("button_pressed", "#4e4c73")
        text = c("button_text", "#f7f7f7")
        border = c("border", "#555555")
        return (
            "QPushButton#jumpBtn {"
            f" background-color: {bg}; color: {text};"
            f" border: 1px solid {border}; border-radius: 8px;"
            " padding: 2px 6px; }"
            f"QPushButton#jumpBtn:hover {{ background-color: {hover}; }}"
            f"QPushButton#jumpBtn:pressed {{ background-color: {pressed}; }}"
        )

    # --- Aufbau ---

    def _collect_targets(self) -> list:
        """Liste der Sprungziele: (label, time_seconds, tooltip)."""
        song = self._song_provider() if self._song_provider else None
        dur = self._engine.get_original_duration() if self._engine else 0.0
        if not song or dur <= 0:
            return []
        loop_in = max(0.0, self._engine.loop_in_seconds or 0.0)
        loop_out = self._engine.loop_out_seconds or 0.0
        # "Loop gesetzt?" — gleiche Definition wie im Loop-Widget (Beat-Snap-
        # Freischaltung): Loop-In vom Anfang weg ODER Loop-Out vor dem Songende.
        # Start bleibt der einzige feste Button; Loop-Start/-Ende nur bei Loop,
        # ein "Ende"-Button ergibt keinen Sinn und entfaellt.
        has_loop = (loop_in > 0.1) or (0.0 < loop_out < dur - 0.5)

        targets = [(_t("jumpmarkers_start"), 0.0)]
        if has_loop:
            lo = loop_out if (0.0 < loop_out <= dur) else dur
            targets.append((_t("jumpmarkers_loop_start"), loop_in))
            targets.append((_t("jumpmarkers_loop_end"), lo))
        # Custom-Marker (nach Zeit sortiert) anhaengen
        try:
            for _idx, t, caption in self._db.get_markers(song.id):
                label = caption if caption else _fmt_time(t)
                targets.append((label, float(t)))
        except Exception:
            pass

        return [(label, t, self._tooltip(label, t)) for label, t in targets]

    @staticmethod
    def _tooltip(label: str, t: float) -> str:
        """intern#100: 'Label · mm:ss.cs', nur 'mm:ss.cs', wenn das Label bloss die
        gerundete Zeit ist (ungelabelt oder Vorbelegung aus 'Marker setzen').
        Frueher 'mm:ss — mm:ss.cs', das wie eine Zeitspanne aussah."""
        precise = _fmt_precise(t)
        if label.strip() in ("", _fmt_time(t)):
            return precise
        return f"{label} · {precise}"

    def refresh(self):
        """Sprungziele neu einlesen und Buttons aufbauen."""
        _t0 = self._perf_start()
        for btn in self._buttons:
            btn.deleteLater()
        self._buttons = []

        self.setStyleSheet(self._button_stylesheet())

        for label, t, tooltip in self._collect_targets():
            btn = QPushButton(label, self)
            btn.setObjectName("jumpBtn")
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setToolTip(tooltip)
            btn.clicked.connect(
                lambda checked=False, tt=t: self._on_clicked(tt))
            btn.show()
            self._buttons.append(btn)

        self._empty_label.setVisible(not self._buttons)
        self._perf_log(f"JumpMarkers Aufbau ({len(self._buttons)} Ziele)", _t0)
        self._relayout()

    def _on_clicked(self, time_seconds: float):
        if self._jump_callback:
            self._jump_callback(time_seconds)

    # --- Layout ---

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self):
        """Buttons gleichmaessig verteilt mit dynamischem Zeilenumbruch anordnen."""
        _t0 = self._perf_start()
        self._empty_label.setGeometry(self.rect())
        n = len(self._buttons)
        if n == 0:
            return

        # Geteilte Raster-Logik (button_grid) — dieselbe wie beim To-Call-Widget.
        cols, rows, cells = compute_cells(
            n, self.width(), self.height(),
            margin=self._MARGIN, gap=self._GAP,
            min_w=self._MIN_W, min_h=self._MIN_H, max_h=self._MAX_H)
        for btn, (x, y, w, h) in zip(self._buttons, cells):
            btn.setGeometry(x, y, w, h)

        self._perf_log(f"JumpMarkers Relayout ({n} Buttons, {cols}×{rows})", _t0)
