"""
Beat Snap Dialog — Visueller Loop-Feinabgleich mit Waveform + Beat-Grid.

Zeigt zwei Waveform-Ausschnitte (Loop-Out oben, Loop-In unten) mit
ueberlagerten Beat-Grid-Linien. Der Caller kann visuell und auditiv
pruefen ob die Loop-Punkte auf Beats liegen, und per Klick snappen.

Prozess:
  1. Dialog oeffnet sich → zeigt IST-Zustand (rote Marker in der Mitte)
  2. User kann untere Waveform per Drag verschieben (Loop-In anpassen)
  3. "Anpassen" → springt zum naechsten Beat
  4. "Vorhoeren" → Playback mit wanderndem Cursor
  5. "Uebernehmen" → aktuelle Positionen werden gesetzt
  6. "Schliessen" ohne Uebernehmen → Rueckfrage
"""

import numpy as np
import soundfile as sf

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QWidget,
    QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QCursor

from i18n import _t
from zoom_wheel import install_ctrl_wheel_zoom


# ---------------------------------------------------------------------------
# Waveform-Widget: Zeichnet Ausschnitt mit Beat-Grid + Marker
# ---------------------------------------------------------------------------

class WaveformWidget(QWidget):
    """Zeichnet eine Waveform mit Beat-Grid-Overlay und Marker-Linie.

    Optionaler Drag-Support: Wenn draggable=True, kann der User die
    Waveform per Maus horizontal verschieben.
    """

    # Signal: Emittiert Delta in Sekunden bei Drag
    dragged = Signal(float)

    def __init__(self, parent=None, draggable=False):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.setMinimumWidth(500)

        self._samples = None
        self._sample_rate = 0
        self._start_sec = 0.0
        self._end_sec = 0.0

        self._marker_sec = 0.0
        self._orig_marker_sec = None  # Zeigt Original-Position als duenne rote Linie
        self._cursor_sec = None

        self._beat_times = []
        self._downbeat_indices = set()

        # Drag
        self._draggable = draggable
        self._drag_active = False
        self._drag_start_x = 0

        if draggable:
            self.setCursor(QCursor(Qt.OpenHandCursor))

        # Farben (Defaults fuer Dark Theme)
        self._bg_color = QColor("#2b2b2b")
        self._wave_color = QColor("#615f8b")
        self._beat_color = QColor("#666666")
        self._downbeat_color = QColor("#cccccc")
        self._marker_color = QColor("#ef4444")
        self._snap_color = QColor("#22c55e")
        self._text_color = QColor("#f0f0f0")
        self._cursor_color = QColor("#ffffff")

    def set_colors(self, bg, wave, beat, downbeat, marker, snap, text, cursor="#ffffff"):
        self._bg_color = QColor(bg)
        self._wave_color = QColor(wave)
        self._beat_color = QColor(beat)
        self._downbeat_color = QColor(downbeat)
        self._marker_color = QColor(marker)
        self._snap_color = QColor(snap)
        self._text_color = QColor(text)
        self._cursor_color = QColor(cursor)
        self.update()

    def set_data(self, samples, sample_rate, start_sec, end_sec):
        self._samples = samples
        self._sample_rate = sample_rate
        self._start_sec = start_sec
        self._end_sec = end_sec
        self.update()

    def set_marker(self, marker_sec, orig_marker_sec=None):
        """Setzt den Marker (gruen = aktuell) und optional den Original-Marker (rot, duenn)."""
        self._marker_sec = marker_sec
        self._orig_marker_sec = orig_marker_sec
        self.update()

    def set_cursor(self, cursor_sec):
        self._cursor_sec = cursor_sec
        self.update()

    def set_beat_grid(self, beat_times, downbeat_indices=None):
        self._beat_times = beat_times if beat_times is not None else []
        self._downbeat_indices = downbeat_indices or set()
        self.update()

    def _sec_to_x(self, sec):
        if self._end_sec <= self._start_sec:
            return 0
        frac = (sec - self._start_sec) / (self._end_sec - self._start_sec)
        return int(frac * self.width())

    # --- Drag Events ---

    def mousePressEvent(self, event):
        if self._draggable and event.button() == Qt.LeftButton:
            self._drag_active = True
            self._drag_start_x = event.position().x()
            self.setCursor(QCursor(Qt.ClosedHandCursor))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_active:
            dx = event.position().x() - self._drag_start_x
            # Pixel → Sekunden: volle Breite = (end - start) Sekunden
            sec_per_px = (self._end_sec - self._start_sec) / max(self.width(), 1)
            delta_sec = -dx * sec_per_px  # negativ: nach rechts ziehen = frueher
            if abs(dx) > 2:  # Mindestbewegung bevor Signal kommt
                self._drag_start_x = event.position().x()
                self.dragged.emit(delta_sec)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_active:
            self._drag_active = False
            self.setCursor(QCursor(Qt.OpenHandCursor))
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # --- Paint ---

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        mid_y = h // 2

        p.fillRect(0, 0, w, h, self._bg_color)

        if self._samples is not None and len(self._samples) > 0:
            self._draw_waveform(p, w, h, mid_y)

        self._draw_beat_grid(p, h)

        # Original-Marker (duenne rote Linie) — nur wenn verschoben
        if self._orig_marker_sec is not None:
            if abs(self._orig_marker_sec - self._marker_sec) > 0.01:
                self._draw_marker(p, h, self._orig_marker_sec,
                                  self._marker_color, 1, dashed=True, label=False)

        # Aktueller Marker (gruen, in der Mitte)
        self._draw_marker(p, h, self._marker_sec, self._snap_color, 2)

        # Playback-Cursor (ganz oben)
        if self._cursor_sec is not None:
            self._draw_cursor(p, h)

        p.end()

    def _draw_waveform(self, p, w, h, mid_y):
        samples = self._samples
        n = len(samples)
        if n == 0 or w == 0:
            return
        pen = QPen(self._wave_color)
        pen.setWidth(1)
        p.setPen(pen)
        for x in range(w):
            start_idx = int(x * n / w)
            end_idx = min(int((x + 1) * n / w), n)
            if start_idx >= end_idx:
                continue
            chunk = samples[start_idx:end_idx]
            max_val = float(np.max(chunk))
            min_val = float(np.min(chunk))
            top = mid_y - int(max_val * mid_y * 0.85)
            bottom = mid_y - int(min_val * mid_y * 0.85)
            p.drawLine(x, top, x, bottom)

    def _draw_beat_grid(self, p, h):
        for i, bt in enumerate(self._beat_times):
            if bt < self._start_sec or bt > self._end_sec:
                continue
            x = self._sec_to_x(bt)
            if i in self._downbeat_indices:
                pen = QPen(self._downbeat_color)
                pen.setWidth(2)
            else:
                pen = QPen(self._beat_color)
                pen.setWidth(1)
            p.setPen(pen)
            p.drawLine(x, 0, x, h)

    def _draw_marker(self, p, h, sec, color, width, dashed=False, label=True):
        if sec < self._start_sec or sec > self._end_sec:
            return
        x = self._sec_to_x(sec)
        pen = QPen(color)
        pen.setWidth(width)
        if dashed:
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.drawLine(x, 0, x, h)
        if label:
            p.setPen(QPen(color))
            p.drawText(x + 4, 14, f"{sec:.2f}s")

    def _draw_cursor(self, p, h):
        sec = self._cursor_sec
        if sec is None or sec < self._start_sec or sec > self._end_sec:
            return
        x = self._sec_to_x(sec)
        pen = QPen(self._cursor_color)
        pen.setWidth(2)
        p.setPen(pen)
        p.drawLine(x, 0, x, h)


# ---------------------------------------------------------------------------
# Beat Snap Dialog
# ---------------------------------------------------------------------------

class BeatSnapDialog(QDialog):
    """Dialog zur visuellen Kontrolle und Feinabstimmung der Loop-Punkte."""

    accepted_snap = Signal(float, float)

    # Zoom-Stufen in Sekunden (±)
    ZOOM_LEVELS = [20.0, 15.0, 10.0, 7.0, 5.0, 3.0, 2.0, 1.0]
    DEFAULT_ZOOM_IDX = 2  # ±10s

    def __init__(self, engine, filepath, beat_times, bpm,
                 skin_mgr=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("beat_snap_title"))
        self.setMinimumSize(700, 450)
        self.resize(900, 520)

        self._engine = engine
        self._filepath = filepath
        self._beat_times = np.array(beat_times)
        self._bpm = bpm
        self._skin_mgr = skin_mgr

        # Zoom
        self._zoom_idx = self.DEFAULT_ZOOM_IDX
        self._window_seconds = self.ZOOM_LEVELS[self._zoom_idx]

        # Originale Loop-Punkte NUR fuer UI-Darstellung (Delta-Anzeige).
        # Die Engine-Loop-Punkte werden vom Dialog NIEMALS veraendert.
        # Nur engine.load() (neuer Song) darf Loop-Punkte aendern.
        self._orig_loop_in = engine.loop_in_seconds
        self._orig_loop_out = engine.loop_out_seconds

        # Aktuelle Positionen (durch Drag oder Adjust veraenderbar)
        self._current_in = self._orig_loop_in
        self._current_out = self._orig_loop_out

        self._modified = False        # True wenn was verschoben wurde
        self._applied = False         # True wenn "Uebernehmen" geklickt
        self._closing = False         # Guard gegen doppeltes closeEvent
        self._crossfade_enabled = False  # CrossFade-Toggle (default OFF)

        # Audio laden
        self._audio_mono = None
        self._audio_sr = 0
        self._load_audio()

        # Downbeats
        self._downbeat_set = self._detect_downbeats()

        # UI bauen
        self._build_ui()

        # Vorhoer-Timer + Cursor
        self._audition_timer = None
        self._cursor_timer = None
        self._audition_phase = 0

    def _load_audio(self):
        try:
            data, sr = sf.read(self._filepath, dtype='float32')
            if data.ndim > 1:
                self._audio_mono = np.mean(data, axis=1)
            else:
                self._audio_mono = data
            self._audio_sr = sr
        except Exception as e:
            print(f"[BeatSnapDialog] Audio laden fehlgeschlagen: {e}")

    def _detect_downbeats(self):
        downbeats = set()
        if self._audio_mono is None or len(self._beat_times) < 8:
            for i in range(0, len(self._beat_times), 8):
                downbeats.add(i)
            return downbeats

        sr = self._audio_sr
        mono = self._audio_mono
        window_samples = int(0.05 * sr)
        beat_energies = []
        for bt in self._beat_times:
            center = int(bt * sr)
            start = max(0, center - window_samples)
            end = min(len(mono), center + window_samples)
            if end > start:
                energy = float(np.sum(mono[start:end] ** 2))
            else:
                energy = 0.0
            beat_energies.append(energy)

        for group_start in range(0, len(self._beat_times), 8):
            group_end = min(group_start + 8, len(self._beat_times))
            if group_end <= group_start:
                break
            group = beat_energies[group_start:group_end]
            best_in_group = group_start + int(np.argmax(group))
            downbeats.add(best_in_group)

        return downbeats

    def _snap_to_nearest_beat(self, sec):
        """Findet den naechsten Beat zu einer Position."""
        if len(self._beat_times) < 2:
            return sec
        idx = np.argmin(np.abs(self._beat_times - sec))
        return float(self._beat_times[idx])

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # --- Loop-Out Waveform (oben) ---
        lbl_out = QLabel(_t("beat_snap_loop_out"))
        lbl_out.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(lbl_out)

        self._waveform_out = WaveformWidget(self, draggable=True)
        self._waveform_out.dragged.connect(self._on_drag_out)
        layout.addWidget(self._waveform_out)

        self._info_out = QLabel()
        self._info_out.setStyleSheet("font-size: 12px; font-family: monospace;")
        layout.addWidget(self._info_out)

        # --- Loop-In Waveform (unten) ---
        lbl_in = QLabel(_t("beat_snap_loop_in"))
        lbl_in.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(lbl_in)

        self._waveform_in = WaveformWidget(self, draggable=True)
        self._waveform_in.dragged.connect(self._on_drag_in)
        layout.addWidget(self._waveform_in)

        self._info_in = QLabel()
        self._info_in.setStyleSheet("font-size: 12px; font-family: monospace;")
        layout.addWidget(self._info_in)

        # --- Zoom ---
        zoom_layout = QHBoxLayout()
        zoom_layout.setSpacing(6)

        zoom_layout.addWidget(QLabel(_t("beat_snap_zoom")))

        self._btn_zoom_out = QPushButton("\u2212")
        self._btn_zoom_out.setFixedWidth(36)
        self._btn_zoom_out.setToolTip(_t("beat_snap_zoom_out"))
        self._btn_zoom_out.clicked.connect(self._on_zoom_out)
        zoom_layout.addWidget(self._btn_zoom_out)

        self._lbl_zoom = QLabel(f"\u00b1{self._window_seconds:.0f}s")
        self._lbl_zoom.setStyleSheet("font-family: monospace; min-width: 40px;")
        self._lbl_zoom.setAlignment(Qt.AlignCenter)
        zoom_layout.addWidget(self._lbl_zoom)

        self._btn_zoom_in = QPushButton("+")
        self._btn_zoom_in.setFixedWidth(36)
        self._btn_zoom_in.setToolTip(_t("beat_snap_zoom_in"))
        self._btn_zoom_in.clicked.connect(self._on_zoom_in)
        zoom_layout.addWidget(self._btn_zoom_in)

        # BL-166: STRG + Mausrad ueber den Wellenformen zoomt wie die Buttons
        for _wf in (self._waveform_out, self._waveform_in):
            install_ctrl_wheel_zoom(_wf, self._on_zoom_in, self._on_zoom_out)

        zoom_layout.addStretch()
        layout.addLayout(zoom_layout)

        # --- Aktions-Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        # Anpassen (springt zum naechsten Beat)
        self._btn_snap = QPushButton(_t("beat_snap_adjust"))
        self._btn_snap.setToolTip(_t("beat_snap_adjust_tip"))
        self._btn_snap.clicked.connect(self._on_snap)
        btn_layout.addWidget(self._btn_snap)

        # CrossFade-Toggle (default OFF, wird bei Drag zurueckgesetzt)
        self._btn_crossfade = QPushButton(_t("beat_snap_crossfade"))
        self._btn_crossfade.setToolTip(_t("beat_snap_crossfade_tip"))
        self._btn_crossfade.setCheckable(True)
        self._btn_crossfade.setChecked(False)
        self._btn_crossfade.toggled.connect(self._on_crossfade_toggled)
        btn_layout.addWidget(self._btn_crossfade)

        # Vorhoeren (immer verfuegbar)
        self._btn_audition = QPushButton(_t("beat_snap_audition"))
        self._btn_audition.setToolTip(_t("beat_snap_audition_tip"))
        self._btn_audition.clicked.connect(self._on_audition)
        btn_layout.addWidget(self._btn_audition)

        btn_layout.addStretch()

        # Uebernehmen (erst nach Aenderung)
        self._btn_apply = QPushButton(_t("beat_snap_apply"))
        self._btn_apply.setProperty("confirm", "true")
        self._btn_apply.clicked.connect(self._on_apply)
        self._btn_apply.setEnabled(False)
        btn_layout.addWidget(self._btn_apply)

        # Schliessen
        self._btn_close = QPushButton(_t("beat_snap_close"))
        self._btn_close.clicked.connect(self._on_close)
        btn_layout.addWidget(self._btn_close)

        layout.addLayout(btn_layout)

        # Farben + Waveforms
        self._apply_colors()
        self._update_waveforms()
        self._update_zoom_buttons()

    def _color(self, name, fallback):
        if self._skin_mgr:
            return self._skin_mgr.color(name, fallback)
        return fallback

    def _apply_colors(self):
        """Wendet Skin-Farben auf Waveforms an.

        KEIN setStyleSheet auf dem Dialog selbst — die App-QSS wird
        automatisch vererbt (Buttons, Labels etc. bekommen den Skin).
        Nur die Waveform-Widgets zeichnen per QPainter eigene Farben.
        """
        wave_bg = self._color("input_bg", "#2b2b2b")
        wave = self._color("button_bg", "#615f8b")
        beat = self._color("text_dim", "#666666")
        downbeat = self._color("text", "#cccccc")
        marker = self._color("warning", "#ef4444")
        snap = self._color("confirm", "#22c55e")
        text = self._color("text", "#f0f0f0")
        cursor = self._color("title_text", "#ffffff")

        self._waveform_out.set_colors(wave_bg, wave, beat, downbeat, marker, snap, text, cursor)
        self._waveform_in.set_colors(wave_bg, wave, beat, downbeat, marker, snap, text, cursor)

    def update_skin(self):
        """Wird bei Skin-Wechsel aufgerufen."""
        self._apply_colors()
        self._update_waveforms()

    # --- Waveform-Daten ---

    def _get_waveform_slice(self, center_sec):
        """Extrahiert Waveform-Ausschnitt symmetrisch um center_sec."""
        if self._audio_mono is None:
            return None, 0.0, 0.0

        sr = self._audio_sr
        win = self._window_seconds
        start = center_sec - win
        end = center_sec + win

        start_idx = int(start * sr)
        end_idx = int(end * sr)
        total_samples = end_idx - start_idx
        if total_samples <= 0:
            return None, start, end

        result = np.zeros(total_samples, dtype=np.float32)
        src_start = max(0, start_idx)
        src_end = min(len(self._audio_mono), end_idx)
        dst_start = src_start - start_idx
        dst_end = dst_start + (src_end - src_start)
        if src_end > src_start:
            result[dst_start:dst_end] = self._audio_mono[src_start:src_end]

        return result, start, end

    def _get_beats_in_range(self, start_sec, end_sec):
        mask = (self._beat_times >= start_sec) & (self._beat_times <= end_sec)
        times = self._beat_times[mask]
        orig_indices = np.where(mask)[0]
        downbeats = set()
        for i, orig_idx in enumerate(orig_indices):
            if orig_idx in self._downbeat_set:
                downbeats.add(i)
        return list(times), downbeats

    def _update_waveforms(self):
        """Aktualisiert beide Waveform-Anzeigen.

        Beide Waveforms zentrieren auf der aktuellen Position (Mitte = Marker).
        Original-Position wird als duenne rote gestrichelte Linie angezeigt
        wenn sie sich von der aktuellen unterscheidet.
        """
        # Loop-Out Waveform — zentriert auf current_out
        samples_out, s_out, e_out = self._get_waveform_slice(self._current_out)
        if samples_out is not None:
            self._waveform_out.set_data(samples_out, self._audio_sr, s_out, e_out)
            beats_out, db_out = self._get_beats_in_range(s_out, e_out)
            self._waveform_out.set_beat_grid(beats_out, db_out)
            # Original als rote Linie nur wenn verschoben
            orig_out = self._orig_loop_out if self._modified else None
            self._waveform_out.set_marker(self._current_out, orig_out)

        if self._modified:
            diff = self._current_out - self._orig_loop_out
            self._info_out.setText(
                f"{_t('beat_snap_original')}: {self._orig_loop_out:.3f}s  \u2192  "
                f"{_t('beat_snap_current')}: {self._current_out:.3f}s  (\u0394 {diff:+.3f}s)"
            )
        else:
            self._info_out.setText(f"{_t('beat_snap_loop_end_label')}: {self._current_out:.3f}s")

        # Loop-In Waveform — zentriert auf current_in
        samples_in, s_in, e_in = self._get_waveform_slice(self._current_in)
        if samples_in is not None:
            self._waveform_in.set_data(samples_in, self._audio_sr, s_in, e_in)
            beats_in, db_in = self._get_beats_in_range(s_in, e_in)
            self._waveform_in.set_beat_grid(beats_in, db_in)
            orig_in = self._orig_loop_in if self._modified else None
            self._waveform_in.set_marker(self._current_in, orig_in)

        if self._modified:
            diff = self._current_in - self._orig_loop_in
            self._info_in.setText(
                f"{_t('beat_snap_original')}: {self._orig_loop_in:.3f}s  \u2192  "
                f"{_t('beat_snap_current')}: {self._current_in:.3f}s  (\u0394 {diff:+.3f}s)"
            )
        else:
            self._info_in.setText(f"{_t('beat_snap_loop_start_label')}: {self._current_in:.3f}s")

    # --- Drag ---

    def _on_drag_in(self, delta_sec):
        """Untere Waveform per Drag verschoben — Loop-In anpassen."""
        self._stop_audition()
        new_in = self._current_in + delta_sec
        # Grenzen: mindestens 0, hoechstens current_out - 1s
        new_in = max(0.0, min(new_in, self._current_out - 1.0))
        self._current_in = new_in
        self._mark_modified()
        self._update_waveforms()

    def _on_drag_out(self, delta_sec):
        """Obere Waveform per Drag verschoben — Loop-Out anpassen."""
        self._stop_audition()
        duration = len(self._audio_mono) / self._audio_sr if self._audio_mono is not None else 999
        new_out = self._current_out + delta_sec
        # Grenzen: mindestens current_in + 1s, hoechstens Song-Ende
        new_out = max(self._current_in + 1.0, min(new_out, duration))
        self._current_out = new_out
        self._mark_modified()
        self._update_waveforms()

    def _mark_modified(self):
        """Markiert dass Positionen veraendert wurden."""
        self._modified = True
        self._btn_apply.setEnabled(True)
        self._btn_snap.setEnabled(True)
        self._btn_snap.setText(_t("beat_snap_adjust"))
        self._reset_crossfade()

    def _reset_crossfade(self):
        """Setzt CrossFade-Toggle auf OFF (bei Drag oder Dialog-Start)."""
        self._crossfade_enabled = False
        self._btn_crossfade.blockSignals(True)
        self._btn_crossfade.setChecked(False)
        self._btn_crossfade.blockSignals(False)

    def _on_crossfade_toggled(self, checked):
        self._crossfade_enabled = checked

    # --- Zoom ---

    def _on_zoom_in(self):
        if self._zoom_idx < len(self.ZOOM_LEVELS) - 1:
            self._stop_audition()
            self._zoom_idx += 1
            self._window_seconds = self.ZOOM_LEVELS[self._zoom_idx]
            self._lbl_zoom.setText(f"\u00b1{self._window_seconds:.0f}s")
            self._update_zoom_buttons()
            self._update_waveforms()

    def _on_zoom_out(self):
        if self._zoom_idx > 0:
            self._stop_audition()
            self._zoom_idx -= 1
            self._window_seconds = self.ZOOM_LEVELS[self._zoom_idx]
            self._lbl_zoom.setText(f"\u00b1{self._window_seconds:.0f}s")
            self._update_zoom_buttons()
            self._update_waveforms()

    def _update_zoom_buttons(self):
        self._btn_zoom_out.setEnabled(self._zoom_idx > 0)
        self._btn_zoom_in.setEnabled(self._zoom_idx < len(self.ZOOM_LEVELS) - 1)

    # --- Snap / Adjust ---

    def _on_snap(self):
        """Springt beide Positionen zum jeweils naechsten Beat."""
        self._stop_audition()

        self._current_in = self._snap_to_nearest_beat(self._current_in)
        self._current_out = self._snap_to_nearest_beat(self._current_out)

        # Sicherheit: Loop-Out muss nach Loop-In liegen
        if self._current_out <= self._current_in + 1.0:
            candidates = self._beat_times[self._beat_times > self._current_in + 1.0]
            if len(candidates) > 0:
                self._current_out = float(
                    candidates[np.argmin(np.abs(candidates - self._orig_loop_out))]
                )

        self._mark_modified()
        self._btn_snap.setEnabled(False)
        self._btn_snap.setText(_t("beat_snap_adjusted"))
        self._update_waveforms()

    # --- Vorhoeren ---
    # WICHTIG: Die Audition aendert KEINE Engine-Loop-Punkte!
    # Der Loop-Sprung wird per seek() simuliert. Die gespeicherten
    # Loop-Marken des Users bleiben IMMER unangetastet.

    def _on_audition(self):
        # Vorherige Audition sauber stoppen falls noch laufend
        self._stop_audition()

        # Aktuelle Positionen verwenden
        aud_in = self._current_in
        aud_out = self._current_out

        # Engine-Loop waehrend Audition DEAKTIVIEREN.
        # Grund: Der Feed-Stretcher macht seinen eigenen Loop-Sprung
        # bei _feed_pos >= _loop_out, und zwar im Feed-Ahead (~0.5s VOR
        # der tatsaechlichen Wiedergabe). Das erzeugt einen hoerbaren
        # Doppel-Sprung: erst Engine-Loop (zu frueh), dann Beat-Snap-Seek.
        # Stattdessen: Engine spielt linear, Beat Snap steuert den
        # einzigen Loop-Sprung allein per seek().
        self._saved_loop_active = self._engine._loop_active
        self._engine._loop_active = False

        # 5 Sekunden vor Loop-Out starten
        start_pos = max(0, aud_out - 5.0)
        self._engine.seek(start_pos)
        self._engine.play()

        self._btn_audition.setEnabled(False)
        self._btn_audition.setText(_t("beat_snap_audition_playing"))

        tempo = self._engine._combined_tempo()
        self._phase1_duration_ms = int((5.0 / tempo) * 1000)
        self._phase2_duration_ms = int((2.0 / tempo) * 1000)

        # Audition-Positionen merken
        self._aud_in = aud_in
        self._aud_out = aud_out
        self._jump_done = False  # Guard: Seek zum Loop-In nur einmal

        # Cursor folgt dem Playback-Sample-Counter der Engine.
        # Dieser zaehlt tatsaechlich ausgegebene Samples im Audio-Callback
        # und ist damit die praeziseste verfuegbare Positions-Quelle.
        self._audition_phase = 1
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(33)  # 30 Hz — schont CPU
        self._cursor_timer.timeout.connect(self._update_cursor)
        self._cursor_timer.start()

        # Safety-Stopp-Timer
        total_ms = self._phase1_duration_ms + self._phase2_duration_ms + 1000
        self._audition_timer = QTimer(self)
        self._audition_timer.setSingleShot(True)
        self._audition_timer.timeout.connect(self._on_audition_done)
        self._audition_timer.start(total_ms)

    def _update_cursor(self):
        if not self._engine.is_playing():
            self._on_audition_done()
            return

        # Playback-Sample-Counter: Zaehlt tatsaechlich ausgegebene Samples.
        # Kein Feed-Ahead-Offset, kein Buffer-Schaetzen, kein Timer-Drift.
        pos = self._engine.get_playback_position_seconds()

        if self._audition_phase == 1:
            # Phase 1: Cursor laeuft in oberer Waveform Richtung Loop-Out
            # Seek zum Loop-In wenn tatsaechlich ausgegebene Position
            # den Loop-Out-Punkt erreicht
            if pos >= self._aud_out and not self._jump_done:
                if self._crossfade_enabled:
                    # Crossfade-Dauer aus Engine-Konfiguration ableiten
                    sr = getattr(self._engine, 'sample_rate', 44100) or 44100
                    xfade_ms = int(
                        getattr(self._engine, '_loop_xfade_frames', 0)
                        * 1000 / sr
                    )
                    self._engine.seek_with_crossfade(self._aud_in, max(1, xfade_ms))
                else:
                    self._engine.seek(self._aud_in)
                self._jump_done = True
                self._audition_phase = 2
                self._waveform_out.set_cursor(None)
                self._waveform_in.set_cursor(self._aud_in)
                return

            self._waveform_out.set_cursor(pos)
            self._waveform_in.set_cursor(None)

        elif self._audition_phase == 2:
            # Phase 2: Cursor laeuft in unterer Waveform ab Loop-In
            self._waveform_in.set_cursor(pos)
            self._waveform_out.set_cursor(None)

    def _on_audition_done(self):
        if self._audition_phase == 0:
            return

        if self._cursor_timer:
            self._cursor_timer.stop()
            self._cursor_timer = None
        if self._audition_timer:
            self._audition_timer.stop()
            self._audition_timer = None
        self._audition_phase = 0
        self._waveform_out.set_cursor(None)
        self._waveform_in.set_cursor(None)

        if self._engine.is_playing():
            self._engine.stop()

        self._btn_audition.setEnabled(True)
        self._btn_audition.setText(_t("beat_snap_audition"))

    # --- Uebernehmen / Schliessen ---

    def _on_apply(self):
        if self._modified:
            self._stop_audition()
            self._applied = True
            self.accepted_snap.emit(self._current_in, self._current_out)
        self.accept()

    def _on_close(self):
        """Schliessen-Button: Rueckfrage wenn modifiziert aber nicht uebernommen."""
        if self._modified and not self._applied:
            reply = QMessageBox.question(
                self,
                _t("beat_snap_unsaved_title"),
                _t("beat_snap_unsaved_msg"),
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )
            if reply == QMessageBox.Save:
                self._on_apply()
                return
            elif reply == QMessageBox.Cancel:
                return
            # Discard → schliessen ohne Speichern
        self.reject()

    def reject(self):
        self._stop_audition()
        # Kein Restore noetig — Engine-Loop wurde nie veraendert
        self._closing = True
        super().reject()

    def closeEvent(self, event):
        """Fenster-X-Button: gleiche Logik wie Schliessen-Button."""
        # Guard: reject() setzt _closing=True, dann darf closeEvent
        # nicht nochmal die Rueckfrage zeigen
        if self._closing:
            event.accept()
            return

        if self._modified and not self._applied:
            reply = QMessageBox.question(
                self,
                _t("beat_snap_unsaved_title"),
                _t("beat_snap_unsaved_msg"),
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )
            if reply == QMessageBox.Save:
                self._on_apply()
                event.accept()
                return
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return
        self._stop_audition()
        # Kein Restore noetig — Engine-Loop wurde nie veraendert
        event.accept()

    def _stop_audition(self):
        """Stoppt laufende Audition. Veraendert KEINE Engine-Loop-Punkte."""
        was_running = self._audition_phase > 0
        if self._cursor_timer:
            self._cursor_timer.stop()
            self._cursor_timer = None
        if self._audition_timer:
            self._audition_timer.stop()
            self._audition_timer = None
        self._audition_phase = 0
        self._waveform_out.set_cursor(None)
        self._waveform_in.set_cursor(None)
        # Engine-Loop ZUERST wiederherstellen (vor stop(), das _feed_pos
        # auf _loop_in setzt wenn _loop_active == True)
        if hasattr(self, '_saved_loop_active'):
            self._engine._loop_active = self._saved_loop_active
        if self._engine.is_playing():
            self._engine.stop()
        if was_running:
            self._btn_audition.setEnabled(True)
            self._btn_audition.setText(_t("beat_snap_audition"))
