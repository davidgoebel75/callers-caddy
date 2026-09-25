"""
To-Call-Widget fuer Callers Caddy (BL-199).

Zeigt eine Menge Calls als gleichmaessig verteilte, anklickbare Kacheln
(dynamischer Zeilenumbruch, geteilte Raster-Logik mit dem Jump-Markers-Widget).
Ziel: Der Caller sieht auf einen Blick, welche Calls er ueber den Abend noch
einsetzen will. Ein Klick markiert einen Call als "genutzt" — die Kachel bleibt
gut sichtbar, wird aber gedaempft (kontrastreich -> gedimmt, theme-basiert).

Der Status lebt nur zur Laufzeit; "Fuellen" (Kopfzeile) startet frisch.
Die Kachel-Beschriftung bricht bei Bedarf um (einheitliche Schriftgroesse,
unterschiedlich lange Call-Namen).

Platzmangel (intern#114): Die Kacheln liegen in einer QScrollArea. Passt nicht
alles hinein, klappt die Erledigt-Zone automatisch zu einer Leiste
("36 erledigt ▸") ein; reicht auch das nicht, schrumpfen die offenen Kacheln
bis _MIN_H und die Flaeche scrollt senkrecht. Ein Klick auf die Leiste klappt
auf/zu (gilt bis zum naechsten "Fuellen").
"""

from PySide6.QtWidgets import (
    QWidget, QPushButton, QLabel, QDialog, QVBoxLayout, QHBoxLayout,
    QComboBox, QListWidget, QListWidgetItem, QDialogButtonBox, QScrollArea,
    QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics

from i18n import _t
from button_grid import compute_cells, min_matrix_height


class _CallTile(QLabel):
    """Anklickbare, umbrechende Call-Kachel (optisch ein Button)."""

    def __init__(self, entity_id: str, name: str, on_toggle, parent=None):
        super().__init__(name, parent)
        self.entity_id = entity_id
        self.call_name = name
        self.used = False
        self.done_seq = 0        # Reihenfolge des Abhakens (fuer Sortierung unten)
        self.font_px = 14        # pro Kachel individuell (Auto-Fit in _relayout)
        self._fitted_for = None  # (w, h), fuer die die Schriftgroesse gilt (Cache)
        self._on_toggle = on_toggle
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignCenter)
        self.setObjectName("callTile")
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.used = not self.used
            if self._on_toggle:
                self._on_toggle(self)
        super().mousePressEvent(event)


class _DoneBar(QLabel):
    """Anklickbare Leiste der eingeklappten/aufgeklappten Erledigt-Zone."""

    def __init__(self, on_click, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self.setAlignment(Qt.AlignCenter)
        self.setObjectName("tocallDoneBar")
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._on_click:
            self._on_click()
        super().mousePressEvent(event)


class ToCallWidget(QWidget):
    """Dock-Widget: Call-Wolke zum Abhaken (BL-199)."""

    _MARGIN = 8
    _GAP = 6
    _MIN_W = 90
    _MIN_H = 34
    _MAX_H = 160      # grosszuegig: Kacheln fuellen die Flaeche, statt zu kleben
    _HEADER_H = 34
    _FONT_MIN = 9     # lange Namen duerfen kleiner werden, statt zu verschwinden
    _FONT_MAX = 30    # kurze Namen duerfen die Kachel ausfuellen
    _DONE_MIN_H = 18  # Mindesthoehe erledigter (kleiner) Kacheln
    _DONE_MAX_H = 44  # Deckel, damit erledigte unten kompakt bleiben
    _RATIO = 2.0      # angestrebtes Seitenverhaeltnis offener Kacheln (breit:hoch)
    _BAR_H = 28       # Leiste der Erledigt-Zone ("36 erledigt ▸")

    def __init__(self, skin_mgr=None, on_fill=None, parent=None,
                 perf_start=None, perf_log=None):
        super().__init__(parent)
        self._skin_mgr = skin_mgr
        self._on_fill = on_fill                  # fn() -> oeffnet Fuellen-Dialog
        self._perf_start = perf_start or (lambda: 0)
        self._perf_log = perf_log or (lambda *a, **k: None)
        self._tiles: list[_CallTile] = []
        self._done_counter = 0   # laufende Nummer fuers Abhaken (Reihenfolge unten)
        # Erledigt-Zone: None = automatisch (einklappen nur bei Platzmangel),
        # True/False = Klick auf die Leiste, gilt bis zum naechsten Fuellen.
        self._done_expanded = None
        self._done_bar_expanded = True   # zuletzt angezeigter Zustand der Leiste
        self.setMinimumSize(160, 120)

        # Kachelflaeche: Leinwand in einer Scroll-Area (intern#114). Die Kacheln
        # werden weiterhin per setGeometry gesetzt, die Leinwand waechst nur,
        # wenn nicht alles in den sichtbaren Bereich passt.
        self._scroll = QScrollArea(self)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; }")
        self._scroll.viewport().setAutoFillBackground(False)
        self._canvas = QWidget()
        self._scroll.setWidget(self._canvas)
        # Erst NACH setWidget: QScrollArea schaltet autoFillBackground der
        # Leinwand ein, sonst malt sie die Palette statt des Skin-Hintergrunds.
        self._canvas.setAutoFillBackground(False)
        self._done_bar = _DoneBar(self._on_done_bar_clicked, self._canvas)
        self._done_bar.hide()

        # Kopfzeile: "Fuellen"-Button oben rechts
        self._fill_btn = QPushButton(_t("tocall_fill"), self)
        self._fill_btn.setObjectName("tocallFill")
        self._fill_btn.setFocusPolicy(Qt.NoFocus)
        self._fill_btn.setToolTip(_t("tocall_fill_tip"))
        self._fill_btn.clicked.connect(self._on_fill_clicked)

        self._empty_label = QLabel(_t("tocall_empty"), self)
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet("color: #888888;")

        self._apply_stylesheet()
        self._relayout()

    # --- Skin ---

    def apply_skin(self, skin_mgr):
        self._skin_mgr = skin_mgr
        self._apply_stylesheet()
        for tile in self._tiles:
            self._style_tile(tile)

    def _c(self, key, fallback):
        return self._skin_mgr.color(key, fallback) if self._skin_mgr else fallback

    @staticmethod
    def _blend(hex_a: str, hex_b: str, t: float) -> str:
        """Mischt zwei #rrggbb-Farben (t=0 -> a, t=1 -> b)."""
        def _rgb(h):
            h = h.lstrip("#")
            if len(h) == 3:
                h = "".join(ch * 2 for ch in h)
            try:
                return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            except (ValueError, IndexError):
                return 128, 128, 128
        ar, ag, ab = _rgb(hex_a)
        br, bg, bb = _rgb(hex_b)
        r = round(ar + (br - ar) * t)
        g = round(ag + (bg - ag) * t)
        b = round(ab + (bb - ab) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _apply_stylesheet(self):
        bg = self._c("button_bg", "#615f8b")
        hover = self._c("button_hover", "#7a78a5")
        pressed = self._c("button_pressed", "#4e4c73")
        text = self._c("button_text", "#f7f7f7")
        border = self._c("border", "#555555")
        self.setStyleSheet(
            "QPushButton#tocallFill {"
            f" background-color: {bg}; color: {text};"
            f" border: 1px solid {border}; border-radius: 6px;"
            " padding: 2px 12px; }"
            f"QPushButton#tocallFill:hover {{ background-color: {hover}; }}"
            f"QPushButton#tocallFill:pressed {{ background-color: {pressed}; }}"
        )
        self._style_done_bar()

    def _style_tile(self, tile: _CallTile):
        """Kachel-Optik je nach Status: ungenutzt = kontrastreiche Theme-Textfarbe
        (button_text, auf button_bg gut lesbar), genutzt = gedimmt (mittlerer Ton
        zwischen Text- und Hintergrundfarbe), aber weiterhin sichtbar."""
        border = self._c("border", "#555555")
        text = self._c("button_text", "#f7f7f7")
        if tile.used:
            # Genutzt: Hintergrund UND Text wechseln -> deutlich gedaempft,
            # aber noch gut lesbar (mittlerer Ton auf gedaempftem Hintergrund).
            bg = self._c("muted_bg", "#424242")
            fg = self._c("text_dim", self._blend(text, bg, 0.5))
        else:
            bg = self._c("button_bg", "#615f8b")
            fg = text
        tile.setStyleSheet(
            "QLabel#callTile {"
            f" background-color: {bg}; color: {fg};"
            f" border: 1px solid {border}; border-radius: 8px;"
            f" padding: 2px 6px; font-weight: 600; font-size: {tile.font_px}px; }}"
        )

    def _style_done_bar(self):
        """Leiste der Erledigt-Zone: gedaempft wie erledigte Kacheln."""
        border = self._c("border", "#555555")
        bg = self._c("muted_bg", "#424242")
        fg = self._c("text_dim", self._blend(self._c("button_text", "#f7f7f7"),
                                             bg, 0.5))
        self._done_bar.setStyleSheet(
            "QLabel#tocallDoneBar {"
            f" background-color: {bg}; color: {fg};"
            f" border: 1px solid {border}; border-radius: 8px;"
            " padding: 2px 6px; font-weight: 600; font-size: 13px; }"
        )

    # Innen-Reserve fuer Rand + Padding (border 1px + padding 2px/6px, etwas Puffer)
    _PAD_W = 18
    _PAD_H = 10

    def _fit_font_px(self, text: str, w: int, h: int) -> int:
        """Groesste Schriftgroesse, bei der der (umbrechende) Text in w×h passt.

        Binaersuche ueber QFontMetrics.boundingRect mit Wortumbruch. Erst wird
        die Matrix verteilt (feste Kachelgroesse), dann fuellt jede Kachel ihren
        Text bestmoeglich aus.
        """
        avail_w = max(1, w - self._PAD_W)
        avail_h = max(1, h - self._PAD_H)
        f = QFont(self.font())
        f.setBold(True)
        lo, hi, best = self._FONT_MIN, self._FONT_MAX, self._FONT_MIN
        while lo <= hi:
            mid = (lo + hi) // 2
            f.setPixelSize(mid)
            fm = QFontMetrics(f)
            rect = fm.boundingRect(0, 0, avail_w, 100000,
                                   Qt.TextWordWrap | Qt.AlignCenter, text)
            if rect.width() <= avail_w and rect.height() <= avail_h:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    # --- Fuellen ---

    def _on_fill_clicked(self):
        if self._on_fill:
            self._on_fill()

    def fill(self, calls: list):
        """Setzt die Call-Menge neu (alle ungenutzt). calls = [(entity_id, name), ...]."""
        _t0 = self._perf_start()
        for tile in self._tiles:
            tile.deleteLater()
        self._tiles = []
        self._done_counter = 0
        self._done_expanded = None
        for eid, name in calls:
            tile = _CallTile(eid, name, self._on_tile_toggle, self._canvas)
            self._style_tile(tile)
            tile.show()
            self._tiles.append(tile)
        self._empty_label.setVisible(not self._tiles)
        self._perf_log(f"ToCall Aufbau ({len(self._tiles)} Calls)", _t0)
        self._relayout()

    def _on_tile_toggle(self, tile: _CallTile):
        if tile.used:
            self._done_counter += 1
            tile.done_seq = self._done_counter   # zuletzt erledigt -> ganz unten
        self._style_tile(tile)   # Farbe sofort umsetzen
        self._relayout()         # erledigte nach unten, offene ruecken auf

    # --- Layout ---

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _on_done_bar_clicked(self):
        # Klick schaltet den aktuellen Zustand um; gilt bis zum naechsten Fuellen.
        self._done_expanded = not self._done_bar_expanded
        self._relayout()

    def _relayout(self):
        _t0 = self._perf_start()
        # Kopfzeile: Fuellen-Button oben rechts
        bw = max(80, self._fill_btn.sizeHint().width())
        self._fill_btn.setGeometry(self.width() - bw - self._MARGIN, 4,
                                   bw, self._HEADER_H - 6)
        self._fill_btn.raise_()

        # Kachelbereich unterhalb der Kopfzeile
        area_top = self._HEADER_H
        area_h = max(1, self.height() - area_top)
        self._scroll.setGeometry(0, area_top, self.width(), area_h)
        self._empty_label.setGeometry(0, area_top, self.width(), area_h)
        n = len(self._tiles)
        if n == 0:
            self._done_bar.hide()
            self._canvas.resize(self.width(), area_h)
            return

        # Zwei Zonen: offene Calls oben (gross), erledigte unten (halbe Hoehe).
        # Erledigte in Abhak-Reihenfolge (zuletzt erledigt zuunterst).
        opens = [t for t in self._tiles if not t.used]
        dones = sorted((t for t in self._tiles if t.used),
                       key=lambda t: t.done_seq)

        # Erst mit voller Breite planen; passt es nicht, mit Platz fuer die
        # Scrollleiste neu planen (weniger Breite -> ggf. andere Spaltenzahl).
        width = self.width()
        plan = self._plan(opens, dones, width, area_h)
        if plan["content_h"] > area_h:
            width -= self._scroll.verticalScrollBar().sizeHint().width()
            plan = self._plan(opens, dones, width, area_h)
        self._canvas.resize(width, max(area_h, plan["content_h"]))

        # Leiste der Erledigt-Zone
        bar = plan["bar"]
        self._done_bar_expanded = not plan["collapsed"]
        if bar is None:
            self._done_bar.hide()
        else:
            arrow = "▾" if self._done_bar_expanded else "▸"
            self._done_bar.setText(f"{_t('tocall_done_bar', count=len(dones))} {arrow}")
            self._done_bar.setGeometry(*bar)
            self._done_bar.show()

        # Auto-Fit pro Kachel (nur wenn sich die Kachelgroesse geaendert hat,
        # 4px-Raster als Cache) und positionieren. Eingeklappte Erledigte
        # werden versteckt.
        for tile in dones if plan["collapsed"] else ():
            tile.hide()
        for tile, x, y, w, h in plan["placed"]:
            key = ((w // 4) * 4, (h // 4) * 4)
            if key != tile._fitted_for:
                tile._fitted_for = key
                tile.font_px = self._fit_font_px(tile.call_name, w, h)
                self._style_tile(tile)
            tile.setGeometry(x, y, w, h)
            tile.show()

        self._perf_log(
            f"ToCall Relayout ({len(opens)} offen / {len(dones)} erledigt)", _t0)

    def _plan(self, opens: list, dones: list, width: int, view_h: int) -> dict:
        """Verteilt die Kacheln auf die Leinwand (Breite width, sichtbare Hoehe
        view_h). Rueckgabe: placed [(tile, x, y, w, h)], bar (x, y, w, h) oder
        None, collapsed, content_h (> view_h = Scrollen noetig)."""
        grid = dict(margin=self._MARGIN, gap=self._GAP, min_w=self._MIN_W)
        open_min = (min_matrix_height(len(opens), width, min_h=self._MIN_H, **grid)
                    if opens else 0)

        # 1) Erledigt-Zone: Kacheln ~halb so hoch wie die offenen (gedeckelt).
        #    Passt beides nicht, klappt sie automatisch ein (Leiste).
        done_box = 0
        collapsed = False
        show_bar = False
        if dones:
            if opens:
                _, _, a_cells = compute_cells(
                    len(opens), width, view_h, min_h=self._MIN_H,
                    max_h=self._MAX_H, target_ratio=self._RATIO, **grid)
                h_open_full = a_cells[0][3]
            else:
                h_open_full = self._MAX_H
            done_h = int(min(self._DONE_MAX_H,
                             max(self._DONE_MIN_H, h_open_full // 2)))
            iw = max(1, width - 2 * self._MARGIN)
            cols_max = max(1, int((iw + self._GAP) // (self._MIN_W + self._GAP)))
            d_cols = min(len(dones), cols_max)
            d_rows = -(-len(dones) // d_cols)  # ceil
            done_box = d_rows * done_h + (d_rows - 1) * self._GAP + 2 * self._MARGIN
            if self._done_expanded is None:
                collapsed = open_min + done_box > view_h
            else:
                collapsed = not self._done_expanded
            # Leiste nur, wenn eingeklappt oder von Hand aufgeklappt -- passt
            # alles von selbst, bleibt die Ansicht wie bisher.
            show_bar = collapsed or self._done_expanded is True
            if collapsed:
                done_box = 0
        bar_block = (self._BAR_H + (self._MARGIN if collapsed else 0)
                     if show_bar else 0)

        # 2) Offene Zone: Rest der sichtbaren Hoehe, mindestens so hoch, dass
        #    jede Kachel _MIN_H behaelt (dann scrollt die Flaeche).
        open_h = max(open_min, view_h - bar_block - done_box) if opens else 0
        placed = []
        if opens:
            _, _, o_cells = compute_cells(
                len(opens), width, open_h, min_h=self._MIN_H,
                max_h=self._MAX_H, target_ratio=self._RATIO, **grid)
            placed += [(t, x, y, w, h) for t, (x, y, w, h) in zip(opens, o_cells)]
        bar = None
        if show_bar:
            bar = (self._MARGIN, open_h, max(1, width - 2 * self._MARGIN),
                   self._BAR_H)
        if dones and not collapsed:
            top = open_h + (self._BAR_H if show_bar else 0)
            _, _, d_cells = compute_cells(
                len(dones), width, done_box, min_h=self._DONE_MIN_H,
                max_h=self._DONE_MAX_H, **grid)
            placed += [(t, x, top + y, w, h) for t, (x, y, w, h) in zip(dones, d_cells)]
        return {"placed": placed, "bar": bar, "collapsed": collapsed,
                "content_h": open_h + bar_block + done_box}


class ToCallFillDialog(QDialog):
    """Fuellen-Dialog: Programm waehlen, Calls an-/abwaehlen, ins Widget uebernehmen
    oder als Notiz-Shortcode ablegen (BL-199).

    Ergebnis nach exec(): self.action ist "fill" oder "notes" (bei Accept),
    dazu program_label / all_names / selected_calls().
    """

    def __init__(self, db, programs: list, active_label: str = "", parent=None):
        super().__init__(parent)
        self.db = db
        self.action = ""
        self._programs = programs           # [(id, code, label, ...)]
        self.setWindowTitle(_t("tocall_fill_title"))
        self.setMinimumSize(420, 480)
        self._build_ui(active_label)
        self._reload_calls()

    def _build_ui(self, active_label: str):
        outer = QVBoxLayout(self)

        # Programm-Auswahl
        prog_row = QHBoxLayout()
        prog_row.addWidget(QLabel(_t("tocall_program")))
        self._combo = QComboBox()
        active_idx = 0
        for i, row in enumerate(self._programs):
            code, label = row[1], (row[2] or row[1])
            self._combo.addItem(label, label)  # userData = Label (= call_programs.program)
            if label == active_label:
                active_idx = i
        self._combo.setCurrentIndex(active_idx)
        self._combo.currentIndexChanged.connect(self._reload_calls)
        prog_row.addWidget(self._combo, 1)
        outer.addLayout(prog_row)

        # Alle an / aus
        toggle_row = QHBoxLayout()
        btn_all = QPushButton(_t("tocall_all_on"))
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none = QPushButton(_t("tocall_all_off"))
        btn_none.clicked.connect(lambda: self._set_all(False))
        toggle_row.addWidget(btn_all)
        toggle_row.addWidget(btn_none)
        toggle_row.addStretch()
        outer.addLayout(toggle_row)

        # Call-Checkliste
        self._list = QListWidget()
        outer.addWidget(self._list, 1)

        # Fussleiste: Fuellen | Add to Notes | Abbrechen
        btns = QDialogButtonBox()
        self._btn_fill = btns.addButton(_t("tocall_do_fill"),
                                        QDialogButtonBox.AcceptRole)
        self._btn_notes = btns.addButton(_t("tocall_add_notes"),
                                         QDialogButtonBox.ActionRole)
        btns.addButton(QDialogButtonBox.Cancel)
        self._btn_fill.clicked.connect(lambda: self._finish("fill"))
        self._btn_notes.clicked.connect(lambda: self._finish("notes"))
        btns.rejected.connect(self.reject)
        outer.addWidget(btns)

    @property
    def program_label(self) -> str:
        return self._combo.currentData() or ""

    def _reload_calls(self):
        self._list.clear()
        for eid, name in self.db.get_calls_for_program(self.program_label):
            it = QListWidgetItem(name)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)   # standardmaessig alle an
            it.setData(Qt.UserRole, eid)
            self._list.addItem(it)

    def _set_all(self, on: bool):
        state = Qt.Checked if on else Qt.Unchecked
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(state)

    @property
    def all_names(self) -> list:
        return [self._list.item(i).text() for i in range(self._list.count())]

    def selected_calls(self) -> list:
        """Angehakte Calls als [(entity_id, name), ...]."""
        out = []
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it.checkState() == Qt.Checked:
                out.append((it.data(Qt.UserRole), it.text()))
        return out

    def _finish(self, action: str):
        self.action = action
        self.accept()

