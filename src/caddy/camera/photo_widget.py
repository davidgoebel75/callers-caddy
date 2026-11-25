"""Foto-Anzeige fuer Callers Caddy (BL-041): Kamera-Schnappschuss vom PilotSquare.

Bis intern#220 Teil von break_photo_widget.py. Zirkelfrei: keine Rueckbezuege
auf main.py.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QComboBox,
    QStackedWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from i18n import _t



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
