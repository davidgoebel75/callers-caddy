"""Pausen-Uhr fuer Callers Caddy: BreakWidget/BreakDisplay (BL-201, intern#220).

Zustand und Uebergaenge stehen ohne Qt in break_clock.py; das Widget misst die
Zeit, schickt Aktionen an reduce() und zeigt den Zustand an.
Zirkelfrei: keine Rueckbezuege auf main.py.
"""

import time

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QInputDialog,
)
from PySide6.QtCore import Qt, QTimer, Signal, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QCursor

from caddy.playback.break_clock import (
    BreakState, Pause, Reset, Restart, SetDuration, Start, Tick, reduce,
)
from i18n import _t


class BreakDisplay(QWidget):
    """Reine Anzeige: grosse Digital-Uhr (MM:SS) + Fortschrittsbalken darunter.

    Bekommt die Werte von aussen (remaining/total/finished) und malt sie mit
    Theme-Farben. Klick auf die Flaeche -> `clicked`-Signal (zum Zeit-Aendern).
    """
    clicked = Signal()

    def __init__(self, skin_mgr=None, parent=None):
        super().__init__(parent)
        self._skin_mgr = skin_mgr
        self._remaining = 0.0
        self._total = 0.0
        self._finished = False
        self.setMinimumSize(150, 80)
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def set_skin(self, skin_mgr):
        self._skin_mgr = skin_mgr
        self.update()

    def set_values(self, remaining, total, finished):
        self._remaining = max(0.0, remaining)
        self._total = max(0.0, total)
        self._finished = finished
        self.update()

    def _c(self, key, fallback):
        return QColor(self._skin_mgr.color(key, fallback) if self._skin_mgr else fallback)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        text = self._c("text", "#f0f0f0")
        accent = (self._c("warning", "#ef4444") if self._finished
                  else self._c("button_bg", "#3daee9"))
        track = self._c("slider_groove", "#404040")

        # Digital-Uhr (MM:SS)
        secs = int(round(self._remaining))
        clock = f"{secs // 60:02d}:{secs % 60:02d}"
        f = p.font()
        f.setPointSize(max(18, int(h * 0.42)))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QPen(accent if self._finished else text))
        p.drawText(QRect(0, 0, w, int(h * 0.70)), Qt.AlignCenter, clock)

        # Fortschrittsbalken = verstrichener Anteil der Pause
        bar_h = max(6, int(h * 0.13))
        bar_y = h - bar_h - 6
        bar_x = 8
        bar_w = w - 16
        if bar_w <= 0:
            p.end()
            return
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, bar_h / 2, bar_h / 2)
        frac = 0.0
        if self._total > 0:
            frac = min(1.0, max(0.0, (self._total - self._remaining) / self._total))
        if frac > 0:
            p.setBrush(accent)
            p.drawRoundedRect(bar_x, bar_y, int(bar_w * frac), bar_h,
                              bar_h / 2, bar_h / 2)
        p.end()




class BreakWidget(QWidget):
    """Pausen-Uhr fuer Tipp-Pausen: Countdown mit Digital-Anzeige + Balken.

    Angedockt; Klick auf die Uhr -> Dauer aendern. Optionaler Button spielt
    den zuletzt gespielten Song als Wartemusik (ohne Historie, Rules gesperrt).
    """
    DEFAULT_SECONDS = 300  # 5 Minuten (Fallback ohne Lokations-Vorgabe)

    # Callbacks (vom MainWindow gesetzt) — Wartemusik ohne Historie-Eintrag
    on_play_last_song = None   # fn(duration_seconds) -> bool (True = laeuft)
    on_stop_last_song = None   # fn()
    # intern#110: Pausen-Ereignisse fuer die Rules (Trigger break_started/-finished)
    on_break_started = None    # fn(with_music: bool) — nur bei frischem Start
    on_break_finished = None   # fn() — nur bei echtem Ablauf auf 0

    def __init__(self, skin_mgr=None, parent=None):
        super().__init__(parent)
        self._skin_mgr = skin_mgr
        self._state = BreakState(total=float(self.DEFAULT_SECONDS),
                                 remaining=float(self.DEFAULT_SECONDS))
        self._last_mono = None   # Zeitmessung fuer Tick, kein Zustand der Uhr
        self._music_playing = False

        self._timer = QTimer(self)
        self._timer.setInterval(200)  # 5x/s -> fluessiger Fortschrittsbalken
        self._timer.timeout.connect(self._tick)

        self._build_ui()
        self._refresh()

    # Mindestmasse, damit Elemente beim Verkleinern nicht ineinander rutschen
    _MIN_BTN_H = 28
    _MIN_DISPLAY_H = 64

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self._display = BreakDisplay(self._skin_mgr)
        self._display.setMinimumSize(140, self._MIN_DISPLAY_H)
        self._display.clicked.connect(self._edit_duration)
        lay.addWidget(self._display, 1)

        row = QHBoxLayout()
        row.setSpacing(4)
        self._btn_start = QPushButton(_t("break_start"))
        self._btn_start.clicked.connect(self._toggle_start)
        self._btn_reset = QPushButton(_t("break_reset"))
        self._btn_reset.clicked.connect(self._reset)
        for b in (self._btn_start, self._btn_reset):
            b.setMinimumHeight(self._MIN_BTN_H)
            row.addWidget(b)
        lay.addLayout(row)

        self._btn_play_last = QPushButton(_t("break_play_last"))
        self._btn_play_last.setMinimumHeight(self._MIN_BTN_H)
        self._btn_play_last.clicked.connect(self._toggle_play_last)
        lay.addWidget(self._btn_play_last)

        # Eigene Mindestgroesse aus den Kindern ableiten — verhindert, dass das
        # Dock die Elemente uebereinander schiebt. Wird nach _make_dock erneut
        # gesetzt (das _make_dock zwingt sonst 50x50 auf).
        self.setMinimumSize(self.minimumSizeHint())

    def enforce_min_size(self):
        """Mindestgroesse erneut setzen (nach _make_dock, das 50x50 erzwingt)."""
        self.setMinimumSize(self.minimumSizeHint())

    def apply_default_duration(self, seconds):
        """Setzt die Pausendauer (z.B. aus der Lokation) — wird beim Oeffnen
        des Break-Fensters aufgerufen. Aendert einen laufenden Countdown NICHT.
        """
        self._dispatch(SetDuration(seconds))

    # ---- Skin ----
    def set_skin(self, skin_mgr):
        self._skin_mgr = skin_mgr
        self._display.set_skin(skin_mgr)

    # ---- Reducer anbinden ----
    @property
    def state(self) -> BreakState:
        """Aktueller Zustand der Pausen-Uhr (nur lesen)."""
        return self._state

    def _dispatch(self, action):
        """Aktion an den Reducer, dann Timer, Anzeige und Callbacks nachziehen."""
        self._state, events = reduce(self._state, action)
        if not self._state.running:
            self._timer.stop()
        elif not self._timer.isActive():
            self._last_mono = None
            self._timer.start()
        self._refresh()
        for event in events:
            if event == "started" and callable(self.on_break_started):
                self.on_break_started(self._music_playing)
            elif event == "finished" and callable(self.on_break_finished):
                self.on_break_finished()

    def _refresh(self):
        s = self._state
        self._btn_start.setText(_t("break_pause") if s.running
                                else _t("break_start"))
        self._display.set_values(s.remaining, s.total, s.finished)

    def _tick(self):
        now = time.monotonic()
        last, self._last_mono = self._last_mono, now
        if last is not None:
            self._dispatch(Tick(now - last))

    # ---- Bedienung ----
    def _toggle_start(self):
        self._dispatch(Pause() if self._state.running else Start())

    def _reset(self):
        self._dispatch(Reset())

    def end_break(self) -> bool:
        """Laufende Pause von aussen beenden (intern#130: manuelles Play des
        Callers). Setzt den Countdown zurueck wie der Reset-Knopf und feuert
        bewusst KEIN on_break_finished (abgebrochen, nicht abgelaufen).
        False, wenn die Pausen-Uhr gar nicht lief."""
        if not self._state.running:
            return False
        self._dispatch(Reset())
        return True

    def _edit_duration(self):
        """Klick auf die Uhr: Countdown pausieren und Dauer neu setzen."""
        self._dispatch(Pause())
        cur = int(round(self._state.total))
        text, ok = QInputDialog.getText(
            self, _t("break_set_title"), _t("break_set_prompt"),
            text=f"{cur // 60:02d}:{cur % 60:02d}")
        if ok:
            self._dispatch(SetDuration(self._parse_duration(text)))

    @staticmethod
    def _parse_duration(text):
        """'MM:SS' -> Sekunden; reine Zahl -> Minuten. None bei Fehler."""
        text = (text or "").strip()
        if not text:
            return None
        try:
            if ":" in text:
                mm, ss = text.split(":", 1)
                return int(mm) * 60 + int(ss)
            return int(round(float(text.replace(",", ".")) * 60))
        except ValueError:
            return None

    # ---- Play last Song (Wartemusik, ohne Historie) ----
    def _toggle_play_last(self):
        if self._music_playing:
            if callable(self.on_stop_last_song):
                self.on_stop_last_song()
            self._music_playing = False
        elif callable(self.on_play_last_song):
            self._music_playing = bool(self.on_play_last_song(self._state.total))
            if self._music_playing:
                # Pausen-Uhr synchron mitlaufen lassen (frisch von total)
                self._dispatch(Restart())
        self._update_play_last_buttons()

    def set_music_stopped(self):
        """Vom MainWindow aufgerufen, wenn die Wartemusik (Auto-Stop) endet."""
        self._music_playing = False
        self._update_play_last_buttons()

    def _update_play_last_buttons(self):
        self._btn_play_last.setText(
            _t("break_play_last_stop") if self._music_playing
            else _t("break_play_last"))

    # ---- Programmatische Steuerung (Rule-Aktionen, BL-177) ----
    def start_break(self, duration_seconds=None):
        """Pause starten (Countdown). Optional mit vorgegebener Dauer.

        Fuer Rule-Aktion "Start Break". Startet den Countdown von vorn.
        """
        self._dispatch(Restart(duration_seconds))

    def start_break_with_last_song(self, duration_seconds=None):
        """Pause starten und den zuletzt gespielten Song als Wartemusik abspielen.

        Fuer Rule-Aktion "Start Break with last Song". Nutzt denselben Pfad wie
        der Play-Last-Button; startet nur, wenn nicht bereits Wartemusik laeuft.
        """
        if self._music_playing:
            # Wartemusik laeuft bereits: nur den Countdown neu anstossen.
            self._dispatch(Restart(duration_seconds))
            return
        # Neue Dauer vorab, damit die Wartemusik sie bekommt; _toggle_play_last
        # startet den Countdown selbst, sobald die Musik laeuft.
        self._dispatch(SetDuration(duration_seconds))
        self._toggle_play_last()
