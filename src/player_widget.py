"""Player-UI fuer Callers Caddy (BL-201, Stufe 6, aus main.py ausgelagert).

Enthaelt PlayerWidget (Transport/Tempo/Loop-Steuerung) samt Countdown-Overlay,
Status-Bar-Player, Loop-Marker-Slider, LoopWidget und den Beat-Snap-Worker.
Zirkelfrei: keine Rueckbezuege auf main.py.
"""

import os

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QPushButton, QLabel, QSlider, QFrame, QCheckBox, QSpinBox,
    QDoubleSpinBox, QAbstractSpinBox, QComboBox, QMessageBox, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QEvent, QSize
from PySide6.QtGui import (
    QKeySequence, QPainter, QColor, QPen, QCursor, QFont,
)

from song_db import Song, Location, CHECK_BEATSNAP_GENRE_NAME
from path_manager import PathManager
from skin_manager import SkinManager
from i18n import _t
from perf import perf_start, perf_split
from ui_helpers import (
    fmt_time, fmt_precise, _make_icon, SectionBarWidget,
    _SVG_PLAY, _SVG_PAUSE, _SVG_STOP, _SVG_FADE, _COFFEE_SVG,
)


class _CountdownOverlay(QWidget):
    """Halbtransparentes Vollbild-Overlay das die Beat-Anzahl bis zum Liedstart
    herunterzaehlt. Laeuft rein visuell — kein Einfluss auf Audio.

    Als rahmenloses Top-Level-Fenster mit WindowStaysOnTopHint, damit es auch
    ueber floating Docks und Rules-Fenstern erscheint.

    INI-Schluessel: display/countdown_enabled (Standard: true)
    Benoetigt: singing_start_m{slot} in DB + base_bpm > 0.
    """

    def __init__(self, main_win):
        super().__init__(None,
                         Qt.FramelessWindowHint |
                         Qt.WindowStaysOnTopHint |
                         Qt.Tool)
        self._main_win = main_win
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._number = 0        # aktuell angezeigte Zahl (0 = versteckt)
        self._pulse = 0.0       # 1.0 = heller Puls, faellt linear auf 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(30)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
        self.hide()

    def show_beat(self, n: int):
        """Zeigt Zahl n an; Puls-Animation wenn sich n veraendert hat.

        Wird bei jedem 50ms-Haupttick aufgerufen, solange der Countdown
        laeuft - setGeometry()/show()/raise() aber NUR beim erstmaligen
        Erscheinen bzw. wenn sich die Hauptfenster-Geometrie tatsaechlich
        geaendert hat (Fenster verschoben/resized), nicht bei jedem Tick.
        Der eigentliche Zahlenwechsel braucht das nicht - er wird ohnehin
        durch den 30ms-Puls-Timer (siehe _on_pulse_tick) neu gezeichnet.
        """
        changed = (n != self._number)
        self._number = n
        if n > 0:
            was_hidden = not self.isVisible()
            main_geo = self._main_win.geometry()
            if was_hidden or main_geo != self.geometry():
                self.setGeometry(main_geo)
            if was_hidden:
                self.show()
                self.raise_()
            if changed:
                self._pulse = 1.0
                if not self._pulse_timer.isActive():
                    self._pulse_timer.start()
        else:
            self._hide()

    def _hide(self):
        self._pulse_timer.stop()
        self._number = 0
        self._pulse = 0.0
        self.hide()

    def hide_overlay(self):
        self._hide()

    def _on_pulse_tick(self):
        self._pulse = max(0.0, self._pulse - 0.07)  # ~400ms Ausklang
        self.update()
        if self._pulse <= 0.0:
            self._pulse_timer.stop()

    def paintEvent(self, event):
        if self._number <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Hintergrund: halbdurchlaessig schwarz
        # Farbe: weiss beim Puls-Peak, mittleres Grau im Ruhezustand
        t = self._pulse
        v = int(180 + t * 75)   # 180 (grau) → 255 (weiss)
        # Schriftgroesse: leichter Zoom-Effekt beim Puls
        base_px = int(min(self.width(), self.height()) * 0.45)
        size_px = int(base_px * (1.0 + 0.12 * t))
        font = QFont()
        font.setPixelSize(max(20, size_px))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(v, v, v))
        p.drawText(self.rect(), Qt.AlignCenter, str(self._number))
        p.end()


class _StatusBarPlayerBar(QWidget):
    """Miniatur-Abspielfortschritt in der Statusleiste (BL-128).

    Zeigt:
    - 7 gleichbreite Sektionsstreifen (Farben wie SectionBarWidget, unten 4 px)
    - Semi-transparente Fortschritts-Fuellung
    - Loop-In / Loop-Out als vertikale Linien
    - Aktuelle Position als weisse Linie

    Ein-/ausschaltbar per INI: display/statusbar_player = true | false
    """

    _SEC_KEYS = SectionBarWidget._SEC_KEYS
    _FALLBACK  = SectionBarWidget._FALLBACK

    def __init__(self, skin_mgr=None, parent=None):
        super().__init__(parent)
        self._skin_mgr    = skin_mgr
        self._position: float = 0.0   # 0.0–1.0 (Wiedergabeposition)
        self._loop_in: float  = 0.0   # 0.0–1.0
        self._loop_out: float = 1.0   # 0.0–1.0
        self._sing_start: float = -1.0  # <0 = nicht bekannt → altes Layout
        self._sing_end: float   = -1.0
        self._has_song: bool  = False
        self.setFixedHeight(18)
        self.setMinimumWidth(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip("Wiedergabefortschritt (Loop-Markierungen und Sektionen)")

    def update_state(self, position: float, loop_in: float, loop_out: float,
                     has_song: bool, sing_start: float = -1.0, sing_end: float = -1.0):
        """Aktualisiert Wiedergabeposition und Loop-Markierungen (kein Repaint wenn unveraendert).
        sing_start/sing_end: Ratio 0–1 des Liedbeginns/-endes; <0 = unbekannt (altes Layout)."""
        if (self._position != position or self._loop_in != loop_in
                or self._loop_out != loop_out or self._has_song != has_song
                or self._sing_start != sing_start or self._sing_end != sing_end):
            self._position   = position
            self._loop_in    = loop_in
            self._loop_out   = loop_out
            self._sing_start = sing_start
            self._sing_end   = sing_end
            self._has_song   = has_song
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        w = self.width()
        h = self.height()

        # Hintergrund: slider_groove — exakt derselbe Key wie der Positionsslider im Player.
        # Existiert in allen Skins; Fallback = dark-skin Defaultwert.
        bg_str = (self._skin_mgr.color("slider_groove", "#404040")
                  if self._skin_mgr else "#404040")
        painter.fillRect(0, 0, w, h, QColor(bg_str))

        if not self._has_song or w <= 0:
            painter.end()
            return

        # 7 Sektionsstreifen mit 5 px Abstand (BG-Farbe) dazwischen — volle Hoehe.
        # Wenn Liedstart/-ende bekannt: Balken genau zwischen diesen Punkten.
        # Sonst: altes Layout mit halber Segmentbreite als Intro/Outro-Rand.
        GAP   = 5
        bg_str = (self._skin_mgr.color("slider_groove", "#404040")
                  if self._skin_mgr else "#404040")
        have_times = (0.0 <= self._sing_start < self._sing_end <= 1.0)
        if have_times:
            x_start = self._sing_start * w
            x_end   = self._sing_end   * w
            seg_w   = max(1.0, (x_end - x_start - GAP * 6) / 7)
        else:
            seg_w   = (w - GAP * 6) / 8   # altes Layout: 7 Seg + 1 (je 0.5 Rand)
            x_start = seg_w / 2
        for i in range(7):
            x0 = int(x_start + i * (seg_w + GAP))
            x1 = int(x0 + seg_w)
            painter.fillRect(x0, 0, max(1, x1 - x0), h, QColor(self._FALLBACK[i]))
        # Bereiche ausserhalb der Balken mit BG-Farbe abdecken
        painter.fillRect(0, 0, int(x_start), h, QColor(bg_str))
        x_after = int(x_start + 7 * (seg_w + GAP) - GAP)
        painter.fillRect(x_after, 0, max(0, w - x_after), h, QColor(bg_str))
        for i in range(6):
            xg = int(x_start + (i + 1) * (seg_w + GAP) - GAP)
            painter.fillRect(xg, 0, GAP, h, QColor(bg_str))

        # Fortschritts-Overlay: weiss, halbdeckend — sichtbar ueber allen Segment-Farben
        if self._position > 0.0:
            overlay = QColor("#ffffff")
            overlay.setAlpha(110)
            painter.fillRect(0, 0, max(1, int(self._position * w)), h, overlay)

        # Loop-Markierungen: schwarz, 4 px — deutlich sichtbar auf hellem Overlay und Sektionsfarben
        if self._loop_in > 0.0 or self._loop_out < 1.0:
            painter.setPen(QPen(QColor("#000000"), 4))
            if self._loop_in > 0.0:
                x_in = int(self._loop_in * w)
                painter.drawLine(x_in, 0, x_in, h - 1)
            if self._loop_out < 1.0:
                x_out = int(self._loop_out * w)
                painter.drawLine(x_out, 0, x_out, h - 1)

        # Positions-Linie: weiss, 2 px, gut sichtbar auf jedem Hintergrund
        x_pos = int(self._position * w)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawLine(x_pos, 0, x_pos, h - 1)

        painter.end()


class _LoopMarkerSlider(QSlider):
    """QSlider mit Loop-In/Out-Markierungen als vertikale Linien."""

    def __init__(self, orientation, skin_mgr=None, parent=None):
        super().__init__(orientation, parent)
        self._loop_in_ratio = 0.0   # 0.0–1.0
        self._loop_out_ratio = 1.0
        self._skin_mgr = skin_mgr

    def set_loop_markers(self, loop_in_ratio, loop_out_ratio):
        self._loop_in_ratio = max(0.0, min(1.0, loop_in_ratio))
        self._loop_out_ratio = max(0.0, min(1.0, loop_out_ratio))
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._loop_in_ratio <= 0.0 and self._loop_out_ratio >= 1.0:
            return
        painter = QPainter(self)
        # Button-Farbe aus Skin oder Fallback
        if self._skin_mgr:
            color_str = self._skin_mgr.color("button_bg", "#3daee9")
        else:
            color_str = "#3daee9"
        color = QColor(color_str)
        pen = QPen(color, 2)
        painter.setPen(pen)
        # Groove-Bereich berechnen (Slider-Raender abziehen)
        margin = 8
        w = self.width() - 2 * margin
        h = self.height()
        if w <= 0:
            return
        # Loop-In Linie
        if self._loop_in_ratio > 0.0:
            x_in = margin + int(self._loop_in_ratio * w)
            painter.drawLine(x_in, 2, x_in, h - 2)
        # Loop-Out Linie
        if self._loop_out_ratio < 1.0:
            x_out = margin + int(self._loop_out_ratio * w)
            painter.drawLine(x_out, 2, x_out, h - 2)
        painter.end()


class _ImportDropButton(QPushButton):
    """NEU-Button, der zusaetzlich Drag&Drop von Dateien/Ordnern annimmt (BL-179).

    Ein Drop von MP3/Audio, ZIP-Paketen oder Ordnern startet denselben Import
    wie der Klick — nur ohne vorgeschaltete Quellenauswahl. Die eigentliche
    Verarbeitung macht das Hauptfenster (`on_paths_dropped`); der Button liefert
    lediglich die lokalen Pfade und ein dezentes Drop-Highlight.
    """

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.on_paths_dropped = None  # Callback(list[str]) → Hauptfenster
        self._drag_style = ""
        self.setAcceptDrops(True)

    @staticmethod
    def _has_local_paths(mime) -> bool:
        return mime.hasUrls() and any(u.isLocalFile() for u in mime.urls())

    def dragEnterEvent(self, event):
        if self._has_local_paths(event.mimeData()):
            event.acceptProposedAction()
            # Dezentes Highlight ueber ein temporaeres StyleSheet; wird beim
            # Verlassen/Drop wieder geleert (Theme-Style bleibt unangetastet).
            if not self._drag_style:
                self._drag_style = "border: 2px dashed #4a90d9;"
                self.setStyleSheet(self._drag_style)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._has_local_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._clear_drag_style()
        super().dragLeaveEvent(event)

    def _clear_drag_style(self):
        if self._drag_style:
            self._drag_style = ""
            self.setStyleSheet("")

    def dropEvent(self, event):
        self._clear_drag_style()
        paths = [u.toLocalFile() for u in event.mimeData().urls()
                 if u.isLocalFile()]
        paths = [p for p in paths if p]
        if paths and self.on_paths_dropped:
            event.acceptProposedAction()
            self.on_paths_dropped(paths)
        else:
            event.ignore()


class BeatSnapWorker(QThread):
    """Worker-Thread fuer Beat-Grid-Berechnung (blockiert UI nicht)."""
    finished = Signal(object)  # (bpm, beat_times) Tuple
    error = Signal(str)

    def __init__(self, filepath: str, bpm: float = None):
        super().__init__()
        self._filepath = filepath
        self._bpm = bpm

    def run(self):
        try:
            from bpm_detector import detect_beat_grid
            result = detect_beat_grid(self._filepath, bpm=self._bpm)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class PlayerWidget(QWidget):
    """Player-Modul: Transport, Heutiges Tempo, Song-Tempo, Pitch, Position-Slider, Lokation-Button."""

    def __init__(self, engine, paths: PathManager, skin_mgr: SkinManager = None, parent=None,
                 session=None):
        super().__init__(parent)
        self.engine = engine
        self.paths = paths
        self._skin_mgr = skin_mgr
        self._seeking = False
        # Callbacks
        self.on_file_loaded = None
        self.on_before_load = None   # Callback: VOR engine.load() (Loop-Snapshot)
        self.on_tempo_changed = None
        self.on_pitch_changed = None
        self.on_today_tempo_changed = None
        self.on_location_clicked = None
        self.on_manager_clicked = None  # Callback: Playlist-Manager Toggle
        self.on_lyrics_clicked = None   # Callback: Lyrics Toggle
        self.on_play_started = None  # Callback: frischer Play-Start (nicht Resume)
        self.on_resumed = None       # Callback: Resume nach Pause
        # Optional: MainWindow orchestriert Play (Rule-Gating via PlayBarrier).
        # Signatur: on_play_orchestrate(is_resume). Ist er gesetzt, ruft der
        # Orchestrator _do_play() selbst auf, sobald der Gate frei ist.
        self.on_play_orchestrate = None
        self.on_pause = None         # Callback: User drueckt Pause
        self.on_manual_stop = None   # Callback: User drueckt Stop
        # BL-074: Audition-Kanal
        self._audition_active = False
        self._pre_audition_volume = 100
        self.on_audition = None       # () → MainWindow schaltet auf Sekundaerkanal
        self.on_exit_audition = None  # () → MainWindow stellt Primaerkanal wieder her
        self.on_dance_program_changed = None  # BL-132: (code: str) → Sequenz-Filter sync
        self.on_pick_programs = None           # MS50: () → MainWindow oeffnet Tanzprogramm-Picker (session-global)
        self.on_break_clicked = None  # () → MainWindow oeffnet das Break-Widget
        self._fade_duration = 3.0   # Sekunden (wird aus INI geladen)
        # Spieldauer-Timer
        self._play_start_time = None   # time.time() bei Play-Start
        self._timer_warn1 = 240        # Sekunden bis Warnstufe 1 (orange)
        self._timer_warn2 = 300        # Sekunden bis Warnstufe 2 (rot)
        self._timer_warn_state = 0     # 0=normal, 1=warn1, 2=warn2
        self._base_bpm = 0.0           # Base-BPM des aktuellen Songs
        self._target_bpm = 0.0         # BL-144: Ziel-BPM der Lokation (0 = aus)
        self._target_bpm_missed = False  # BL-144: Ziel bei diesem Song nicht erreichbar
        self._title_font_px  = 0   # letzter gesetzter Font-Pixelwert (0 = noch nicht gesetzt)
        self._theme_font_px  = 13  # aus skin.json font_size, Standard 13
        # NEU-Button ist jetzt im Loop-Widget, aber _load_file bleibt hier
        self._build_ui()
        # intern#142: Lokationswechsel kommt aus der aktuellen Sitzung
        if session is not None:
            session.location_changed.connect(self.set_location)

    def _build_ui(self):
        _pb0 = perf_start()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Info-Streifen: Timer | BPM | Loop-Count | Tanzprogramm ──────────
        self._info_frame = QFrame()
        self._info_frame.setObjectName("PlayerInfoStrip")
        info_grid = QGridLayout(self._info_frame)
        info_grid.setContentsMargins(8, 4, 8, 4)
        info_grid.setSpacing(2)
        info_grid.setColumnStretch(0, 1)
        info_grid.setColumnStretch(1, 1)
        info_grid.setColumnStretch(2, 1)
        info_grid.setColumnStretch(3, 1)

        # Hilfsfunktion: gleiche SizePolicy fuer alle Zellen erzwingen
        def _info_policy():
            p = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            return p

        # ── Zeile 0: Beschriftungs-Labels ────────────────────────────────────
        for col, hdr_text in enumerate([_t("player_header_duration"), "BPM", "Loops", _t("player_header_program")]):
            lbl = QLabel(hdr_text)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setMinimumWidth(0)
            lbl.setSizePolicy(_info_policy())
            lbl.setProperty("infoHeader", True)   # fuer CSS-Selektor QLabel[infoHeader="true"]
            info_grid.addWidget(lbl, 0, col)

        # ── Zeile 1: Werte ────────────────────────────────────────────────────
        # Spieldauer-Timer (Spalte 0)
        self._timer_border_color = self._skin_mgr.color("muted_bg", "#424242") if self._skin_mgr else "#424242"
        self.label_play_timer = QLabel("00:00")
        self.label_play_timer.setAlignment(Qt.AlignCenter)
        self.label_play_timer.setMinimumWidth(0)
        self.label_play_timer.setSizePolicy(_info_policy())
        self.label_play_timer.setToolTip(_t("tooltip_loop_count"))
        self.label_play_timer.setStyleSheet(
            "font-size: 15px; font-family: monospace; font-weight: bold;")
        info_grid.addWidget(self.label_play_timer, 1, 0)

        # BPM (Spalte 1)
        self.label_bpm = QLabel("")
        self.label_bpm.setAlignment(Qt.AlignCenter)
        self.label_bpm.setMinimumWidth(0)
        self.label_bpm.setSizePolicy(_info_policy())
        self.label_bpm.setStyleSheet(
            "font-size: 13px; font-family: monospace; font-weight: bold;")
        info_grid.addWidget(self.label_bpm, 1, 1)

        # Loop-Count (Spalte 2, initial versteckt)
        self.label_loop_count = QLabel("")
        self.label_loop_count.setAlignment(Qt.AlignCenter)
        self.label_loop_count.setMinimumWidth(0)
        self.label_loop_count.setSizePolicy(_info_policy())
        self.label_loop_count.setToolTip(_t("tooltip_loop_count"))
        self.label_loop_count.setStyleSheet(
            "font-size: 13px; font-family: monospace; font-weight: bold;")
        self.label_loop_count.setVisible(False)
        info_grid.addWidget(self.label_loop_count, 1, 2)

        # BL-083: Tanzprogramm-Button (Spalte 3)
        self._dance_program_id = None
        self._dance_program_code = ""
        self.btn_program = QPushButton("—")
        self.btn_program.setMinimumWidth(0)
        self.btn_program.setMinimumHeight(0)
        self.btn_program.setMaximumHeight(24)
        self.btn_program.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.btn_program.setToolTip(_t("dance_btn_tooltip"))
        self.btn_program.clicked.connect(self._on_program_btn_clicked)
        info_grid.addWidget(self.btn_program, 1, 3)

        # Kaffeetasse (einfarbig, flach) als eigene Spalte am Ende -> Break-Widget
        self.btn_break = QPushButton()
        self.btn_break.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_break.setToolTip(_t("break_btn_tooltip"))
        self.btn_break.setFlat(True)
        self.btn_break.setFixedWidth(34)
        self.btn_break.setIconSize(QSize(20, 20))
        self.btn_break.setStyleSheet(
            "QPushButton { border: none; background: transparent; }"
            "QPushButton:hover { background: rgba(127,127,127,0.20); "
            "border-radius: 6px; }")
        self.btn_break.clicked.connect(self._on_break_btn_clicked)
        self._apply_break_icon()
        # Eigene, nicht gedehnte Spalte 4 (ueber beide Zeilen)
        info_grid.addWidget(self.btn_break, 0, 4, 2, 1)

        layout.addWidget(self._info_frame)
        _pb1 = perf_split("      Player._build_ui: info strip", _pb0)

        # ── Player-Karte ─────────────────────────────────────────────────────
        self._card = QFrame()
        self._card.setObjectName("PlayerCard")
        self._card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(8, 8, 8, 6)
        card_layout.setSpacing(4)

        # Song-Titel (links) + Status (rechts) in einer Zeile.
        # label_file hat Expanding vertikal: es nimmt allen freien Platz in der
        # Card auf. resizeEvent skaliert den Font passend zur verfuegbaren Hoehe.
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        self._current_filename = None   # None = keine Datei angezeigt (intern#212)
        self.label_file = QLabel(_t("no_file_loaded"))
        self.label_file.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.label_file.setWordWrap(True)
        self.label_file.setMinimumHeight(0)
        self.label_file.setMaximumHeight(52)
        self.label_file.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # BL-138 (v0.97 Refinement): Status + Label-Info stehen rechts in einer
        # vertikalen Spalte. Spacing 0 — Label klebt direkt über dem Status,
        # frisst dem Titel keinen zusätzlichen horizontalen Platz.
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(0)
        self.label_label_info = QLabel("")
        self.label_label_info.setAlignment(Qt.AlignTop | Qt.AlignRight)
        self.label_label_info.setWordWrap(False)
        self.label_label_info.setMinimumHeight(0)
        self.label_label_info.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.label_label_info.setVisible(False)
        self.label_status = QLabel(_t("status_ready"))
        self.label_status.setAlignment(Qt.AlignTop | Qt.AlignRight)
        self.label_status.setWordWrap(False)
        self.label_status.setMinimumHeight(0)
        self.label_status.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        right_col.addWidget(self.label_label_info)
        right_col.addWidget(self.label_status)
        title_row.addWidget(self.label_file)
        title_row.addLayout(right_col)
        card_layout.addLayout(title_row)

        # Zeitanzeige: aktuelle Zeit (gross+fett) + Gesamtzeit (gedimmt)
        time_row = QHBoxLayout()
        time_row.setContentsMargins(0, 4, 0, 0)
        self.label_time_current = QLabel("00:00.00")
        self.label_time_current.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.label_time_total = QLabel(" / 00:00")
        self.label_time_total.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        time_row.addStretch()
        time_row.addWidget(self.label_time_current)
        time_row.addWidget(self.label_time_total)
        time_row.addStretch()
        card_layout.addLayout(time_row)

        # Position-Slider mit Loop-Marken (MUSS _LoopMarkerSlider bleiben!)
        self.slider_position = _LoopMarkerSlider(Qt.Horizontal, skin_mgr=self._skin_mgr)
        self.slider_position.setRange(0, 1000)
        self.slider_position.setValue(0)
        self.slider_position.setEnabled(False)
        self.slider_position.sliderPressed.connect(self._on_seek_start)
        self.slider_position.sliderReleased.connect(self._on_seek_end)
        card_layout.addWidget(self.slider_position)

        # Singing-Call Abschnitte
        self.section_bar = SectionBarWidget(skin_mgr=self._skin_mgr, parent=self._card)
        card_layout.addWidget(self.section_bar)

        layout.addWidget(self._card, 1)   # Stretch 1: nimmt extra Hoehe auf
        _pb2 = perf_split("      Player._build_ui: card", _pb1)

        # ── Transport-Buttons ─────────────────────────────────────────────────
        self.btn_play = QPushButton(_t("btn_play"))
        self.btn_play.clicked.connect(self._on_play)
        self.btn_play.setEnabled(False)
        self.btn_play.setMinimumHeight(44)
        self.btn_play.setIconSize(QSize(20, 20))
        self.btn_play.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # BL-074: Audition — Song auf sekundaerem Kanal vorhören
        self.btn_audition = QPushButton(_t("btn_audition"))
        self.btn_audition.setToolTip(_t("tooltip_audition"))
        self.btn_audition.setCheckable(True)
        self.btn_audition.clicked.connect(self._on_audition)
        self.btn_audition.setEnabled(False)
        self.btn_audition.setMinimumHeight(44)
        self.btn_audition.setIconSize(QSize(16, 16))

        self.btn_pause = QPushButton(_t("btn_pause"))
        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setMinimumHeight(34)
        self.btn_pause.setIconSize(QSize(16, 16))

        self.btn_stop = QPushButton(_t("btn_stop"))
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setMinimumHeight(34)
        self.btn_stop.setIconSize(QSize(16, 16))

        self.btn_fade = QPushButton(_t("btn_fade_out"))
        self.btn_fade.setToolTip(_t("tooltip_fade_out"))
        self.btn_fade.clicked.connect(self._on_fade_out)
        self.btn_fade.setEnabled(False)
        self.btn_fade.setMinimumHeight(34)
        self.btn_fade.setIconSize(QSize(16, 16))

        # Grid: [Play (Spalten 0+1)] [Audition (Spalte 2)]
        #        [Pause  (Spalte 0)] [Stop (Sp 1)] [Fade (Sp 2)]
        # → Audition liegt optisch exakt über Fade Out
        from PySide6.QtWidgets import QGridLayout as _QGridLayout
        transport_grid = _QGridLayout()
        transport_grid.setSpacing(6)
        transport_grid.addWidget(self.btn_play,     0, 0, 1, 2)
        transport_grid.addWidget(self.btn_audition, 0, 2)
        transport_grid.addWidget(self.btn_pause,    1, 0)
        transport_grid.addWidget(self.btn_stop,     1, 1)
        transport_grid.addWidget(self.btn_fade,     1, 2)
        layout.addLayout(transport_grid)
        _pb3 = perf_split("      Player._build_ui: transport buttons", _pb2)

        # ── MIX: Heutiges Tempo | Song-Tempo | Pitch | Live-Vol ───────────────
        tp_layout = QGridLayout()
        tp_layout.setColumnStretch(0, 1)
        tp_layout.setColumnStretch(1, 1)
        tp_layout.setColumnStretch(2, 1)
        tp_layout.setColumnStretch(3, 1)

        for col, key in enumerate(["label_today_tempo", "label_song_tempo",
                                    "label_pitch", "label_live_volume"]):
            lbl = QLabel(_t(key))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size: 11px;")
            lbl.setWordWrap(True)
            lbl.setMinimumWidth(0)
            lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            tp_layout.addWidget(lbl, 0, col)

        self.spin_today_tempo = QSpinBox()
        self.spin_today_tempo.setRange(50, 150)
        self.spin_today_tempo.setValue(100)
        self.spin_today_tempo.setSuffix(" %")
        self.spin_today_tempo.setSingleStep(1)
        self.spin_today_tempo.setMinimumHeight(24)
        self.spin_today_tempo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.spin_today_tempo.setToolTip(_t("tooltip_today_tempo"))
        self.spin_today_tempo.valueChanged.connect(self._on_today_tempo_changed)
        tp_layout.addWidget(self.spin_today_tempo, 1, 0)

        self.spin_tempo = QSpinBox()
        self.spin_tempo.setRange(50, 150)
        self.spin_tempo.setValue(100)
        self.spin_tempo.setSuffix(" %")
        self.spin_tempo.setSingleStep(1)
        self.spin_tempo.setMinimumHeight(24)
        self.spin_tempo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.spin_tempo.setToolTip(_t("tooltip_song_tempo"))
        self.spin_tempo.valueChanged.connect(self._on_tempo_changed)
        # editingFinished: speichert in DB beim Verlassen des Feldes
        # (Enter / Tab / Fokus-Wechsel). Wird auch beim Song-Wechsel
        # ueber _flush_tempo manuell ausgeloest, falls dirty.
        self.spin_tempo.editingFinished.connect(self._flush_tempo)
        tp_layout.addWidget(self.spin_tempo, 1, 1)

        self.spin_pitch = QDoubleSpinBox()
        self.spin_pitch.setRange(-6.0, 6.0)
        self.spin_pitch.setValue(0.0)
        self.spin_pitch.setSuffix(" HT")
        self.spin_pitch.setSingleStep(0.2)
        self.spin_pitch.setDecimals(1)
        self.spin_pitch.setMinimumHeight(24)
        self.spin_pitch.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.spin_pitch.setToolTip(_t("tooltip_pitch"))
        self.spin_pitch.valueChanged.connect(self._on_pitch_changed)
        self.spin_pitch.editingFinished.connect(self._flush_pitch)
        tp_layout.addWidget(self.spin_pitch, 1, 2)

        self.slider_live_volume = QSlider(Qt.Horizontal)
        self.slider_live_volume.setRange(0, 100)
        self.slider_live_volume.setValue(100)
        self.slider_live_volume.setMinimumHeight(24)
        self.slider_live_volume.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.slider_live_volume.setToolTip(_t("tooltip_live_volume"))
        self.slider_live_volume.valueChanged.connect(self._on_live_volume_changed)
        tp_layout.addWidget(self.slider_live_volume, 1, 3)

        layout.addLayout(tp_layout)
        _pb4 = perf_split("      Player._build_ui: tempo+pitch spinboxes", _pb3)

        # ── Toolbar: Lokation | Planner | Lyrics | Loop-Checkbox ─────────────
        toolbar_layout = QGridLayout()
        toolbar_layout.setColumnStretch(0, 1)
        toolbar_layout.setColumnStretch(1, 1)
        toolbar_layout.setColumnStretch(2, 1)
        toolbar_layout.setColumnStretch(3, 1)

        self.btn_location = QPushButton(_t("btn_location"))
        self.btn_location.setShortcut(QKeySequence())
        self.btn_location.setToolTip(_t("tooltip_location"))
        self.btn_location.setMinimumHeight(34)
        self.btn_location.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.btn_location.clicked.connect(self._on_location_clicked)
        self._set_location_button_warning(True)
        toolbar_layout.addWidget(self.btn_location, 0, 0)

        self.btn_manager = QPushButton(_t("btn_planner"))
        self.btn_manager.setShortcut(QKeySequence())
        self.btn_manager.setToolTip(_t("tooltip_planner"))
        self.btn_manager.setMinimumHeight(34)
        self.btn_manager.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.btn_manager.clicked.connect(self._on_manager_clicked)
        toolbar_layout.addWidget(self.btn_manager, 0, 1)

        self.btn_lyrics = QPushButton(_t("btn_lyrics"))
        self.btn_lyrics.setToolTip(_t("tooltip_lyrics"))
        self.btn_lyrics.setMinimumHeight(34)
        self.btn_lyrics.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.btn_lyrics.clicked.connect(self._on_lyrics_clicked)
        toolbar_layout.addWidget(self.btn_lyrics, 0, 2)

        # Spalte 3: Loop-Active-Checkbox wird von MainWindow eingefuegt
        self._loop_active_grid = toolbar_layout

        layout.addLayout(toolbar_layout)
        perf_split("      Player._build_ui: toolbar", _pb4)

        # Skin-abhaengige Styles initial setzen
        self.update_skin()

        # Mausrad-Schutz: SpinBoxes/Combos/Slider im Player nicht versehentlich
        # via Scrollen aenderbar (Tempo/Pitch/Volume/Position sind im Live-
        # Betrieb kritisch — ein Scroll-Unfall haette hoerbare Folgen).
        for child in self.findChildren(QAbstractSpinBox):
            child.installEventFilter(self)
        for child in self.findChildren(QComboBox):
            child.installEventFilter(self)
        for child in self.findChildren(QSlider):
            child.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and isinstance(
                obj, (QAbstractSpinBox, QComboBox, QSlider)):
            event.ignore()
            return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        """Schiebt Font-Update NACH den Qt-Layout-Durchlauf (singleShot 0)."""
        super().resizeEvent(event)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._update_title_font)

    def _update_title_font(self):
        """Skaliert Titel-Font sanft zur verfuegbaren Label-Hoehe.

        label_file hat Expanding-Policy und nimmt den freien Platz der Card auf.
        Nach dem Layout-Durchlauf (QTimer.singleShot) spiegelt label_file.height()
        den echten Wert wider. Skalierung: 13 px (h<=20) bis 26 px (h>=100).
        Wichtig: setStyleSheet() statt setFont(), weil skin.qss
        QWidget { font-size } global setzt und setFont() dort unterliegt.
        """
        h = self.label_file.height()
        base = self._theme_font_px          # z.B. 13
        # Linear: base px bei h=20, base+13 px bei h=100, danach konstant
        new_px = max(base, min(base + 13, base + (h - 20) * 13 // 80))
        if new_px == self._title_font_px:
            return
        self._title_font_px = new_px
        tc = getattr(self, '_title_text_color', '#f0f0f0')
        self.label_file.setStyleSheet(
            f"font-size: {new_px}px; font-weight: bold; color: {tc}; background: transparent;")

    def _set_button_warning(self, button, warning: bool):
        """Setzt einen Button auf rot (Warnung) oder normal (Skin-Default)."""
        button.setProperty("warning", "true" if warning else "false")
        button.style().unpolish(button)
        button.style().polish(button)

    def _set_location_button_warning(self, warning: bool):
        """Setzt den Lokation-Button auf rot (keine Lokation) oder normal."""
        self._set_button_warning(self.btn_location, warning)

    def set_planner_warning(self, warning: bool):
        """Setzt den Planner-Button auf rot oder normal (von aussen steuerbar)."""
        self._set_button_warning(self.btn_manager, warning)

    def set_title(self, title: str):
        """Zeigt den Song-Titel statt Dateinamen an."""
        if title:
            self.label_file.setText(title)

    def set_label_info(self, label: str):
        """BL-138: zeigt das Label (Plattenlabel inkl. Nummer aus song.label)
        direkt über der Statuszeile, rechts ausgerichtet, ohne Abstand.

        Wenn leer: Widget ausgeblendet.
        """
        text = (label or "").strip()
        if not text:
            self.label_label_info.setVisible(False)
            self.label_label_info.setText("")
            return
        self.label_label_info.setText(text)
        self.label_label_info.setVisible(True)

    def set_location(self, location: Location):
        """Aktualisiert den Lokation-Button nach Auswahl.

        Der Button-Text bleibt immer "Lokation" (bzw. die jeweilige Uebersetzung) —
        der gewaehlte Lokationsname wird bewusst NICHT in den Button geschrieben.
        Nur die Warn-Markierung haengt davon ab, ob eine Lokation gewaehlt ist.
        """
        self.btn_location.setText(_t("btn_location"))
        self._set_location_button_warning(location is None)
        self._location = location  # MS50: fuer Mehrfach-Programmwahl am Player-Button
        # BL-144: Ziel-BPM der Lokation merken — angewandt wird sie beim Songwechsel
        self._target_bpm = (float(location.target_bpm)
                            if location is not None and location.has_target_bpm
                            else 0.0)
        # BL-144: Ziel-BPM hat Vorrang — fuer den bereits geladenen Song sofort
        # nachziehen. Sonst BL-086: temporaeres Tempo der Lokation uebernehmen.
        if self._target_bpm > 0:
            self._apply_target_bpm()
            self._update_bpm_display()
        elif location is not None and location.temp_tempo is not None:
            self.spin_today_tempo.setValue(int(location.temp_tempo))
        # Caller-Workflow: mit Lokation ist der Planner der naechste Schritt
        self.set_planner_warning(location is not None)

    # BL-083 ----------------------------------------------------------------
    def set_dance_program(self, program_id, code: str):
        """Setzt das aktive Tanzprogramm und aktualisiert den Button-Text."""
        self._dance_program_id = program_id
        self._dance_program_code = code
        if program_id is None:
            self.btn_program.setText("—")
            self.btn_program.setToolTip(_t("dance_btn_tooltip_none"))
        else:
            self.btn_program.setText(code)
            self.btn_program.setToolTip(_t("dance_btn_tooltip_active", label=code))
        # Kein setFixedWidth – Spaltenbreite wird durch QGridLayout mit Ignored-Policy gesteuert
        # BL-132: Sequenz-Filter-Sync benachrichtigen
        if self.on_dance_program_changed is not None:
            self.on_dance_program_changed(code)

    def _apply_break_icon(self):
        """Kaffeetassen-Icon in Theme-Textfarbe setzen (nach Skin-Wechsel erneut)."""
        color = self._skin_mgr.color("text", "#f0f0f0") if self._skin_mgr else "#f0f0f0"
        self.btn_break.setIcon(_make_icon(_COFFEE_SVG, color))

    def _on_break_btn_clicked(self):
        """Kaffeetassen-Button -> Break-Widget oeffnen (Callback ans MainWindow)."""
        if callable(self.on_break_clicked):
            self.on_break_clicked()

    def _on_program_btn_clicked(self):
        # MS50: Tanzprogramm ist session-global (unabhaengig von der Lokation).
        # Die Auswahl + Persistenz uebernimmt das MainWindow via Callback.
        cb = getattr(self, 'on_pick_programs', None)
        if callable(cb):
            cb()
    # -----------------------------------------------------------------------

    def apply_song_settings(self, song: Song):
        """Setzt Tempo/Pitch/Volume auf die gespeicherten Song-Werte."""
        # _loading unterdrueckt Dirty-Marker in _on_tempo_changed/_on_pitch_changed,
        # waehrend die SpinBoxes auf die gerade-aus-DB-gelesenen Werte gesetzt werden.
        self._loading = True
        try:
            tempo_pct = int(song.standard_tempo * 100)
            self.spin_tempo.setValue(max(50, min(150, tempo_pct)))
            self.spin_pitch.setValue(max(-6.0, min(6.0, song.pitch)))
        finally:
            self._loading = False
        # intern#147: engine.load() setzt Pitch/Tempo zurueck. Zeigt die SpinBox
        # schon denselben Wert (Song erneut geladen), feuert kein valueChanged —
        # daher die Werte hier explizit an die Engine geben.
        self.engine.set_tempo(self.spin_tempo.value() / 100.0)
        self.engine.set_pitch(self.spin_pitch.value())
        # Frisch geladen = nichts mehr zu speichern.
        self._tempo_dirty = False
        self._pitch_dirty = False
        self._base_bpm = song.base_bpm or 0.0
        self._apply_target_bpm()
        self._update_bpm_display()
        # Song-Volume an Engine weitergeben (multiplikativer Faktor)
        self.engine.set_volume(song.volume)

    def refresh_loop_markers(self):
        """Setzt die Loop-Marken (schwarze Balken) im Positions-Slider neu.

        Eigene Methode, damit sie auch ausserhalb des Timers (z.B. nach
        Loop-Finder-Apply im pausierten Zustand) aufgerufen werden kann.
        """
        orig_dur = self.engine.get_original_duration()
        li = self.engine.loop_in_seconds
        lo = self.engine.loop_out_seconds
        self.slider_position.set_loop_markers(
            li / orig_dur if orig_dur > 0 else 0.0,
            lo / orig_dur if orig_dur > 0 else 1.0
        )

    def update_display(self):
        import time as _time
        self._show_device_notice()
        # intern#212: Ohne angezeigte Datei (nichts geladen oder Song geloescht)
        # nichts anzeigen und vor allem btn_play nicht wieder einschalten. Die
        # Engine behaelt die Audiodaten eines geloeschten Songs bis zum
        # naechsten Laden, is_loaded() bleibt deshalb True.
        if not self.has_file():
            return
        if self.engine.is_playing():
            # Loop-Punkt-Erkennung: Seek zum Loop-In wenn Wiedergabe
            # den Loop-Out erreicht (wie Beat Snap Audition).
            self.engine.check_loop_point()
            # _feed_stretcher() wird ab v0.80 vom dedizierten Feeder-Thread
            # in AudioEngine aufgerufen — nicht mehr vom UI-Timer.
            # Damit ist das Audio-Feeding vom Main-Thread entkoppelt.

        pos = self.engine.get_position_seconds()
        dur = self.engine.get_duration_seconds()
        orig_dur = self.engine.get_original_duration()
        # Echtzeit-Position = original_pos * (echtzeit_total / original_total)
        # Beide Labels damit in derselben Einheit (Echtzeit), Slider-Fraction bleibt gleich.
        real_pos = (pos * dur / orig_dur) if orig_dur > 0 else 0.0
        self.label_time_current.setText(fmt_precise(real_pos))
        self.label_time_total.setText(f" / {fmt_time(dur)}")

        if not self._seeking:
            if orig_dur > 0:
                val = int((pos / orig_dur) * 1000)
                self.slider_position.blockSignals(True)
                self.slider_position.setValue(min(1000, val))
                self.slider_position.blockSignals(False)
                # Loop-Marken aktualisieren
                self.refresh_loop_markers()

        # Spieldauer-Timer aktualisieren
        if self._play_start_time is not None:
            elapsed = _time.time() - self._play_start_time
            mins = int(elapsed) // 60
            secs = int(elapsed) % 60
            self.label_play_timer.setText(f"{mins:02d}:{secs:02d}")
            # Warnstufen pruefen
            new_state = 0
            if elapsed >= self._timer_warn2:
                new_state = 2
            elif elapsed >= self._timer_warn1:
                new_state = 1
            if new_state != self._timer_warn_state:
                self._timer_warn_state = new_state
                self._update_timer_style()

        # Loop-Count-Anzeige aktualisieren
        target = self.engine.loop_count_target
        if target > 0:
            done = self.engine.loop_count_done
            self.label_loop_count.setText(f"{done}/{target}")
            self.label_loop_count.setVisible(True)
        elif self.engine._loop_active and self.engine.is_playing():
            self.label_loop_count.setText("∞")
            self.label_loop_count.setVisible(True)
        else:
            self.label_loop_count.setVisible(False)

        if self.engine.is_playing():
            if self.engine.is_fading():
                self.label_status.setText(_t("status_fade_out"))
            else:
                if self.engine._loop_active:
                    self.label_status.setText(_t("status_playing_loop"))
                else:
                    self.label_status.setText(_t("status_playing"))
        elif self.engine.is_paused():
            self.label_status.setText(_t("status_paused"))
        elif self.engine.is_loaded() and not self.engine.playing:
            self._exit_audition()  # Primaerkanal wiederherstellen falls Audition lief
            self.label_status.setText(_t("status_stopped"))
            # Button-States korrigieren wenn Song natuerlich endet / Fade endet
            self.btn_play.setEnabled(True)
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.btn_fade.setEnabled(False)
            # Timer zuruecksetzen bei natuerlichem Song-Ende
            if self._play_start_time is not None:
                self._reset_play_timer()

    def _on_seek_start(self):
        self._seeking = True

    def _on_seek_end(self):
        self._seeking = False
        dur = self.engine.get_original_duration()
        if dur > 0:
            self.engine.seek((self.slider_position.value() / 1000.0) * dur)

    def _on_today_tempo_changed(self, value):
        self.engine.set_today_tempo(value / 100.0)
        self._update_bpm_display()
        if self.on_today_tempo_changed:
            self.on_today_tempo_changed(value / 100.0)

    def _on_tempo_changed(self, value):
        self.engine.set_tempo(value / 100.0)
        self._update_bpm_display()
        if self.on_tempo_changed:
            self.on_tempo_changed(value / 100.0)
        # Variante C+: KEIN DB-Write hier — sonst Audio-Buffer-Underrun
        # bei schnellem Drag (DB-commit blockiert Main-Thread).
        # Nur Dirty-Flag setzen; geschrieben wird bei editingFinished
        # (Fokus-Verlust / Enter) oder vor dem naechsten Song-Wechsel.
        if not getattr(self, '_loading', False):
            self._tempo_dirty = True

    def _on_pitch_changed(self, value):
        self.engine.set_pitch(value)
        if self.on_pitch_changed:
            self.on_pitch_changed(value)
        if not getattr(self, '_loading', False):
            self._pitch_dirty = True

    # ---- Dirty-Flag-basiertes Persistieren (kein Throttle, kein Thread) ----

    def _flush_tempo(self):
        """Schreibt Tempo in DB falls geaendert. Idempotent.
        Wird ausgeloest von editingFinished UND vor jedem Song-Wechsel
        ueber MainWindow._flush_player_values()."""
        if not getattr(self, '_tempo_dirty', False):
            return
        main_win = self.window()
        song = getattr(main_win, '_current_song', None)
        db = getattr(self, '_db', None)
        if not song or not song.id or db is None:
            self._tempo_dirty = False
            return
        tempo = self.spin_tempo.value() / 100.0
        song.standard_tempo = tempo
        db.save_playback_settings(song.id, tempo=tempo)
        self._tempo_dirty = False

    def _flush_pitch(self):
        """Schreibt Pitch in DB falls geaendert. Idempotent."""
        if not getattr(self, '_pitch_dirty', False):
            return
        main_win = self.window()
        song = getattr(main_win, '_current_song', None)
        db = getattr(self, '_db', None)
        if not song or not song.id or db is None:
            self._pitch_dirty = False
            return
        pitch = self.spin_pitch.value()
        song.pitch = pitch
        db.save_playback_settings(song.id, pitch=pitch)
        self._pitch_dirty = False

    def _on_live_volume_changed(self, value):
        """Live-Volume-Slider geaendert: sofort via WASAPI setzen (artefaktfrei)."""
        self.engine.set_live_volume(value / 100.0)
        # Tooltip mit aktuellem Wert aktualisieren
        self.slider_live_volume.setToolTip(
            f"{_t('tooltip_live_volume')} ({value}%)")

    def reset_live_volume(self):
        """Setzt Live-Volume auf 100% zurueck (bei Song-Wechsel)."""
        self.slider_live_volume.blockSignals(True)
        self.slider_live_volume.setValue(100)
        self.slider_live_volume.blockSignals(False)
        self.engine.reset_live_volume()

    def _on_location_clicked(self):
        if self.on_location_clicked:
            self.on_location_clicked()

    def _on_manager_clicked(self):
        if self.on_manager_clicked:
            self.on_manager_clicked()

    def _on_lyrics_clicked(self):
        if self.on_lyrics_clicked:
            self.on_lyrics_clicked()

    def _load_file(self, filepath):
        """Laedt eine MP3-Datei in die Engine."""
        try:
            # Callback VOR engine.load(): Loop-Werte sichern, da load()
            # die Engine-Loops auf (0, Songlaenge) zuruecksetzt
            if self.on_before_load:
                self.on_before_load()
            # Live-Volume bewusst NICHT zuruecksetzen: der Regler bleibt fuer die
            # Session auf dem eingestellten Wert (Nutzerwunsch). Die Engine
            # re-appliziert _live_volume nach load() selbst (_wasapi_lookup_delayed).
            # Wer pro Song/Auto-Advance einen festen Pegel will, nutzt die
            # Rules-Action "Set Live-Volume" (z.B. Trigger "Song Changed").
            self.engine.load(filepath)
            self._current_filename = os.path.basename(filepath)
            self.label_file.setText(self._current_filename)
            dur = self.engine.get_original_duration()
            self.label_status.setText(_t("status_loaded", time=fmt_time(dur)))
            self.btn_play.setEnabled(True)
            self.btn_audition.setEnabled(True)
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.btn_fade.setEnabled(False)
            self.slider_position.setEnabled(True)

            if self.on_file_loaded:
                self.on_file_loaded(filepath)

        except Exception:
            self.label_status.setText(_t("status_load_failed"))
            fname = os.path.basename(filepath)
            ext = os.path.splitext(filepath)[1].lower()
            # Bekannt nicht abspielbare Nicht-Audio-Formate (z.B. MIDI): das ist
            # kein unerwarteter Fehler -> knappe Log-Zeile statt Traceback.
            if ext in ('.mid', '.midi', '.kar'):
                print(f"[Player] Nicht abspielbares Format uebersprungen: {fname}")
            else:
                import traceback
                traceback.print_exc()
                # MP3-spezifischer Hinweis: defekte Frames koennen nur von
                # robusten Decodern (z.B. ffmpeg) uebersprungen werden.
                # Callers Caddy nutzt libsndfile/mpg123, das bei nicht-standard-
                # konformen Frames abbricht. Nutzer klar aufklaeren.
                if ext == '.mp3':
                    QMessageBox.warning(
                        self,
                        _t("err_mp3_title"),
                        _t("err_mp3_body", filename=fname)
                    )

    def load_from_list(self, filepath):
        """Wird von der Songliste aufgerufen — laedt ohne Dialog."""
        self._load_file(filepath)

    def _on_play(self):
        if not self.has_file():
            return  # intern#212: nichts geladen oder Song geloescht
        self._exit_audition()  # Audition-Modus beenden, Primaerkanal wiederherstellen
        import time as _time
        is_resume = self.engine.paused  # VOR engine.play() pruefen
        is_restart = self.engine.is_playing() and not self.engine.paused
        if is_restart:
            # Song laeuft bereits → von vorne starten
            self.engine.seek(0)
            self._play_start_time = _time.time()
            self._timer_warn_state = 0
            self._update_timer_style()
            return
        # Ab hier startet der Song frisch (oder resumt). Wenn MainWindow das
        # Play orchestriert (Rule-Gating), uebergeben wir die Kontrolle: der
        # Orchestrator feuert die Rules ZUERST (bei Stille) und ruft _do_play()
        # erst auf, wenn stream-gefaehrdende Layout-/Loop-Aktionen fertig sind.
        if self.on_play_orchestrate:
            self.on_play_orchestrate(is_resume)
        else:
            # Fallback (kein MainWindow verdrahtet): altes Verhalten 1:1.
            self._do_play(is_resume)
            if not is_resume and self.on_play_started:
                self.on_play_started()
            if is_resume and self.on_resumed:
                self.on_resumed()

    def _show_device_notice(self):
        """Zeigt einen Geraete-Hinweis der Engine an (intern#237).

        Nicht-modal: Die Musik laeuft beim Ausweichen aufs Standardgeraet schon,
        der Hinweis darf nichts blockieren. Ein noch offener Hinweis wird
        ersetzt statt gestapelt.
        """
        notice = self.engine.take_device_notice()
        if notice is None:
            return
        kind, detail = notice
        if kind == "fallback":
            body = _t("audio_device_fallback_body", device=detail)
        else:
            body = _t("audio_device_failed_body")
        box = getattr(self, "_device_notice_box", None)
        if box is None:
            box = QMessageBox(QMessageBox.Warning, _t("audio_device_title"), "",
                              QMessageBox.Ok, self)
            box.setModal(False)
            self._device_notice_box = box
        box.setText(body)
        box.show()
        box.raise_()

    def _do_play(self, is_resume: bool):
        """Startet die AUDIO-Wiedergabe + UI-Zustand. Feuert bewusst KEINE
        Rule-Trigger — das macht der Orchestrator vor bzw. nach diesem Aufruf,
        damit die Reihenfolge (Layout vor hoerbarem Audio) stimmt."""
        import time as _time
        self.engine.reset_audio_diag()
        self.engine.play()
        if not self.engine.playing and self.engine.is_loaded():
            # intern#237: kein Ausgabegeraet startbar — Knoepfe bleiben im
            # Stop-Zustand, Hinweis sofort statt erst beim naechsten Tick.
            self._show_device_notice()
            return
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.btn_fade.setEnabled(True)
        # Spieldauer-Timer: nur bei frischem Start (nicht Resume)
        if not is_resume:
            self._play_start_time = _time.time()
            self._timer_warn_state = 0
            self._update_timer_style()

    def _on_pause(self):
        self._exit_audition()  # Audition-Modus beenden, Primaerkanal wiederherstellen
        self.engine.pause()
        self.btn_play.setEnabled(True)
        self.btn_pause.setEnabled(False)
        # Timer laeuft weiter (Taenzer warten)
        if self.on_pause:
            self.on_pause()

    def _on_stop(self):
        self._exit_audition()
        self.engine.stop()
        self.btn_play.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_fade.setEnabled(False)
        self._reset_play_timer()
        if self.on_manual_stop:
            self.on_manual_stop()

    def clear_loaded_song(self):
        """Zeigt wieder "keine Datei geladen" (intern#212, Song geloescht).

        Nur die Oberflaeche: Die Audiodaten bleiben in der Engine, bis der
        naechste Song geladen wird. update_display() laesst den Player ohne
        Datei in Ruhe, damit btn_play aus bleibt; ohne Play-Knopf startet
        auch keine Rule (die klickt btn_play).
        """
        self._current_filename = None
        self.label_file.setText(_t("no_file_loaded"))
        self.label_status.setText(_t("status_ready"))
        for btn in (self.btn_play, self.btn_audition, self.btn_pause,
                    self.btn_stop, self.btn_fade):
            btn.setEnabled(False)
        self.slider_position.setEnabled(False)
        self.slider_position.blockSignals(True)
        self.slider_position.setValue(0)
        self.slider_position.blockSignals(False)
        self.label_time_current.setText(fmt_precise(0.0))
        self.label_time_total.setText(f" / {fmt_time(0.0)}")
        self.label_loop_count.setVisible(False)
        self._reset_play_timer()

    def has_file(self) -> bool:
        """True, solange der Player eine Datei anzeigt (geladen, nicht geloescht)."""
        return self._current_filename is not None

    def _reset_play_timer(self):
        """Timer zuruecksetzen (Stop, Song-Ende, Fade-Ende)."""
        self._play_start_time = None
        self._timer_warn_state = 0
        self.label_play_timer.setText("00:00")
        self._update_timer_style()

    def _update_timer_style(self):
        """Timer-Label Hintergrundfarbe je nach Warnstufe setzen."""
        timer_px = self._theme_font_px + 2   # Dauer-Timer: z.B. 15 px bei Standard
        base = f"font-size: {timer_px}px; font-family: monospace; font-weight: bold; border-radius: 4px; padding: 2px 4px;"
        if self._timer_warn_state == 2:
            bg = self._skin_mgr.color("warning", "#ef4444") if self._skin_mgr else "#ef4444"
            self.label_play_timer.setStyleSheet(f"{base} background-color: {bg}; color: white;")
        elif self._timer_warn_state == 1:
            bg = self._skin_mgr.color("timer_warn1", "#f59e0b") if self._skin_mgr else "#f59e0b"
            self.label_play_timer.setStyleSheet(f"{base} background-color: {bg}; color: white;")
        else:
            self.label_play_timer.setStyleSheet(f"{base} background-color: transparent;")

    def update_skin(self):
        """Theme-abhaengige Styles neu anwenden — nach Skin-Wechsel aufrufen."""
        sm = self._skin_mgr
        if not sm:
            return
        text      = sm.color("text",          "#f0f0f0")
        text_dim  = sm.color("text_dim",      "#999999")
        widget_bg = sm.color("widget_bg",     "#363636")
        muted_bg  = sm.color("muted_bg",      "#424242")
        border    = sm.color("border",        "#555555")
        btn_bg    = sm.color("button_bg",     "#615f8b")
        btn_hov   = sm.color("button_hover",  "#7a78a5")
        btn_pre   = sm.color("button_pressed","#4e4c73")
        btn_txt   = sm.color("button_text",   "#ffffff")
        muted_txt = sm.color("muted_text",    "#999999")

        # Theme-Schriftgroesse als Zahl (z.B. "13px" → 13)
        try:
            font_px = int(sm.font_size.replace("px", "").strip())
        except (ValueError, AttributeError):
            font_px = 13
        self._theme_font_px = font_px

        # Info-Streifen
        self._info_frame.setStyleSheet(f"""
            QFrame#PlayerInfoStrip {{
                background-color: {muted_bg};
                border-radius: 8px;
            }}
            QFrame#PlayerInfoStrip QLabel {{
                color: {text};
                background-color: transparent;
            }}
            QFrame#PlayerInfoStrip QLabel[infoHeader="true"] {{
                color: {text_dim};
                font-size: {font_px - 2}px;
            }}
            QFrame#PlayerInfoStrip QPushButton {{
                padding: 1px 4px;
                font-size: {font_px - 1}px;
            }}
        """)
        self._timer_border_color = muted_bg  # fuer Rueckwaertskompatibilitaet
        # Kaffeetassen-Icon in neuer Theme-Textfarbe neu rendern
        if hasattr(self, "btn_break"):
            self._apply_break_icon()

        # Info-Strip Wert-Labels: theme-relativ (groesser als Header, kleiner als Titel)
        val_px = font_px + 1   # Werte: z.B. 14 px bei Standard-Theme
        # BL-144: Basis-Stil merken, damit die Warnfarbe nur die Farbe tauscht
        # und nicht Schriftgroesse/Monospace verliert.
        self._bpm_base_px = val_px
        self._bpm_base_color = text
        self._apply_bpm_style()
        self.label_loop_count.setStyleSheet(
            f"font-size: {val_px}px; font-family: monospace; font-weight: bold; color: {text}; background: transparent;")

        # Player-Karte
        self._card.setStyleSheet(f"""
            QFrame#PlayerCard {{
                background-color: {widget_bg};
                border-radius: 10px;
                border: 1px solid {border};
            }}
            QFrame#PlayerCard QLabel {{
                color: {text};
                background-color: transparent;
            }}
        """)

        # Zeitanzeige: aktuelle Zeit gross+fett, Gesamtzeit gedimmt
        self.label_time_current.setStyleSheet(
            f"font-size: 28px; font-family: monospace; font-weight: bold; color: {text};")
        self.label_time_total.setStyleSheet(
            f"font-size: 18px; font-family: monospace; color: {text_dim};")

        # Song-Titel: Farben merken, Font-Groesse wird von _update_title_font gesetzt
        self._title_text_color = text
        self._title_dim_color  = text_dim
        # Titel-Label: aktuell berechnete Groesse beibehalten (Minimum = font_px)
        fs = max(font_px, self._title_font_px)
        self.label_file.setStyleSheet(
            f"font-size: {fs}px; font-weight: bold; color: {text}; background: transparent;")
        # Status-Label: fest klein, skaliert NICHT mit dem Titel
        self.label_status.setStyleSheet(
            f"font-size: {font_px - 2}px; color: {text_dim}; background: transparent;")
        # BL-138: Label-Info — gleiche Attribute wie Status (rechts, dim, klein)
        self.label_label_info.setStyleSheet(
            f"font-size: {font_px - 2}px; color: {text_dim}; background: transparent;")

        # Play-Button: volle Breite, Akzentfarbe
        self.btn_play.setStyleSheet(f"""
            QPushButton {{
                background-color: {btn_bg};
                color: {btn_txt};
                border: none;
                border-radius: 6px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:hover   {{ background-color: {btn_hov}; }}
            QPushButton:pressed {{ background-color: {btn_pre}; }}
            QPushButton:disabled {{ background-color: {muted_bg}; color: {text_dim}; }}
        """)

        # SVG-Icons mit button_text-Farbe; deaktiviert in derselben Farbe wie
        # der Text (Play: eigenes Stylesheet oben, Rest: skin.qss)
        self.btn_play.setIcon(_make_icon(_SVG_PLAY,  btn_txt, text_dim))
        self.btn_pause.setIcon(_make_icon(_SVG_PAUSE, btn_txt, muted_txt))
        self.btn_stop.setIcon(_make_icon(_SVG_STOP,  btn_txt, muted_txt))
        self.btn_fade.setIcon(_make_icon(_SVG_FADE,  btn_txt, muted_txt))

        # Sektionsleiste + Timer-Style
        self.section_bar.update_colors()
        self._update_timer_style()

    # BL-144 ----------------------------------------------------------------

    def _apply_target_bpm(self):
        """Setzt das heutige Tempo so, dass der Song die Ziel-BPM der Lokation trifft.

        Wird bei JEDEM Songwechsel gerechnet (nach _base_bpm). Eine manuelle
        Korrektur am heutigen Tempo bleibt fuer den laufenden Song erhalten und
        wird erst beim naechsten Song wieder ueberschrieben — so kann der Caller
        bewusst abweichen (Hot Hash schneller, Workshop langsamer).

        Ohne hinterlegte BPM (base_bpm = 0) bleibt das Tempo auf 100 %.
        Ist die Ziel-BPM ausserhalb des Stellbereichs, wird gekappt und in der
        BPM-Anzeige markiert.
        """
        self._target_bpm_missed = False
        if self._target_bpm <= 0:
            return

        if self._base_bpm <= 0:
            # Kein BPM-Wert am Song — Ziel nicht berechenbar, neutral lassen
            self.spin_today_tempo.setValue(100)
            self._target_bpm_missed = True
            return

        song_tempo = self.spin_tempo.value() / 100.0
        ist_bpm = self._base_bpm * song_tempo
        if ist_bpm <= 0:
            self.spin_today_tempo.setValue(100)
            self._target_bpm_missed = True
            return

        pct = round(self._target_bpm / ist_bpm * 100)
        lo = self.spin_today_tempo.minimum()
        hi = self.spin_today_tempo.maximum()
        if pct < lo or pct > hi:
            self._target_bpm_missed = True
            pct = max(lo, min(hi, pct))
        self.spin_today_tempo.setValue(int(pct))

    def _update_bpm_display(self):
        """BPM-Anzeige aktualisieren: base_bpm * song_tempo * today_tempo."""
        if self._base_bpm <= 0:
            # BL-144: bei aktiver Ziel-BPM sichtbar machen, dass sie hier nicht greift
            self.label_bpm.setText("—" if self._target_bpm > 0 else "")
            self.label_bpm.setToolTip(_t("bpm_target_no_base") if self._target_bpm > 0 else "")
            self._set_bpm_warning(self._target_bpm > 0)
            return
        song_tempo = self.spin_tempo.value() / 100.0
        today_tempo = self.spin_today_tempo.value() / 100.0
        effective_bpm = self._base_bpm * song_tempo * today_tempo
        self.label_bpm.setText(f"{effective_bpm:.1f}")
        # BL-144: Ziel nicht erreichbar → Anzeige markieren
        self._set_bpm_warning(self._target_bpm_missed)
        if self._target_bpm_missed:
            self.label_bpm.setToolTip(_t("bpm_target_missed",
                                         target=f"{self._target_bpm:.0f}"))
        elif self._target_bpm > 0:
            self.label_bpm.setToolTip(_t("bpm_target_active",
                                         target=f"{self._target_bpm:.0f}"))
        else:
            self.label_bpm.setToolTip("")

    def _apply_bpm_style(self):
        """Setzt den Stil der BPM-Anzeige — Warnfarbe tauscht NUR die Farbe.

        Der uebrige Stil (Groesse, Monospace, Bold) kommt aus dem Skin und muss
        erhalten bleiben, sonst springt das Label beim Songwechsel im Aussehen.
        """
        px = getattr(self, "_bpm_base_px", self._theme_font_px + 1)
        normal = getattr(self, "_bpm_base_color", "#f0f0f0")
        if getattr(self, "_target_bpm_missed", False):
            col = (self._skin_mgr.color("warning", "#ef4444")
                   if self._skin_mgr else "#ef4444")
        else:
            col = normal
        self.label_bpm.setStyleSheet(
            f"font-size: {px}px; font-family: monospace; font-weight: bold; "
            f"color: {col}; background: transparent;")

    def _set_bpm_warning(self, active: bool):
        """Markiert die BPM-Anzeige, wenn die Ziel-BPM nicht erreicht wurde."""
        self._target_bpm_missed = active
        self._apply_bpm_style()

    def _on_fade_out(self):
        self.engine.start_fade_out(self._fade_duration)
        self.btn_fade.setEnabled(False)
        self.btn_pause.setEnabled(False)
        self.label_status.setText(_t("status_fade_out"))

    # BL-074 ----------------------------------------------------------------

    def _on_audition(self):
        """Audition-Button geklickt: Sekundaerkanal ein/aus."""
        if self._audition_active:
            # Toggle aus: Audition stoppen
            self._exit_audition()
            self.engine.stop()
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.btn_fade.setEnabled(False)
            self.btn_play.setEnabled(True)
            self.label_status.setText(_t("status_stopped"))
            return
        if not self.engine.is_loaded():
            self.btn_audition.setChecked(False)
            return
        if self.on_audition:
            self.on_audition()  # MainWindow schaltet Geraet + Lautstaerke
        self._audition_active = True
        self.engine.seek(0)
        self.engine.play()
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.btn_fade.setEnabled(True)
        self.label_status.setText(_t("status_audition"))

    def _exit_audition(self):
        """Beendet den Audition-Modus ohne Engine zu stoppen."""
        if not self._audition_active:
            return
        self._audition_active = False
        self.btn_audition.setChecked(False)
        if self.on_exit_audition:
            self.on_exit_audition()  # MainWindow stellt Primaerkanal wieder her


class LoopWidget(QWidget):
    """Loop-Modul: NEU-Button, Loop-In/Out setzen, Beat Snap, Loop-Test, Loop an/aus.

    Der NEU-Button oeffnet den FileDialog zum Hinzufuegen neuer Songs.
    Loop-Einstellungen werden typischerweise einmal gesetzt und selten geaendert,
    daher passen sie gut zusammen mit dem NEU-Button.
    """

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.on_new_clicked = None  # Callback: neuer Song laden
        self.on_new_dropped = None  # Callback(list[str]): Dateien/Ordner gedroppt (BL-179)
        self.on_set_marker = None   # Callback: Custom-Marker an aktueller Pos setzen (BL-185)
        self._current_filepath = None  # Fuer Beat-Grid-Berechnung
        self._current_bpm = None       # Fuer Beat-Grid-Berechnung
        self._beat_grid_cache = {}     # filepath → beat_times
        self._snap_worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 4)   # Bottom-Padding bewusst klein
        layout.setSpacing(4)

        # NEU-Button (oeffnet FileDialog; nimmt zusaetzlich Drag&Drop an, BL-179)
        self.btn_new = _ImportDropButton(_t("btn_new"))
        self.btn_new.setToolTip(_t("tooltip_new_song"))
        self.btn_new.setMinimumHeight(32)
        self.btn_new.clicked.connect(self._on_new)
        self.btn_new.on_paths_dropped = self._on_new_dropped
        layout.addWidget(self.btn_new)

        # Loop Active Checkbox — wird spaeter in den Player verschoben
        self.chk_loop = QCheckBox(_t("chk_loop_active"))
        self.chk_loop.toggled.connect(self._on_loop_toggled)

        # Loop-Zeiten nebeneinander
        time_row = QHBoxLayout()
        time_row.setSpacing(4)
        self.label_loop_in = QLabel(_t("label_loop_in", time="00:00.00"))
        self.label_loop_in.setStyleSheet(
            "font-size: 13px; font-family: monospace; color: green;"
        )
        self.label_loop_in.setAlignment(Qt.AlignCenter)
        time_row.addWidget(self.label_loop_in)
        self.label_loop_out = QLabel(_t("label_loop_out", time="00:00.00"))
        self.label_loop_out.setStyleSheet(
            "font-size: 13px; font-family: monospace; color: red;"
        )
        self.label_loop_out.setAlignment(Qt.AlignCenter)
        time_row.addWidget(self.label_loop_out)
        layout.addLayout(time_row)

        # Beide Button-Reihen in EINEM Raster aus vier gleich breiten Spalten,
        # damit die Kanten fluchten (intern#158). Zwei getrennte Zeilen-Layouts
        # verteilen den Platz je fuer sich: drei Abstaende oben, zwei unten.
        # Ignored: die Textbreite zaehlt nicht, sonst waeren die Spalten bei
        # langen Texten (de/en/ja) ungleich breit. Textumbruch bei Platzmangel.
        btn_grid = QGridLayout()
        btn_grid.setHorizontalSpacing(4)
        btn_grid.setVerticalSpacing(layout.spacing())
        for _col in range(4):
            btn_grid.setColumnStretch(_col, 1)
        _shrink = QSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)

        self.btn_set_in = QPushButton(_t("btn_set_loop_in").replace(" ", "\n"))
        self.btn_set_in.clicked.connect(self._on_set_in)
        self.btn_set_in.setEnabled(False)
        self.btn_set_in.setSizePolicy(_shrink)
        self.btn_set_in.setMinimumWidth(10)
        self.btn_set_in.setMinimumHeight(38)
        btn_grid.addWidget(self.btn_set_in, 0, 0)

        self.btn_clear_loop = QPushButton(_t("btn_clear_loop").replace(" ", "\n"))
        self.btn_clear_loop.clicked.connect(self._on_clear_loop)
        self.btn_clear_loop.setEnabled(False)
        self.btn_clear_loop.setSizePolicy(_shrink)
        self.btn_clear_loop.setMinimumWidth(10)
        self.btn_clear_loop.setMinimumHeight(38)
        btn_grid.addWidget(self.btn_clear_loop, 0, 1)

        self.btn_set_out = QPushButton(_t("btn_set_loop_out").replace(" ", "\n"))
        self.btn_set_out.clicked.connect(self._on_set_out)
        self.btn_set_out.setEnabled(False)
        self.btn_set_out.setSizePolicy(_shrink)
        self.btn_set_out.setMinimumWidth(10)
        self.btn_set_out.setMinimumHeight(38)
        btn_grid.addWidget(self.btn_set_out, 0, 2)

        _test_txt = _t("btn_loop_test")
        # Nur nach erstem Wort umbrechen: "Loop testen\n(5s)"
        _parts = _test_txt.split(" ", 1)
        self.btn_test = QPushButton("\n".join(_parts) if len(_parts) > 1 else _test_txt)
        self.btn_test.clicked.connect(self._on_loop_test)
        self.btn_test.setEnabled(False)
        self.btn_test.setSizePolicy(_shrink)
        self.btn_test.setMinimumWidth(10)
        self.btn_test.setMinimumHeight(38)
        btn_grid.addWidget(self.btn_test, 0, 3)

        # Zweite Reihe: Find Loop ueber zwei Spalten, Beat Snap, Set Marker
        self.btn_find_loop = QPushButton(_t("btn_find_loop").replace(" ", "\n"))
        self.btn_find_loop.setToolTip(_t("tooltip_find_loop"))
        self.btn_find_loop.setEnabled(False)
        self.btn_find_loop.setSizePolicy(_shrink)
        self.btn_find_loop.setMinimumWidth(10)
        self.btn_find_loop.setMinimumHeight(38)
        btn_grid.addWidget(self.btn_find_loop, 1, 0, 1, 2)

        self.btn_snap = QPushButton(_t("btn_snap").replace(" ", "\n"))
        self.btn_snap.setToolTip(_t("tooltip_snap"))
        self.btn_snap.clicked.connect(self._on_beat_snap)
        self.btn_snap.setEnabled(False)
        self.btn_snap.setSizePolicy(_shrink)
        self.btn_snap.setMinimumWidth(10)
        self.btn_snap.setMinimumHeight(38)
        btn_grid.addWidget(self.btn_snap, 1, 2)

        # BL-185: Custom-Jump-Marker an der aktuellen Abspielposition setzen
        self.btn_set_marker = QPushButton(_t("btn_set_marker").replace(" ", "\n"))
        self.btn_set_marker.setToolTip(_t("tooltip_set_marker"))
        self.btn_set_marker.clicked.connect(self._on_set_marker)
        self.btn_set_marker.setEnabled(False)
        self.btn_set_marker.setSizePolicy(_shrink)
        self.btn_set_marker.setMinimumWidth(10)
        self.btn_set_marker.setMinimumHeight(38)
        btn_grid.addWidget(self.btn_set_marker, 1, 3)
        layout.addLayout(btn_grid)

        self.label_length = QLabel(_t("label_loop_length_default"))
        self.label_length.setAlignment(Qt.AlignCenter)
        self.label_length.setStyleSheet("font-size: 12px; font-family: monospace;")
        layout.addWidget(self.label_length)
        # Kein addStretch() — kein ungenutzter Leerraum am unteren Rand

    def set_song_info(self, filepath: str, bpm: float = None):
        """Speichert Filepath und BPM fuer Beat-Grid-Berechnung."""
        self._current_filepath = filepath
        self._current_bpm = bpm

    def apply_song_settings(self, song: Song):
        """Setzt Loop-Marker und Offset aus den gespeicherten Song-Werten."""
        if song.loop_in > 0:
            self.engine.set_loop_in(song.loop_in)
        if song.loop_out > 0:
            self.engine.set_loop_out(song.loop_out)
        if song.loop_offset_ms != 0.0:
            self.engine.set_loop_offset_ms(song.loop_offset_ms)
        else:
            self.engine.set_loop_offset_ms(0)

    def update_display(self):
        li = self.engine.loop_in_seconds
        lo = self.engine.loop_out_seconds
        self.label_loop_in.setText(_t("label_loop_in", time=fmt_precise(li)))
        self.label_loop_out.setText(_t("label_loop_out", time=fmt_precise(lo)))

        length = lo - li
        if length > 0:
            self.label_length.setText(_t("label_loop_length", time=fmt_precise(length)))

        loaded = self.engine.is_loaded()
        self.btn_set_in.setEnabled(loaded)
        self.btn_set_out.setEnabled(loaded)
        self.btn_clear_loop.setEnabled(loaded)
        self.btn_test.setEnabled(loaded)
        self.btn_find_loop.setEnabled(loaded)
        self.btn_set_marker.setEnabled(loaded)
        # Beat Snap nur aktiv wenn Song geladen UND Loop-Punkte manuell gesetzt
        has_custom_loop = loaded and (li > 0.1 or (lo > 0 and lo < self.engine.get_original_duration() - 0.5))
        self.btn_snap.setEnabled(has_custom_loop)

    def _on_new(self):
        """NEU-Button: delegiert ans Hauptfenster zum Laden eines neuen Songs."""
        if self.on_new_clicked:
            self.on_new_clicked()

    def _on_new_dropped(self, paths):
        """Drop auf den NEU-Button: delegiert ans Hauptfenster (BL-179)."""
        if self.on_new_dropped:
            self.on_new_dropped(paths)

    def _on_set_marker(self):
        """Set-Marker-Button: delegiert ans Hauptfenster (braucht Song + DB)."""
        if self.on_set_marker:
            self.on_set_marker()

    def _on_loop_toggled(self, checked):
        self.engine.set_loop_active(checked)

    def _on_set_in(self):
        self.engine.set_loop_in_at_current()
        self._sync_loop_to_song_data()
        # Variante C: sofort persistieren statt auf Song-Wechsel zu warten.
        self._save_loop_to_db()

    def _on_set_out(self):
        self.engine.set_loop_out_at_current()
        self._sync_loop_to_song_data()
        self._save_loop_to_db()

    def _save_loop_to_db(self):
        """Schreibt loop_in/loop_out aus der Engine direkt in die DB
        (Variante C: keine Sammelspeicherung beim Song-Wechsel mehr)."""
        main_win = self.window()
        song = getattr(main_win, '_current_song', None)
        if not song or not song.id:
            return
        loop_in = self.engine.loop_in_seconds
        loop_out = self.engine.loop_out_seconds
        song.loop_in = loop_in
        song.loop_out = loop_out
        main_win.db.save_playback_settings(
            song.id, loop_in=loop_in, loop_out=loop_out)

    def _on_clear_loop(self):
        """Loop-Marker entfernen (In=0, Out=Songende)."""
        reply = QMessageBox.question(
            self, _t("btn_clear_loop"),
            _t("confirm_clear_loop"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.engine.set_loop_in(0.0)
        dur = self.engine.get_original_duration()
        self.engine.set_loop_out(dur)
        self.chk_loop.setChecked(False)
        self._sync_loop_to_song_data()
        self.update_display()
        # In DB speichern (clear_loop umgeht Safety-Guard)
        main_win = self.window()
        if hasattr(main_win, '_current_song') and main_win._current_song:
            main_win._current_song.loop_in = 0.0
            main_win._current_song.loop_out = 0.0
            main_win.db.clear_loop(main_win._current_song.id)

    def _sync_loop_to_song_data(self):
        """Aktualisiert Loop-SpinBoxes im Song-Daten-Widget."""
        main_win = self.window()
        if hasattr(main_win, 'song_data'):
            main_win.song_data.spin_loop_in.setValue(self.engine.loop_in_seconds)
            main_win.song_data.spin_loop_out.setValue(self.engine.loop_out_seconds)

    def _on_loop_test(self):
        self.engine.jump_to_loop_test()
        self.chk_loop.setChecked(True)

    def _on_beat_snap(self):
        """Beat Snap: Oeffnet den visuellen Beat Snap Dialog."""
        if not self._current_filepath:
            return

        # Cache pruefen
        if self._current_filepath in self._beat_grid_cache:
            self._open_snap_dialog(self._beat_grid_cache[self._current_filepath])
            return

        # Beat-Grid im Hintergrund berechnen
        self.btn_snap.setEnabled(False)
        self.btn_snap.setText(_t("btn_snap_working"))
        self._snap_worker = BeatSnapWorker(
            self._current_filepath, bpm=self._current_bpm
        )
        self._snap_worker.finished.connect(self._on_snap_finished)
        self._snap_worker.error.connect(self._on_snap_error)
        self._snap_worker.start()

    def _on_snap_finished(self, result):
        """Callback: Beat-Grid wurde berechnet."""
        bpm, beat_times = result
        # Cachen
        if self._current_filepath:
            self._beat_grid_cache[self._current_filepath] = beat_times
        self.btn_snap.setText(_t("btn_snap"))
        self.btn_snap.setEnabled(True)
        self._open_snap_dialog(beat_times)

    def _on_snap_error(self, msg):
        """Callback: Beat-Grid-Berechnung fehlgeschlagen."""
        print(f"[BeatSnap] Fehler: {msg}")
        self.btn_snap.setText(_t("btn_snap"))
        self.btn_snap.setEnabled(True)

    def _open_snap_dialog(self, beat_times):
        """Oeffnet den visuellen Beat Snap Dialog."""
        from beat_snap_dialog import BeatSnapDialog

        # SkinManager vom Hauptfenster holen
        skin_mgr = None
        main_win = self.window()
        if hasattr(main_win, '_skin_mgr'):
            skin_mgr = main_win._skin_mgr

        dlg = BeatSnapDialog(
            engine=self.engine,
            filepath=self._current_filepath,
            beat_times=beat_times,
            bpm=self._current_bpm or 0,
            skin_mgr=skin_mgr,
            parent=self
        )
        dlg.accepted_snap.connect(self._on_snap_applied)

        # Tutorial beim ersten Oeffnen anzeigen
        if hasattr(main_win, 'tutorial_engine') and main_win.tutorial_engine:
            from tutorial_definitions import BEAT_SNAP_DIALOG_STEPS
            engine = main_win.tutorial_engine
            steps = BEAT_SNAP_DIALOG_STEPS
            QTimer.singleShot(300, lambda: engine.show_dialog_tutorial(
                dlg, "beat_snap", steps
            ))

        # Auto-Advance sperren + Play-Log unterdruecken solange Beat Snap offen ist
        if hasattr(main_win, '_beat_snap_active'):
            main_win._beat_snap_active = True
        if hasattr(main_win, '_suppress_play_log'):
            main_win._suppress_play_log = True
        dlg.exec()
        if hasattr(main_win, '_beat_snap_active'):
            main_win._beat_snap_active = False
        if hasattr(main_win, '_suppress_play_log'):
            main_win._suppress_play_log = False

    def _on_snap_applied(self, new_in, new_out):
        """Callback: User hat Snap im Dialog bestaetigt."""
        self.engine.set_loop_in(new_in)
        self.engine.set_loop_out(new_out)
        self.update_display()

        main_win = self.window()
        song = getattr(main_win, '_current_song', None)

        # Loop-Offset automatisch messen und anwenden
        offset_ms = None
        result = self.engine.measure_loop_offset(auto_apply=True)
        if result:
            offset_samples, offset_ms, corr = result
            if song:
                song.loop_offset_ms = offset_ms
            if hasattr(main_win, 'song_data'):
                main_win.song_data.spin_loop_offset.setValue(offset_ms)

        # Variante C: loop_in/loop_out (+ ggf. offset) sofort und gezielt in DB.
        # Kein _save_current_song mehr -> keine Snapshot-Wackelei moeglich.
        if song and song.id:
            loop_in = self.engine.loop_in_seconds
            loop_out = self.engine.loop_out_seconds
            song.loop_in = loop_in
            song.loop_out = loop_out
            kwargs = dict(loop_in=loop_in, loop_out=loop_out)
            if offset_ms is not None:
                kwargs['loop_offset_ms'] = offset_ms
            main_win.db.save_playback_settings(song.id, **kwargs)
            # To-Do-Marker abraeumen: hatte der Bulk-Beat-Snap diesen Song als
            # 'CHECK: BEATSNAP' geflaggt, ist er jetzt manuell gesnappt → Marker
            # entfernen (analog zu CHECK: START beim manuellen Singing-Start).
            try:
                gid = main_win.db.get_genre_id_by_name(CHECK_BEATSNAP_GENRE_NAME)
                if gid and gid > 0:
                    main_win.db.remove_song_genre(song.id, gid)
            except Exception as e:
                print(f"[CHECK:BEATSNAP] Marker abraeumen fehlgeschlagen: {e}")

        self._sync_loop_to_song_data()
