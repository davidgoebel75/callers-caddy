"""Square Flow: die Sequenz aus dem Sequenz-Detail als tanzender Square (intern#247).

Optik wie der Pruefstand (intern#163): Boden mit Linienraster (Mittelachsen kraeftiger),
Paarfarben, Mann eckig, Frau rund, Nase fuer die Blickrichtung, Paarnummer. Farben aus dem
Theme (Schluessel squareflow_*; fehlen sie im Theme, ergaenzt der SkinManager sie aus default).

Laden nur bei Freigabe: Ist Square Flow ausgeschaltet, startet weder Worker noch Engine.
Gerechnet wird im Hintergrund (flow_worker), gezeichnet wird nur die Square-Flaeche; Raster
und Beschriftung liegen als Bild im Zwischenspeicher. Tempo = Tempo des Songs (bpm_source).
"""
import html
import math

from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QPointF, QRectF, Signal
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QPixmap, QPolygonF, QFont,
                           QActionGroup)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QBoxLayout, QLabel, QPushButton, QMenu,
                               QSizePolicy)

from caddy.choreo import figure_clock, pilot_colors, square_chain
from caddy.choreo.timeline import Timeline
from caddy.settings import ini_keys
from i18n import _t

FALLBACK_BPM = 128.0
ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 0.6, 2.5, 1.1
_NOTCH = 120                                  # ein Raster-Schritt des Mausrads
CONTROL_POSITIONS = ("below", "above", "left", "right")
_DEFAULTS = {
    "squareflow_floor": "#1d2028", "squareflow_grid": "#2a2e38",
    "squareflow_grid_strong": "#3b404c", "squareflow_body_stroke": "#0b0d11",
    "squareflow_couple1": "#d93a3a", "squareflow_couple2": "#2a9a4a",
    "squareflow_couple3": "#3a5fd9", "squareflow_couple4": "#e3b81e",
    "squareflow_band_good": "#1fa050", "squareflow_band_bad": "#d63428",
}


class _Floor(QWidget):
    """Die Square-Flaeche. Bekommt Stellung, Taenzer und Pruefbaender von aussen."""

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self._color = color                # callable(key) -> QColor
        self.dancers = []
        self.pose = []
        self.bands = None                  # (paare als Index-Tupel, gut: bool) oder None
        self.pilot = {}                    # Pilot-Square-Farben {(Couple, Mann?): hex} (intern#249)
        self.ext = 5.5
        self.zoom = 1.0                    # Shift/Strg + Mausrad, ZOOM_MIN..ZOOM_MAX
        self._bg = None
        self._bg_key = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(120, 120)

    def invalidate_background(self):
        self._bg = None
        self.update()

    on_wheel_zoom = None                   # callback(schritte), gesetzt vom SquareFlowWidget

    def wheelEvent(self, event):
        """Shift + Mausrad zoomt (wie gewuenscht), Strg + Mausrad ebenso (App-Standard,
        BL-166). Shift kann das Rad je nach System auf die x-Achse legen: beide lesen."""
        mods = event.modifiers()
        if self.on_wheel_zoom and mods & (Qt.ShiftModifier | Qt.ControlModifier):
            d = event.angleDelta()
            self._accum = getattr(self, "_accum", 0) + (d.y() or d.x())
            steps = int(self._accum / _NOTCH)
            if steps:
                self._accum -= steps * _NOTCH
                self.on_wheel_zoom(steps)
            event.accept()
            return
        super().wheelEvent(event)

    def _geometry(self):
        side = min(self.width(), self.height())
        scale = side / (2 * self.ext) * self.zoom
        return scale, self.width() / 2, self.height() / 2

    def _to_screen(self, x, y, scale, cx, cy):
        # Taminations: x zur Buehne (oben), Couple 1 unten bei x = -3
        return QPointF(cx - y * scale, cy - x * scale)

    def _background(self):
        key = (self.width(), self.height(), self.ext, self.zoom)
        if self._bg is not None and self._bg_key == key:
            return self._bg
        pm = QPixmap(max(1, self.width()), max(1, self.height()))
        pm.fill(self._color("squareflow_floor"))
        p = QPainter(pm)
        scale, cx, cy = self._geometry()
        # Raster ueber die ganze Flaeche (auch herausgezoomt)
        n = int(math.ceil(max(self.width(), self.height()) / 2 / scale))
        for i in range(-n, n + 1):
            strong = i == 0
            pen = QPen(self._color("squareflow_grid_strong" if strong else "squareflow_grid"))
            pen.setWidthF(max(1.0, scale * (0.04 if strong else 0.03)))
            p.setPen(pen)
            a = self._to_screen(i, -n, scale, cx, cy)
            b = self._to_screen(i, n, scale, cx, cy)
            p.drawLine(a, b)
            a = self._to_screen(-n, i, scale, cx, cy)
            b = self._to_screen(n, i, scale, cx, cy)
            p.drawLine(a, b)
        p.end()
        self._bg, self._bg_key = pm, key
        return pm

    def paintEvent(self, _event):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._background())
        if not self.pose or not self.dancers:
            p.end()
            return
        p.setRenderHint(QPainter.Antialiasing)
        scale, cx, cy = self._geometry()
        pts = [self._to_screen(x, y, scale, cx, cy) for x, y, _ in self.pose]
        if self.bands:
            pairs, good = self.bands
            col = QColor(self._color("squareflow_band_good" if good else "squareflow_band_bad"))
            col.setAlpha(150)
            pen = QPen(col, max(3.0, scale * 0.55), Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen)
            for a, b in pairs:
                if a < len(pts) and b < len(pts):
                    p.drawLine(pts[a], pts[b])
        size = scale * 0.8
        font = QFont()
        font.setPixelSize(max(8, int(size * 0.45)))
        font.setBold(True)
        p.setFont(font)
        stroke = QPen(self._color("squareflow_body_stroke"), max(1.0, scale * 0.05))
        for d, pt, (_x, _y, deg) in zip(self.dancers, pts, self.pose):
            fill = pilot_colors.fill_for(self.pilot, d)
            c = QColor(fill) if fill else self._color(f"squareflow_couple{d.get('couple')}")
            p.save()
            p.translate(pt)
            p.rotate(-deg)                 # Winkel 0 = Blick nach oben, Qt dreht im Uhrzeigersinn
            nose = QPolygonF([QPointF(0, -size * 0.85), QPointF(size * 0.3, -size * 0.3),
                              QPointF(-size * 0.3, -size * 0.3)])
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(c.darker(130)))
            p.drawPolygon(nose)
            p.setBrush(QBrush(c))
            p.setPen(stroke)
            r = QRectF(-size / 2, -size / 2, size, size)
            if d.get("boy"):
                p.drawRect(r)
            else:
                p.drawEllipse(r)
            p.restore()
            p.setPen(QColor(pilot_colors.text_on(fill) if fill else "#141414"))
            p.drawText(QRectF(pt.x() - size / 2, pt.y() - size / 2, size, size),
                       Qt.AlignCenter, str(d.get("couple")))
        p.end()


class SquareFlowWidget(QWidget):
    """Dock-Inhalt Square Flow. Zirkelfrei: kennt main.py nicht, bekommt alles per Aufruf."""

    current_card_changed = Signal(int)      # Kartenzeile, die gerade getanzt wird (-1 = keine)
    result_ready = Signal(object, object)   # (Calls der Sequenz, Ergebnis oder None)
    edit_requested = Signal()               # "Sequenz bearbeiten" geklickt

    def __init__(self, skin_mgr=None, settings=None, db_path=None, bpm_source=None, parent=None):
        super().__init__(parent)
        self._skin_mgr = skin_mgr
        self._settings = settings
        self._db_path = db_path
        self._bpm_source = bpm_source
        self._worker = None
        self._token = 0
        self._seq = None                    # (calls, seq_type)
        self._seq_id = None                 # fuer den DB-Cache (sequence_choreo)
        self._dirty = False
        self._result = None
        self._tl = None
        self._beat = 0.0
        self._stop_at = None                # Ende einer einzeln gespielten Kartenzeile
        self._pending_card = None           # Klick, bevor die Animation da war
        self._card = -1
        self._emitted_card = -1
        self._active = False                # Wiedergabe/Navigation durch den Nutzer
        self._shown_line = None
        # Mitlaufen im Singing Call (Phase 2): der Song gibt den Beat vor
        self._following = False
        self._follow_region = None          # ("f", Teil) in einer Figur, ("o", letzter Teil) sonst
        self._follow_hold = None            # Eingriff des Nutzers: Region, bis zu deren Ende
        # Phase 2b: Weitertanzen ueber die Figuren und Heads/Sides-Spiegeln (nur Anzeige)
        self._chain = None                  # square_chain.PartnerChain, lebt ueber Sequenzen
        self._end_perm = None               # wo jeder Taenzer am Figurenende steht (oder None)
        self._rot_slots = None              # Platz je Startplatz beim Spiegeln
        self._view = None                   # (rot, gezeigte Taenzer) waehrend des Mitlaufens
        self._view_rot = False
        self._pilot = {}                    # Phase 3: letzte Farben aus dem Pilot Square
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._load_options()
        self._build_ui()
        self._show_message(_t("sf_no_sequence"))

    # --- Aufbau ---------------------------------------------------------------

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        self._status = QLabel(self)
        self._status.setWordWrap(True)
        self._status.setTextFormat(Qt.PlainText)
        lay.addWidget(self._status)
        # Hinweise bei Warnung (intern#254): woran es liegen kann, Weg in den Editor
        self._hints = QLabel(self)
        self._hints.setWordWrap(True)
        self._hints.setTextFormat(Qt.RichText)
        self._hints.setVisible(False)
        lay.addWidget(self._hints)
        self._btn_edit = QPushButton(_t("sf_btn_edit"), self)
        self._btn_edit.clicked.connect(self.edit_requested.emit)
        self._btn_edit.setVisible(False)
        lay.addWidget(self._btn_edit, 0, Qt.AlignLeft)
        # Phase 2b: Partner-Kette gerissen (Figur endete nicht zu Hause)
        self._chain_note = QLabel(_t("sf_chain_reset"), self)
        self._chain_note.setWordWrap(True)
        self._chain_note.setVisible(False)
        lay.addWidget(self._chain_note)
        # Buehne: Square (mit Call-Zeile) und Tasten; Lage der Tasten per Rechtsklick
        self._floor = _Floor(self._color, self)
        self._floor.zoom = self._zoom
        self._floor.on_wheel_zoom = self.zoom_by
        self._call_label = QLabel(self)
        self._call_label.setTextFormat(Qt.PlainText)
        self._call_label.setAlignment(Qt.AlignCenter)
        floor_box = QVBoxLayout()
        floor_box.setSpacing(4)
        floor_box.addWidget(self._floor, 1)
        floor_box.addWidget(self._call_label)
        self._btn_restart = self._button("|◀", _t("sf_btn_restart"), self.restart)
        self._btn_prev = self._button("◀", _t("sf_btn_prev"), self.prev_call)
        self._btn_play = self._button("▶", _t("sf_btn_play"), self.toggle_play)
        self._btn_next = self._button("▶|", _t("sf_btn_next"), self.next_call)
        self._controls = QWidget(self)
        self._controls_lay = QBoxLayout(QBoxLayout.LeftToRight, self._controls)
        self._controls_lay.setContentsMargins(0, 0, 0, 0)
        self._controls_lay.setSpacing(4)
        self._controls_lay.addStretch(1)
        for b in (self._btn_restart, self._btn_prev, self._btn_play, self._btn_next):
            self._controls_lay.addWidget(b)
        self._controls_lay.addStretch(1)
        self._stage = QBoxLayout(QBoxLayout.TopToBottom)
        self._stage.setSpacing(4)
        self._stage.addLayout(floor_box, 1)
        self._stage.addWidget(self._controls)
        lay.addLayout(self._stage, 1)
        self._apply_controls_pos()
        self._apply_label_colors()

    def _button(self, text, tip, slot):
        # Groesse wie die Vor/Zurueck-Knoepfe im Sequenz-Detail (44 x 40, 16 px)
        b = QPushButton(text, self)
        b.setFixedSize(44, 40)
        b.setStyleSheet("font-size: 16px; padding: 0px;")
        b.setToolTip(tip)
        b.clicked.connect(slot)
        return b

    # --- Einstellungen und Theme -----------------------------------------------

    def _load_options(self):
        def get(key, typ):
            if self._settings is None:
                return ini_keys.default(key)
            return ini_keys.get(self._settings, key, type=typ)
        self._enabled = bool(get(ini_keys.SQUARE_FLOW_ENABLED, bool))
        self._fps = max(5, min(30, int(get(ini_keys.SQUARE_FLOW_FRAME_RATE, int) or 25)))
        self._saving = bool(get(ini_keys.SQUARE_FLOW_SAVING_MODE, bool))
        try:
            self._lag_beats = max(0, min(8, int(get(ini_keys.SQUARE_FLOW_LAG_BEATS, int))))
        except (TypeError, ValueError):
            self._lag_beats = 2
        try:
            zoom = int(get(ini_keys.SQUARE_FLOW_ZOOM_PCT, int)) / 100.0
        except (TypeError, ValueError):
            zoom = 1.0
        self._zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))
        pos = str(get(ini_keys.SQUARE_FLOW_CONTROLS_POS, str) or "below")
        self._controls_pos = pos if pos in CONTROL_POSITIONS else "below"
        self._use_pilot = bool(get(ini_keys.SQUARE_FLOW_PILOT_COLORS, bool))

    def _store(self, key, value):
        if self._settings is not None and hasattr(self._settings, "setValue"):
            self._settings.setValue(key, value)

    # --- Zoom und Lage der Tasten ----------------------------------------------

    def zoom_by(self, steps):
        """Zoomen in Mausrad-Schritten, begrenzt auf ZOOM_MIN..ZOOM_MAX."""
        zoom = max(ZOOM_MIN, min(ZOOM_MAX, self._zoom * (ZOOM_STEP ** steps)))
        if abs(zoom - self._zoom) < 1e-9:
            return
        self._zoom = zoom
        self._floor.zoom = zoom
        self._floor.invalidate_background()
        self._store(ini_keys.SQUARE_FLOW_ZOOM_PCT, int(round(zoom * 100)))

    def reset_zoom(self):
        self._zoom = self._floor.zoom = 1.0
        self._floor.invalidate_background()
        self._store(ini_keys.SQUARE_FLOW_ZOOM_PCT, 100)

    def set_controls_pos(self, pos):
        if pos not in CONTROL_POSITIONS:
            return
        self._controls_pos = pos
        self._apply_controls_pos()
        self._store(ini_keys.SQUARE_FLOW_CONTROLS_POS, pos)

    def _apply_controls_pos(self):
        """Tasten unter, ueber, links oder rechts vom Square."""
        stage_dir = {"below": QBoxLayout.TopToBottom, "above": QBoxLayout.BottomToTop,
                     "left": QBoxLayout.RightToLeft, "right": QBoxLayout.LeftToRight}
        self._stage.setDirection(stage_dir[self._controls_pos])
        side = self._controls_pos in ("left", "right")
        self._controls_lay.setDirection(QBoxLayout.TopToBottom if side
                                        else QBoxLayout.LeftToRight)

    # --- Pilot-Square-Farben (Phase 3, intern#249) -------------------------------

    def set_pilot_colors(self, colors):
        """Farben je Taenzer aus dem Pilot Square, {(Couple, Mann?): hex}; leer = Standard."""
        self._pilot = pilot_colors.clean(colors)
        self._apply_pilot()

    def set_use_pilot_colors(self, on):
        self._use_pilot = bool(on)
        self._store(ini_keys.SQUARE_FLOW_PILOT_COLORS, self._use_pilot)
        self._apply_pilot()

    def _apply_pilot(self):
        self._floor.pilot = self._pilot if self._use_pilot else {}
        self._floor.update()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act = menu.addAction(_t("sf_ctx_pilot_colors"))
        act.setCheckable(True)
        act.setChecked(self._use_pilot)
        act.triggered.connect(self.set_use_pilot_colors)
        menu.addSeparator()
        group = QActionGroup(menu)
        for pos in CONTROL_POSITIONS:
            act = menu.addAction(_t(f"sf_ctx_controls_{pos}"))
            act.setCheckable(True)
            act.setChecked(pos == self._controls_pos)
            group.addAction(act)
            act.triggered.connect(lambda _c=False, p=pos: self.set_controls_pos(p))
        menu.addSeparator()
        act = menu.addAction(_t("sf_ctx_zoom_reset"))
        act.setEnabled(abs(self._zoom - 1.0) > 1e-9)
        act.triggered.connect(self.reset_zoom)
        menu.exec(event.globalPos())
        menu.deleteLater()
        event.accept()

    def reload_settings(self):
        was = self._enabled
        self._load_options()
        if self._timer.isActive():
            self._timer.start(self._interval())
        if self._enabled and not was:
            self._dirty = True
            self._maybe_request()
        elif not self._enabled:
            self.pause()
            self._show_message(_t("sf_disabled"))

    def enabled(self):
        return self._enabled

    def _color(self, key):
        fb = _DEFAULTS.get(key, "#888888")
        return QColor(self._skin_mgr.color(key, fb) if self._skin_mgr else fb)

    def _apply_label_colors(self):
        text = self._skin_mgr.color("text", "#f0f0f0") if self._skin_mgr else "#f0f0f0"
        dim = self._skin_mgr.color("text_dim", "#999999") if self._skin_mgr else "#999999"
        self._status.setStyleSheet(f"color: {text};")
        self._call_label.setStyleSheet(f"color: {dim};")
        self._hints.setStyleSheet(f"color: {dim};")
        self._chain_note.setStyleSheet(f"color: {dim};")

    def set_skin(self, skin_mgr):
        self._skin_mgr = skin_mgr
        self._apply_label_colors()
        self._floor.invalidate_background()
        if self._result:
            self._show_result_status()

    # --- Sequenz -------------------------------------------------------------

    def set_sequence(self, calls, seq_type, seq_id=None):
        """Sequenz aus dem Sequenz-Detail. Gerechnet wird nur, wenn Square Flow freigegeben
        ist (auch bei geschlossenem Dock: die Takte im Sequenz-Detail brauchen das Ergebnis)."""
        calls = [c for c in (calls or []) if c and str(c).strip()]
        seq = (tuple(calls), seq_type or "") if calls else None
        if seq == self._seq:
            return
        self._seq = seq
        self._seq_id = seq_id
        self.pause()
        self._result, self._tl = None, None
        self._floor.pose, self._floor.bands = [], None
        self._floor.update()
        self._active = False
        self._pending_card = None
        self._set_card(-1)
        self._set_hints([], False)
        self.result_ready.emit(seq[0] if seq else (), None)
        self._dirty = seq is not None
        if seq is None:
            self._show_message(_t("sf_no_sequence"))
        self._maybe_request()

    def showEvent(self, event):
        super().showEvent(event)
        if self._result is not None and not self._result.get("animation"):
            self._dirty = True                   # Ergebnis aus der DB: Animation nachholen
        self._maybe_request()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.pause()

    def _maybe_request(self):
        if not self._enabled:
            self._show_message(_t("sf_disabled"))
            return
        if not self._dirty or self._seq is None:
            return
        if self._worker is None:
            from caddy.choreo.flow_worker import SquareFlowWorker
            self._worker = SquareFlowWorker(self._db_path, parent=self)
            self._worker.ready.connect(self._on_ready)
        self._dirty = False
        self._token += 1
        if self._result is None:
            self._show_message(_t("sf_calculating"))
        self._worker.request(self._token, *self._seq, seq_id=self._seq_id,
                             need_animation=self.isVisible())

    def invalidate(self):
        """Call-Mapping geaendert: Zwischenspeicher verwerfen und neu rechnen."""
        if self._worker is not None:
            self._worker.invalidate()
        if self._seq is not None:
            self._dirty = True
            self._maybe_request()

    def shutdown(self):
        self._timer.stop()
        if self._worker is not None:
            self._worker.shutdown()

    def _on_ready(self, token, result):
        if token != self._token:
            return                                   # veraltet: andere Sequenz gewaehlt
        if result.get("error"):
            key = "sf_engine_missing" if result["error"] == "engine_missing" else None
            self._show_message(_t(key) if key else result["error"])
            return
        self._result = result
        self._tl = Timeline(result.get("animation"))
        ext = self._tl.extent()
        self._floor.ext = max(5.5, math.ceil(ext) + 1.0)
        self._floor.dancers = self._tl.dancers
        self._view, self._view_rot = None, False
        self._prepare_chain(result)
        self._floor.invalidate_background()
        self._show_result_status()
        self._seek(0.0)
        self.result_ready.emit(self._seq[0], result)
        if self._pending_card is not None and not self._tl.empty():
            card, self._pending_card = self._pending_card, None
            self.play_card(card)

    # --- Anzeige ----------------------------------------------------------------

    def _show_message(self, text):
        self._status.setText(text)
        self._call_label.setText("")
        enabled = self._tl is not None and not self._tl.empty()
        for b in (self._btn_restart, self._btn_prev, self._btn_play, self._btn_next):
            b.setEnabled(enabled)

    def _show_result_status(self):
        r = self._result
        if not r["stufe1"]:
            line = (r["fail_card"] + 1) if r.get("fail_card") is not None else "?"
            text = _t("sf_result_abbruch").format(line=line, error=r.get("error") or "")
        else:
            key = f"sf_result_{r['urteil']}" if r.get("urteil") else "sf_result_kein_band"
            text = _t(key)
        if r.get("beats_total") is not None:
            text += "   ·   " + _t("sf_beats_total").format(beats=f"{r['beats_total']:g}")
        self._status.setText(text)
        for b in (self._btn_restart, self._btn_prev, self._btn_play, self._btn_next):
            b.setEnabled(not self._tl.empty())
        lines, strong = self.hint_lines(r, self._seq[0] if self._seq else ())
        self._set_hints(lines, strong)

    @staticmethod
    def hint_lines(r, calls):
        """Hinweise zum Ergebnis: (Textzeilen, Warnung ja/nein). Warnung = Abbruch, rot,
        strittig; ergaenzte Bedeutungen allein sind ein Hinweis ohne Warnung."""
        lines, strong = [], False
        if not r["stufe1"]:
            strong = True
            fc = r.get("fail_card")
            text = calls[fc] if fc is not None and fc < len(calls) else ""
            lines.append(_t("sf_hint_abbruch").format(line=(fc + 1) if fc is not None else "?",
                                                      text=text))
        elif r.get("urteil") == "rot":
            strong = True
            lines.append(_t("sf_hint_rot").format(type=r.get("type") or ""))
        elif r.get("urteil") == "strittig":
            strong = True
            lines.append(_t("sf_hint_strittig"))
        meaning = [x for x in (r.get("read_as") or []) if x.get("meaning")]
        for x in meaning[:6]:
            lines.append(_t("sf_hint_read_as").format(line=x["card"] + 1, text=x["text"])
                         + f" ({_t('sf_kind_' + x['kind'])})")
        if meaning:
            lines.append(_t("sf_hint_root"))
        return lines, strong

    def _set_hints(self, lines, strong):
        self._hints.setText("<br>".join(html.escape(x) for x in lines))
        self._hints.setVisible(bool(lines))
        self._btn_edit.setVisible(bool(lines))
        if strong:
            self._status.setText("⚠ " + self._status.text())

    def _check_beat(self):
        """Ab hier zeigt der Square die Pruefbaender (Singer: Koerper-Ende, sonst Ende)."""
        r = self._result
        if not r or not r.get("targets") or r.get("urteil") not in ("gruen", "rot", "strittig"):
            return None
        starts = self._tl.call_starts
        if r["type"].lower().startswith("singer") and r.get("with_end") and starts:
            return starts[-1]
        return self._tl.total_beats

    def _band_pairs(self):
        dancers = self._tl.dancers

        def idx(t):
            return next((k for k, d in enumerate(dancers)
                         if str(d["couple"]) == t[0] and bool(d["boy"]) == (t[1] == "B")), None)
        pairs = [(idx(a), idx(b)) for a, b in self._result["targets"]]
        return [p for p in pairs if None not in p]

    def _card_at(self, beat):
        spans = self._result.get("card_spans") or []
        for i, sp in enumerate(spans):
            if sp and sp[0] <= beat < sp[1]:
                return i
        last = max((i for i, sp in enumerate(spans) if sp), default=-1)
        if last >= 0 and beat >= spans[last][1]:
            return last
        return -1

    def _seek(self, beat):
        if self._tl is None or self._tl.empty():
            return
        self._beat = max(0.0, min(beat, self._tl.total_beats))
        shown = self._beat
        if self._saving and (self._timer.isActive() or self._following):
            i = self._tl.line_at(self._beat)
            if i == self._shown_line:
                return                                # Sparmodus: nur bei Call-Wechsel zeichnen
            self._shown_line = i
            shown = self._tl.line_span(i)[1] if i >= 0 else 0.0
        pose = self._tl.pose_at(shown)
        self._floor.pose = square_chain.rotate_pose(pose) if self._view_rot else pose
        cb = self._check_beat()
        self._floor.bands = ((self._band_pairs(), self._result["urteil"] == "gruen")
                             if cb is not None and shown >= cb - 1e-6 else None)
        self._floor.update()
        self._set_card(self._card_at(self._beat))

    def _set_card(self, card):
        shown = card if self._active else -1
        if shown != self._emitted_card:
            self._emitted_card = shown
            self.current_card_changed.emit(shown)
        if card == self._card:
            return
        self._card = card
        r = self._result
        if r is None or card < 0:
            self._call_label.setText(_t("sf_call_start") if r else "")
        else:
            calls = self._seq[0] if self._seq else ()
            total = len(calls)
            text = calls[card] if card < total else ""
            beats = (r.get("card_beats") or [None] * total)[card]
            label = _t("sf_call_label").format(n=card + 1, total=total, call=text)
            if beats is not None:
                label += f"   ·   {beats:g}"
            self._call_label.setText(label)

    # --- Wiedergabe -------------------------------------------------------------

    def _interval(self):
        return 100 if self._saving else int(1000 / self._fps)

    def _bpm(self):
        try:
            bpm = float(self._bpm_source()) if self._bpm_source else 0.0
        except Exception:
            bpm = 0.0
        return bpm if bpm > 0 else FALLBACK_BPM

    # --- Mitlaufen im Singing Call (Phase 2) ------------------------------------

    def follow(self, window, pos):
        """Im Wiedergabe-Takt: Square Flow tanzt die Figur, die der Song gerade spielt.

        window = LyricsWidget.figure_window(pos) (um den Versatz verschoben, siehe
        lag_seconds): None (Dynamic Lyrics aus -> manuell),
        (-1, k, None, None, False) ausserhalb einer Figur -> Ausgangsstellung,
        (k, k, t0, t1, gespiegelt) Figur k -> Beat anteilig im Fenster t0..t1 (bei Abbruch im
        Song-Tempo bis zur Abbruchzeile, danach bleibt der Square stehen).
        Phase 2b: Die Paare tanzen ueber die Figuren weiter (Belegung aus square_chain), eine
        gespiegelte Figur wird um 90 Grad gedreht gezeigt.
        Ein Eingriff (Knoepfe, Klick im Sequenz-Detail) haelt das Mitlaufen bis zum naechsten
        Figuren-SyncPoint an."""
        if window is None:
            self.follow_off()
            return
        part, last, t0, t1, inverted = window
        region = ("f", part) if part >= 0 else ("o", last)
        self._follow_region = region
        ready = self._tl is not None and not self._tl.empty()
        if ready and self._chain is not None:
            if region == ("o", -1):
                self._chain.reset()                  # vor der ersten Figur: neuer Durchgang
            elif part >= 0:                          # auch waehrend eines Eingriffs festhalten
                self._chain.record(part, self._end_perm,
                                   self._rot_slots if inverted else None)
        if self._follow_hold is not None:
            if region == self._follow_hold or region[0] != "f":
                return
            self._follow_hold = None
        if not self._following:
            self.pause()
            self._following = True
            self._shown_line = None
        if not ready:
            return                                   # Ergebnis kommt noch
        rot = self._rot_slots if (part >= 0 and inverted) else None
        ids, broken = (self._chain.ids_for(part if part >= 0 else last + 1)
                       if self._chain is not None else (None, False))
        self._apply_view(rot, ids)
        self._chain_note.setVisible(broken)
        if part < 0:
            if self._active or self._beat > 0.0:     # nur einmal zeichnen
                self._active = False
                self._seek(0.0)
            return
        if self._result.get("stufe1"):
            beat = figure_clock.beat_in_window(pos, t0, t1, self._tl.total_beats)
        else:
            beat = figure_clock.beat_by_tempo(pos, t0, self._bpm())
        self._active = True
        self._seek(beat)

    def follow_off(self):
        """Song steht oder Dynamic Lyrics ist aus: Square Flow wieder manuell (Belegung und
        Drehung zurueck auf die Sequenz, wie sie im Sequenz-Detail steht)."""
        self._following = False
        self._follow_hold = None
        self._follow_region = None
        if self._view is not None:
            self._view, self._view_rot = None, False
            if self._tl is not None:
                self._floor.dancers = self._tl.dancers
                self._shown_line = None
                self._seek(self._beat)
            self._chain_note.setVisible(False)

    def lag_seconds(self, bpm=None):
        """Versatz im Singing Call in Song-Sekunden (Process- und Execution-Time)."""
        try:
            bpm = float(bpm) if bpm else self._bpm()
        except (TypeError, ValueError):
            bpm = self._bpm()
        return self._lag_beats * 60.0 / bpm if bpm > 0 else 0.0

    def _prepare_chain(self, result):
        """Zum neuen Ergebnis: Endplaetze der Figur und Drehung fuers Spiegeln."""
        tl = self._tl
        start = tl.pose_at(0.0)
        self._rot_slots = square_chain.rotation_slots(start)
        self._end_perm = None
        if result.get("stufe1") and result.get("with_end") and result.get("urteil") != "rot":
            self._end_perm = square_chain.end_permutation(start, tl.pose_at(tl.total_beats))
        if self._chain is None or self._chain.n != len(start):
            self._chain = square_chain.PartnerChain(len(start))

    def _apply_view(self, rot, ids):
        """Gezeigte Belegung und Drehung setzen (nur bei Aenderung neu zeichnen)."""
        n = len(self._tl.dancers)
        if ids is None or len(ids) != n:
            ids = square_chain.identity(n)
        if rot is not None and len(rot) != n:
            rot = None
        shown = tuple(square_chain.shown_dancers(ids, rot))
        view = (tuple(rot) if rot else None, shown)
        if view == self._view:
            return
        self._view = view
        self._view_rot = rot is not None
        self._floor.dancers = [self._tl.dancers[j] for j in shown]
        self._shown_line = None
        self._seek(self._beat)

    def following(self):
        return self._following

    def _user_takes_over(self):
        if self._following:
            self._following = False
            self._follow_hold = self._follow_region

    def toggle_play(self):
        self._user_takes_over()
        if self._timer.isActive():
            self.pause()
        else:
            self.play()

    def play(self, stop_at=None):
        if self._tl is None or self._tl.empty():
            return
        if self._beat >= self._tl.total_beats - 1e-6 and stop_at is None:
            self._beat = 0.0
        self._stop_at = stop_at
        self._active = True
        self._shown_line = None
        self._clock.start()
        self._timer.start(self._interval())
        self._btn_play.setText("⏸")
        self._btn_play.setToolTip(_t("sf_btn_pause"))

    def pause(self):
        self._timer.stop()
        self._stop_at = None
        self._btn_play.setText("▶")
        self._btn_play.setToolTip(_t("sf_btn_play"))

    def _tick(self):
        dt = self._clock.restart() / 1000.0
        beat = self._beat + dt * self._bpm() / 60.0
        end = self._stop_at if self._stop_at is not None else self._tl.total_beats
        if beat >= end:
            self.pause()
            self._seek(end)
            return
        self._seek(beat)

    def restart(self):
        self._user_takes_over()
        self.pause()
        self._active = False
        self._seek(0.0)

    def _card_starts(self):
        spans = (self._result.get("card_spans") or []) if self._result else []
        return sorted({sp[0] for sp in spans if sp})

    def prev_call(self):
        self._user_takes_over()
        self.pause()
        self._active = True
        starts = [s for s in self._card_starts() if s < self._beat - 1e-6]
        self._seek(starts[-1] if starts else 0.0)

    def next_call(self):
        self._user_takes_over()
        self.pause()
        self._active = True
        spans = (self._result.get("card_spans") or []) if self._result else []
        ends = sorted({sp[1] for sp in spans if sp and sp[1] > self._beat + 1e-6})
        self._seek(ends[0] if ends else self._tl.total_beats)

    def result_for(self, calls):
        """Letztes Ergebnis, wenn es zu diesen Calls gehoert, sonst None."""
        if self._result is not None and self._seq and tuple(calls) == self._seq[0]:
            return self._result
        return None

    def play_card(self, card):
        """Eine Kartenzeile im Song-Tempo tanzen (Klick im Sequenz-Detail)."""
        self._user_takes_over()
        if self._result is None or self._tl is None or self._tl.empty():
            self._pending_card = card            # wird gespielt, sobald die Animation da ist
            return
        spans = self._result.get("card_spans") or []
        if not 0 <= card < len(spans) or spans[card] is None:
            return
        start, end = spans[card]
        self.pause()
        self._seek(start)
        self.play(stop_at=end)
