"""Pausen- und Foto-Anzeige fuer Callers Caddy (BL-201, Stufe 10).

BreakWidget/BreakDisplay (Pausen-Countdown) und PhotoWidget (Foto-Anzeige).
Zirkelfrei: keine Rueckbezuege auf main.py.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QComboBox, QInputDialog, QStackedWidget,
)
from PySide6.QtCore import Qt, QTimer, Signal, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QCursor, QPixmap

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
        self._total = float(self.DEFAULT_SECONDS)
        self._remaining = float(self.DEFAULT_SECONDS)
        self._running = False
        self._finished = False
        self._last_mono = None
        self._music_playing = False

        self._timer = QTimer(self)
        self._timer.setInterval(200)  # 5x/s -> fluessiger Fortschrittsbalken
        self._timer.timeout.connect(self._tick)

        self._build_ui()
        self._refresh_views()
        self._update_buttons()

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
        seconds = max(1, int(seconds))
        self._total = float(seconds)
        if not self._running:
            self._remaining = float(seconds)
            self._finished = False
            self._update_buttons()
            self._refresh_views()

    # ---- Skin ----
    def set_skin(self, skin_mgr):
        self._skin_mgr = skin_mgr
        self._display.set_skin(skin_mgr)

    # ---- Timer ----
    def _tick(self):
        import time as _t
        now = _t.monotonic()
        if self._last_mono is None:
            self._last_mono = now
            return
        dt = now - self._last_mono
        self._last_mono = now
        if self._running:
            self._remaining -= dt
            if self._remaining <= 0:
                self._remaining = 0.0
                self._running = False
                self._finished = True
                self._timer.stop()
                self._update_buttons()
                if callable(self.on_break_finished):
                    self.on_break_finished()
        self._refresh_views()

    def _toggle_start(self):
        if self._running:
            self._running = False
            self._timer.stop()
            self._update_buttons()
            self._refresh_views()
        else:
            self._start_countdown()

    def _start_countdown(self):
        """Countdown starten (von vorn, falls abgelaufen/leer)."""
        # Frisch = volle Restzeit oder abgelaufen; Fortsetzen nach Anhalten nicht.
        # Anhalten im ersten Tick oder neue Dauer per Klick zaehlt bewusst als frisch.
        fresh = (self._finished or self._remaining <= 0
                 or self._remaining >= self._total)
        if self._finished or self._remaining <= 0:
            self._remaining = self._total
            self._finished = False
        self._running = True
        self._last_mono = None
        self._timer.start()
        self._update_buttons()
        self._refresh_views()
        if fresh and callable(self.on_break_started):
            self.on_break_started(self._music_playing)

    def _reset(self):
        self._running = False
        self._finished = False
        self._timer.stop()
        self._remaining = self._total
        self._update_buttons()
        self._refresh_views()

    def end_break(self) -> bool:
        """Laufende Pause von aussen beenden (intern#130: manuelles Play des
        Callers). Setzt den Countdown zurueck wie der Reset-Knopf und feuert
        bewusst KEIN on_break_finished (abgebrochen, nicht abgelaufen).
        False, wenn die Pausen-Uhr gar nicht lief."""
        if not self._running:
            return False
        self._reset()
        return True

    def _edit_duration(self):
        """Klick auf die Uhr: Countdown pausieren und Dauer neu setzen."""
        self._running = False
        self._timer.stop()
        cur = int(round(self._total))
        text, ok = QInputDialog.getText(
            self, _t("break_set_title"), _t("break_set_prompt"),
            text=f"{cur // 60:02d}:{cur % 60:02d}")
        if ok:
            secs = self._parse_duration(text)
            if secs and secs > 0:
                self._total = float(secs)
                self._remaining = float(secs)
                self._finished = False
        self._update_buttons()
        self._refresh_views()

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

    def _update_buttons(self):
        self._btn_start.setText(_t("break_pause") if self._running
                                else _t("break_start"))

    def _refresh_views(self):
        self._display.set_values(self._remaining, self._total, self._finished)

    # ---- Play last Song (Wartemusik, ohne Historie) ----
    def _toggle_play_last(self):
        if self._music_playing:
            if callable(self.on_stop_last_song):
                self.on_stop_last_song()
            self._music_playing = False
        else:
            if callable(self.on_play_last_song):
                ok = self.on_play_last_song(self._total)
                self._music_playing = bool(ok)
                if ok:
                    # Pausen-Uhr synchron mitlaufen lassen (frisch von total)
                    self._remaining = self._total
                    self._finished = False
                    self._start_countdown()
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
    def _apply_duration(self, duration_seconds):
        """Setzt Dauer/Restzeit frisch, wenn eine gueltige Dauer uebergeben wird."""
        if duration_seconds and duration_seconds > 0:
            secs = max(1, int(round(duration_seconds)))
            self._total = float(secs)
            self._remaining = float(secs)
            self._finished = False

    def start_break(self, duration_seconds=None):
        """Pause starten (Countdown). Optional mit vorgegebener Dauer.

        Fuer Rule-Aktion "Start Break". Startet den Countdown von vorn.
        """
        self._apply_duration(duration_seconds)
        # Frischer Start auch wenn schon ein (alter) Countdown lief
        self._remaining = self._total
        self._finished = False
        self._start_countdown()

    def start_break_with_last_song(self, duration_seconds=None):
        """Pause starten und den zuletzt gespielten Song als Wartemusik abspielen.

        Fuer Rule-Aktion "Start Break with last Song". Nutzt denselben Pfad wie
        der Play-Last-Button; startet nur, wenn nicht bereits Wartemusik laeuft.
        """
        self._apply_duration(duration_seconds)
        if not self._music_playing:
            # _toggle_play_last spielt den letzten Song (Dauer = self._total)
            # und startet den Countdown selbst.
            self._toggle_play_last()
        else:
            # Wartemusik laeuft bereits: nur den Countdown neu anstossen.
            self._remaining = self._total
            self._finished = False
            self._start_countdown()


class PhotoWidget(QWidget):
    """Schnappschuss vom PilotSquare — nur im RAM, kein Speichern.

    Lazy-Init: wird erst beim ersten Sichtbar-werden erstellt.
    Kamera starten → Vorschau sehen → Foto schiessen → Bild bleibt
    bis zum naechsten Foto oder Kamera-Neustart.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._camera = None
        self._capture_session = None
        self._image_capture = None
        self._camera_active = False
        self._last_image = None  # QImage im RAM
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # --- Toolbar ---
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        # Kamera-Auswahl
        self._combo_camera = QComboBox()
        self._combo_camera.setMinimumWidth(150)
        toolbar.addWidget(self._combo_camera)

        self._btn_toggle_cam = QPushButton(_t("photo_start_camera"))
        self._btn_toggle_cam.clicked.connect(self._on_toggle_camera)
        toolbar.addWidget(self._btn_toggle_cam)

        self._btn_capture = QPushButton(_t("photo_capture"))
        self._btn_capture.clicked.connect(self._on_capture)
        self._btn_capture.setEnabled(False)
        toolbar.addWidget(self._btn_capture)

        # Kamera-Liste befuellen (nach Button-Erstellung!)
        self._refresh_cameras()

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # --- Anzeige-Bereich: Stack mit Foto und Video ---
        self._stack = QStackedWidget()

        # Seite 0: Foto-Anzeige (QLabel mit Pixmap)
        self._label_photo = QLabel()
        self._label_photo.setAlignment(Qt.AlignCenter)
        self._label_photo.setMinimumSize(320, 240)
        self._label_photo.setStyleSheet("background: #222;")
        self._label_photo.setText(_t("photo_no_photo"))
        self._stack.addWidget(self._label_photo)

        # Seite 1: Kamera-Vorschau (QVideoWidget)
        from PySide6.QtMultimediaWidgets import QVideoWidget
        self._video_widget = QVideoWidget()
        self._video_widget.setMinimumSize(320, 240)
        self._stack.addWidget(self._video_widget)

        layout.addWidget(self._stack, 1)

    def _refresh_cameras(self):
        """Aktualisiert die Kamera-Liste."""
        from PySide6.QtMultimedia import QMediaDevices
        self._combo_camera.clear()
        self._devices = QMediaDevices.videoInputs()
        if not self._devices:
            self._combo_camera.addItem(_t("photo_no_camera"))
            self._btn_toggle_cam.setEnabled(False)
        else:
            for dev in self._devices:
                self._combo_camera.addItem(dev.description())
            self._btn_toggle_cam.setEnabled(True)

    def _on_toggle_camera(self):
        """Kamera starten/stoppen."""
        if self._camera_active:
            self._stop_camera()
        else:
            self._start_camera()

    def _start_camera(self):
        """Startet die Kamera-Vorschau."""
        from PySide6.QtMultimedia import QCamera, QMediaCaptureSession, QImageCapture
        idx = self._combo_camera.currentIndex()
        if idx < 0 or idx >= len(self._devices):
            return

        self._camera = QCamera(self._devices[idx])
        self._capture_session = QMediaCaptureSession()
        self._capture_session.setCamera(self._camera)
        self._capture_session.setVideoOutput(self._video_widget)
        self._image_capture = QImageCapture(self._camera)
        self._capture_session.setImageCapture(self._image_capture)
        self._image_capture.imageCaptured.connect(self._on_image_captured)
        self._image_capture.errorOccurred.connect(self._on_capture_error)

        self._camera.start()
        self._camera_active = True
        self._stack.setCurrentIndex(1)  # Video-Vorschau
        self._btn_toggle_cam.setText(_t("photo_stop_camera"))
        self._btn_capture.setEnabled(True)
        self._combo_camera.setEnabled(False)

    def _stop_camera(self):
        """Stoppt die Kamera und zeigt letztes Foto (falls vorhanden)."""
        if self._camera:
            self._camera.stop()
            self._camera = None
        self._capture_session = None
        self._image_capture = None
        self._camera_active = False
        self._stack.setCurrentIndex(0)  # Foto-Anzeige
        self._btn_toggle_cam.setText(_t("photo_start_camera"))
        self._btn_capture.setEnabled(False)
        self._combo_camera.setEnabled(True)
        self._show_last_image()

    def _on_capture(self):
        """Foto aufnehmen."""
        if self._image_capture and self._image_capture.isReadyForCapture():
            self._image_capture.capture()

    def _on_image_captured(self, request_id, image):
        """Callback: Foto wurde aufgenommen (QImage im RAM behalten)."""
        self._last_image = image
        print(f"[Photo] Schnappschuss aufgenommen ({image.width()}x{image.height()})")
        # Kamera stoppen, Foto anzeigen
        self._stop_camera()

    def _on_capture_error(self, id, error, message):
        """Callback: Fehler bei der Aufnahme."""
        print(f"[Photo] Fehler: {message}")

    def _show_last_image(self):
        """Zeigt das letzte aufgenommene Bild im Label an."""
        if self._last_image is None:
            self._label_photo.setText(_t("photo_no_photo"))
            return
        pixmap = QPixmap.fromImage(self._last_image)
        scaled = pixmap.scaled(
            self._label_photo.size(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._label_photo.setPixmap(scaled)

    def resizeEvent(self, event):
        """Bei Groessenaenderung das Foto neu skalieren."""
        super().resizeEvent(event)
        if self._last_image is not None and not self._camera_active:
            self._show_last_image()
