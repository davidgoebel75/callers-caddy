"""Pilot-Square-Widget (BL-207) — 8 Textfelder raeumlich als Square angeordnet.

Der Caller macht sich zu den 8 Taenzern im Square Notizen (Name, Level,
Hinweise wie „braucht Blickkontakt"). Anordnung als 3x3-Raster mit den vier
Paaren an ihren realen Square-Positionen:

    .              Couple 3 (oben)     .
    Couple 4       Farb-Palette        Couple 2
    (links)        (4x4 Felder)        (rechts)
    [Leeren]       Couple 1 (unten)    [Schliessen]

Die Boxen jedes Paars folgen der realen Blickrichtung (Taenzer schauen zur
Mitte), bleiben aber normal ausgerichtet (gut les- und tippbar):
- Couple 1 (unten, Blick nach oben):  Mann links,  Frau rechts   (horizontal)
- Couple 3 (oben,  Blick nach unten): Frau links,  Mann rechts   (horizontal)
- Couple 2 (rechts, Blick nach links): Frau oben,  Mann unten    (vertikal)
- Couple 4 (links, Blick nach rechts): Mann oben,  Frau unten    (vertikal)

Mann = eckiges Quadrat, Frau = leicht abgerundetes Quadrat. Alle Elemente
wachsen mit der Widget-Groesse mit (Expanding) und haben Mindestgroessen,
damit beim Verkleinern nichts ineinanderlaeuft.

Farbe zuweisen: erst in ein Personenfeld klicken, dann ein Farbfeld in der
Mitte anklicken — das Feld wird eingefaerbt. Die Schriftfarbe wechselt
automatisch zwischen hell und dunkel, damit der Text kontrastreich bleibt.

Persistenz: bewusst fluechtig — Inhalt lebt nur, solange die App laeuft.
Der Leeren-Button setzt alles zurueck (mit Rueckfrage).
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor, QTextOption, QFont, QTextDocument, QPalette,
    QPainter, QTextCursor, QTextBlockFormat)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QSizePolicy, QMessageBox)

from i18n import _t


# ── Farb-Palette (15 Farben + 1 „ohne Farbe") ────────────────────────────────
# Reihenfolge fuellt das 4x4-Raster zeilenweise; Index 0 = neutral (Fuellung
# entfernen), danach 15 gut unterscheidbare Farben.
_NEUTRAL = None
_PALETTE_COLORS: list[Optional[str]] = [
    _NEUTRAL,   "#e74c3c", "#e67e22", "#f1c40f",
    "#2ecc71",  "#1abc9c", "#3498db", "#5b6ee1",
    "#9b59b6",  "#e84393", "#a0522d", "#95a5a6",
    "#34495e",  "#a3cb38", "#00cec9", "#d980fa",
]


def _contrast_text(bg_hex: str) -> str:
    """Waehlt Schwarz oder Weiss als Textfarbe, je nach Helligkeit von bg_hex."""
    c = QColor(bg_hex)
    lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return "#111111" if lum > 150 else "#f5f5f5"


# ── Personen-Textbox ─────────────────────────────────────────────────────────

class _PersonBox(QPlainTextEdit):
    """Ein Textfeld fuer eine Person (Mann/Frau nur fuer die Reihenfolge).

    Einheitlich abgerundete Ecken, Text horizontal wie vertikal zentriert.
    Waechst mit dem Widget (Expanding), haelt aber eine Mindestgroesse, damit
    beim Verkleinern nichts ineinanderlaeuft. Merkt sich Fuellfarbe und
    Auswahl-Zustand; beides fliesst ins Stylesheet ein.
    """

    _MIN_W = 66
    _MIN_H = 42
    _RADIUS = 12
    _MIN_FONT = 7      # pt
    _MAX_FONT = 40     # pt — Obergrenze fuer kurzen Text (fuellt die Box)
    _PLACEHOLDER_FONT = 11  # pt — normale Groesse fuer den Platzhalter

    def __init__(self, is_woman: bool, on_focus: Callable[["_PersonBox"], None],
                 placeholder: str = ""):
        super().__init__()
        self._is_woman = is_woman
        self._on_focus = on_focus
        self._fill: Optional[str] = None
        self._selected = False
        self._colors: dict = {}
        self._font_pt = self._PLACEHOLDER_FONT  # aktuelle Schriftgroesse (pt)
        self._last_top = -1     # letzter gesetzter oberer Rand (verhindert Oszillation)
        self._refitting = False  # Reentrancy-Guard fuer Auto-Size
        self._placeholder = placeholder or ""  # selbst gezeichnet (siehe paintEvent)
        # KEIN nativer Platzhalter: QPlainTextEdit zeichnet ihn links/oben,
        # ohne Umbruch und ohne Ausrichtung -> wir malen ihn selbst.
        self.setTabChangesFocus(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMinimumSize(self._MIN_W, self._MIN_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Umbruch an der Widget-Breite (Voraussetzung dafuer, dass Zentrierung wirkt)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        # Horizontale Zentrierung doppelt absichern: Dokument-Default-Option UND
        # (in _center_blocks) Block-Format — QPlainTextEdit ignoriert je nach
        # Situation das eine oder andere.
        opt = self.document().defaultTextOption()
        opt.setAlignment(Qt.AlignHCenter)
        opt.setWrapMode(QTextOption.WordWrap)
        self.document().setDefaultTextOption(opt)
        # Auto-Size + Zentrierung bei jeder Textaenderung
        self.textChanged.connect(self._refit)

    def _refit(self):
        """Passt die Schriftgroesse an den Inhalt an (Auto-Size) — auch fuer den
        Platzhalter, damit das Feld schon vor der ersten Eingabe optimal gefuellt
        ist. Groesse landet im Instanz-Stylesheet (schlaegt die globale
        QWidget-Regel) und zusaetzlich per setFont; Text wird horizontal
        (Block-Ausrichtung) und vertikal zentriert; der Platzhalter wird in
        paintEvent selbst zentriert gezeichnet."""
        if self._refitting:
            return
        self._refitting = True
        try:
            text = self.toPlainText().strip()
            content = text or self._placeholder
            self._font_pt = self._best_font_size(content) if content else self._PLACEHOLDER_FONT
            if self.font().pointSize() != self._font_pt:
                f = QFont(self.font())
                f.setPointSize(self._font_pt)
                self.setFont(f)
            self._apply_style()
            if text:
                self._center_blocks()
                self._recenter_vertical()
            else:
                # leeres Feld: Platzhalter fuellt selbst den vollen Bereich
                if self._last_top != 0:
                    self._last_top = 0
                    self.setViewportMargins(0, 0, 0, 0)
            self.viewport().update()
        finally:
            self._refitting = False

    def _center_blocks(self):
        """Zentriert alle Textzeilen horizontal (zuverlaessiger als
        defaultTextOption, das QPlainTextEdit teils ignoriert)."""
        cur = QTextCursor(self.document())
        cur.select(QTextCursor.Document)
        bf = QTextBlockFormat()
        bf.setAlignment(Qt.AlignHCenter)
        cur.mergeBlockFormat(bf)

    def _measure_doc(self, text: str, size: int, avail_w: int) -> QTextDocument:
        """Hilfs-Dokument zur Groessenmessung mit gegebener Punktgroesse."""
        f = QFont(self.font())
        f.setPointSize(size)
        doc = QTextDocument()
        doc.setDefaultFont(f)
        opt = QTextOption(Qt.AlignHCenter)
        opt.setWrapMode(QTextOption.WordWrap)  # wie beim Zeichnen (Qt.TextWordWrap)
        doc.setDefaultTextOption(opt)
        doc.setDocumentMargin(0)
        doc.setTextWidth(avail_w)
        doc.setPlainText(text)
        return doc

    def _best_font_size(self, text: str) -> int:
        """Groesste Punktgroesse, bei der der Text (mit Umbruch) in die Box passt."""
        avail_w = max(1, self.contentsRect().width() - 12)
        avail_h = max(1, self.contentsRect().height() - 10)
        for size in range(self._MAX_FONT, self._MIN_FONT - 1, -1):
            doc = self._measure_doc(text, size, avail_w)
            if doc.size().height() <= avail_h and doc.idealWidth() <= avail_w:
                return size
        return self._MIN_FONT

    def _recenter_vertical(self):
        # Textblock-Hoehe unabhaengig vom QSS-Timing messen (gleiche Punktgroesse
        # wie im Stylesheet). Basis ist der stabile contentsRect.
        avail_w = max(1, self.contentsRect().width() - 12)
        avail = self.contentsRect().height()
        text_h = self._measure_doc(self.toPlainText(), self._font_pt, avail_w).size().height()
        top = max(0, int((avail - text_h) / 2) - 2)
        if top == self._last_top:
            return
        self._last_top = top
        self.setViewportMargins(0, top, 0, 0)

    def _current_bg(self) -> str:
        if self._fill:
            return self._fill
        return self._colors.get("input_bg", "#404040")

    def paintEvent(self, event):
        super().paintEvent(event)
        # Platzhalter selbst zeichnen: zentriert, umgebrochen, in Zielgroesse und
        # Kontrastfarbe — nur wenn das Feld leer ist.
        if self.toPlainText() or not self._placeholder:
            return
        painter = QPainter(self.viewport())
        f = QFont(self.font())
        f.setPointSize(self._font_pt)
        painter.setFont(f)
        col = QColor(_contrast_text(self._current_bg()))
        col.setAlpha(150)
        painter.setPen(col)
        rect = self.viewport().rect().adjusted(4, 4, -4, -4)
        painter.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, self._placeholder)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refit()

    def showEvent(self, event):
        # Beim ersten Sichtbarwerden ist die echte Feldgroesse bekannt -> Platzhalter
        # sofort in optimaler Groesse rendern (nicht erst nach der ersten Eingabe).
        super().showEvent(event)
        self._refit()

    def fill(self) -> Optional[str]:
        """Eigene Farbe des Taenzers oder None."""
        return self._fill

    def set_fill(self, color: Optional[str]):
        self._fill = color
        self._apply_style()

    def set_selected(self, selected: bool):
        if self._selected == selected:
            return
        self._selected = selected
        self._apply_style()

    def clear_names(self):
        self.clear()
        self._refit()

    def clear_colors(self):
        self.set_fill(None)

    def clear_content(self):
        self.clear_names()
        self.clear_colors()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._on_focus(self)

    def apply_colors(self, colors: dict):
        self._colors = colors
        self._refit()

    def _apply_style(self):
        c = self._colors
        radius = self._RADIUS
        if self._fill:
            bg = self._fill
            fg = _contrast_text(self._fill)
        else:
            bg = c.get("input_bg", "#404040")
            fg = c.get("input_text", "#f0f0f0")
        if self._selected:
            border = f"2px solid {c.get('button_bg', '#615f8b')}"
        else:
            border = f"1px solid {c.get('border', '#555555')}"
        # font-size im Instanz-Stylesheet -> uebersteuert die globale
        # QWidget-Schriftregel des Skins fuer genau dieses Feld.
        self.setStyleSheet(
            f"QPlainTextEdit {{ background: {bg}; color: {fg}; "
            f"border: {border}; border-radius: {radius}px; padding: 3px; "
            f"font-size: {self._font_pt}pt; }}")
        # Platzhalter kontrastreich gegen den aktuellen Hintergrund (leicht gedimmt)
        ph = QColor(_contrast_text(bg))
        ph.setAlpha(160)
        pal = self.palette()
        pal.setColor(QPalette.PlaceholderText, ph)
        self.setPalette(pal)


# ── Farb-Swatch ──────────────────────────────────────────────────────────────

class _Swatch(QPushButton):
    """Ein anklickbares Farbfeld in der Mittel-Palette."""

    def __init__(self, color: Optional[str], on_pick: Callable[[Optional[str]], None]):
        super().__init__()
        self._color = color
        self.setMinimumSize(18, 18)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.NoFocus)  # stiehlt dem Personenfeld nicht den Fokus
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(lambda: on_pick(self._color))
        self.setToolTip(_t("square.color_none") if color is None
                        else _t("square.color_pick"))

    def apply_colors(self, colors: dict):
        if self._color is None:
            bg = colors.get("input_bg", "#404040")
            fg = colors.get("text_dim", "#888888")
            self.setText("✕")
            self.setStyleSheet(
                f"QPushButton {{ background: {bg}; color: {fg}; "
                f"border: 1px solid {colors.get('border', '#555')}; "
                f"border-radius: 4px; font-size: 12px; }}"
                f"QPushButton:hover {{ border: 2px solid "
                f"{colors.get('button_bg', '#615f8b')}; }}")
        else:
            self.setText("")
            self.setStyleSheet(
                f"QPushButton {{ background: {self._color}; "
                f"border: 1px solid {colors.get('border', '#555')}; "
                f"border-radius: 4px; }}"
                f"QPushButton:hover {{ border: 2px solid "
                f"{colors.get('text', '#f0f0f0')}; }}")


# ── Paar-Zelle ───────────────────────────────────────────────────────────────

class _CoupleCell(QWidget):
    """Ein Paar: Nummern-Label + zwei Personenboxen in der jeweiligen
    Orientierung/Reihenfolge (nach realer Blickrichtung)."""

    def __init__(self, number: int, orientation: str, order: list[str],
                 on_focus: Callable[["_PersonBox"], None]):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)

        self._label = QLabel(_t("square.couple_label").format(n=number))
        self._label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._label)

        self.man = _PersonBox(False, on_focus, _t("square.man_placeholder"))
        self.woman = _PersonBox(True, on_focus, _t("square.woman_placeholder"))
        by_key = {"man": self.man, "woman": self.woman}

        boxes = QHBoxLayout() if orientation == "h" else QVBoxLayout()
        boxes.setSpacing(4)
        for key in order:
            boxes.addWidget(by_key[key])
        lay.addLayout(boxes, stretch=1)

    def person_boxes(self) -> list[_PersonBox]:
        return [self.man, self.woman]

    def apply_colors(self, colors: dict):
        self._label.setStyleSheet(
            f"color: {colors.get('text_dim', '#999')}; "
            f"font-size: 10px; font-weight: bold;")
        self.man.apply_colors(colors)
        self.woman.apply_colors(colors)


# ── Hauptwidget ──────────────────────────────────────────────────────────────

class PilotSquareWidget(QWidget):
    """Pilot-Square-Widget: 8 Personenfelder als Square + Farb-Palette."""

    # Farbe + Name je Taenzer nach jeder Aenderung (intern#249), Form siehe dancer_data()
    dancers_changed = Signal(object)

    # Orientierung + Box-Reihenfolge je Paar (nach realer Blickrichtung).
    _LAYOUT = {
        1: ("h", ["man", "woman"]),    # unten, Blick hoch:   Mann links,  Frau rechts
        2: ("v", ["woman", "man"]),    # rechts, Blick links: Frau oben,   Mann unten
        3: ("h", ["woman", "man"]),    # oben,  Blick runter: Frau links,  Mann rechts
        4: ("v", ["man", "woman"]),    # links, Blick rechts: Mann oben,   Frau unten
    }

    def __init__(self, on_close: Optional[Callable[[], None]] = None, parent=None):
        super().__init__(parent)
        self._on_close = on_close
        self._colors: dict = {}
        self._selected_box: Optional[_PersonBox] = None
        self._couples: dict[int, _CoupleCell] = {}
        self._swatches: list[_Swatch] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        grid = QGridLayout()
        grid.setSpacing(6)
        root.addLayout(grid)

        # Alle drei Spalten/Zeilen gleich dehnbar -> Elemente fuellen die Flaeche
        for i in range(3):
            grid.setColumnStretch(i, 1)
            grid.setRowStretch(i, 1)

        for num, (orient, order) in self._LAYOUT.items():
            self._couples[num] = _CoupleCell(num, orient, order, self._select_box)
            for box in self._couples[num].person_boxes():
                box.textChanged.connect(self._emit_colors)
        grid.addWidget(self._couples[3], 0, 1)  # oben
        grid.addWidget(self._couples[4], 1, 0)  # links
        grid.addWidget(self._couples[2], 1, 2)  # rechts
        grid.addWidget(self._couples[1], 2, 1)  # unten

        # Mitte: 4x4 Farb-Palette
        palette = QWidget()
        palette.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        pgrid = QGridLayout(palette)
        pgrid.setContentsMargins(0, 0, 0, 0)
        pgrid.setSpacing(3)
        for i, color in enumerate(_PALETTE_COLORS):
            sw = _Swatch(color, self._apply_color_to_selected)
            self._swatches.append(sw)
            pgrid.addWidget(sw, i // 4, i % 4)
        grid.addWidget(palette, 1, 1)

        # Ecke links unten: drei gleich breite Leeren-Buttons uebereinander
        # (Namen / Farben / Alles). Die Buttons fuellen die Breite des
        # Containers, der sich nach dem breitesten Text richtet.
        clear_box = QWidget()
        clear_lay = QVBoxLayout(clear_box)
        clear_lay.setContentsMargins(0, 0, 0, 0)
        clear_lay.setSpacing(4)
        self._btn_clear_names = QPushButton(_t("square.clear_names_btn"))
        self._btn_clear_names.setToolTip(_t("square.clear_names_tooltip"))
        self._btn_clear_names.clicked.connect(self._on_clear_names)
        self._btn_clear_colors = QPushButton(_t("square.clear_colors_btn"))
        self._btn_clear_colors.setToolTip(_t("square.clear_colors_tooltip"))
        self._btn_clear_colors.clicked.connect(self._on_clear_colors)
        self._btn_clear = QPushButton(_t("square.clear_btn"))
        self._btn_clear.setToolTip(_t("square.clear_tooltip"))
        self._btn_clear.clicked.connect(self._on_clear)
        for btn in (self._btn_clear_names, self._btn_clear_colors,
                    self._btn_clear):
            btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            clear_lay.addWidget(btn)
        clear_box.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        grid.addWidget(clear_box, 2, 0, Qt.AlignCenter)

        # Ecke rechts unten: Schliessen (normale Buttongroesse, unten-rechts)
        self._btn_close = QPushButton(_t("square.close_btn"))
        self._btn_close.setToolTip(_t("square.close_tooltip"))
        self._btn_close.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._btn_close.clicked.connect(self._on_close_clicked)
        grid.addWidget(self._btn_close, 2, 2, Qt.AlignCenter)

        # Tabulator-Reihenfolge: Mann/Frau paarweise 1..4, dann Leeren, Schliessen.
        # (Die Farb-Swatches haben NoFocus und werden uebersprungen.)
        tab_order = [
            self._couples[1].man, self._couples[1].woman,
            self._couples[2].man, self._couples[2].woman,
            self._couples[3].man, self._couples[3].woman,
            self._couples[4].man, self._couples[4].woman,
            self._btn_clear_names, self._btn_clear_colors,
            self._btn_clear, self._btn_close,
        ]
        for first, second in zip(tab_order, tab_order[1:]):
            QWidget.setTabOrder(first, second)

    # ── Auswahl / Farbe ──
    def _select_box(self, box: _PersonBox):
        if self._selected_box is box:
            return
        if self._selected_box is not None:
            self._selected_box.set_selected(False)
        self._selected_box = box
        box.set_selected(True)

    def _apply_color_to_selected(self, color: Optional[str]):
        if self._selected_box is None:
            return
        self._selected_box.set_fill(color)
        self._emit_colors()

    def _box(self, couple: int, boy: bool) -> Optional[_PersonBox]:
        cell = self._couples.get(couple)
        if cell is None:
            return None
        return cell.man if boy else cell.woman

    def dancer_data(self) -> dict:
        """Farbe + Name je Taenzer mit Inhalt:
        {(Couple 1-4, Mann?): {"color": "#rrggbb" oder None, "name": str}}.
        Der Pilot Square ist die einzige Ablage; Square Flow zeigt nur an (intern#249)."""
        out = {}
        for num in self._couples:
            for boy in (True, False):
                box = self._box(num, boy)
                name = box.toPlainText().strip()
                if box.fill() or name:
                    out[(num, boy)] = {"color": box.fill(), "name": name}
        return out

    def _emit_colors(self):
        self.dancers_changed.emit(self.dancer_data())

    def edit_dancer(self, couple: int, boy: bool, parent=None) -> bool:
        """Modales Fenster fuer Name + Farbe eines Taenzers (Doppelklick in Square Flow).
        Schreibt direkt in das Pilot-Square-Feld; True bei OK."""
        box = self._box(int(couple), bool(boy))
        if box is None:
            return False
        from caddy.choreo.pilot_dancer_dialog import PilotDancerDialog
        who = _t("square.man_placeholder") if boy else _t("square.woman_placeholder")
        title = _t("square.couple_label").format(n=int(couple)) + " · " + who
        dlg = PilotDancerDialog(title, " ".join(box.toPlainText().split()), box.fill(),
                                _PALETTE_COLORS, self._colors, parent or self)
        if dlg.exec() != PilotDancerDialog.Accepted:
            return False
        name = dlg.result_name()
        if name != box.toPlainText().strip():
            box.setPlainText(name)          # meldet per textChanged
        if dlg.result_color() != box.fill():
            box.set_fill(dlg.result_color())
            self._emit_colors()
        return True

    # ── Leeren ──
    def _all_boxes(self) -> list[_PersonBox]:
        boxes: list[_PersonBox] = []
        for cell in self._couples.values():
            boxes.extend(cell.person_boxes())
        return boxes

    def _confirm_clear(self, has_content: bool, key: str) -> bool:
        """Sicherheitsabfrage — nur, wenn es tatsaechlich etwas zu loeschen gibt."""
        if not has_content:
            return True
        reply = QMessageBox.question(
            self, _t(f"square.{key}_confirm_title"),
            _t(f"square.{key}_confirm_msg"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return reply == QMessageBox.Yes

    def _on_clear_names(self):
        boxes = self._all_boxes()
        if not self._confirm_clear(
                any(b.toPlainText().strip() for b in boxes), "clear_names"):
            return
        for b in boxes:
            b.clear_names()

    def _on_clear_colors(self):
        boxes = self._all_boxes()
        if not self._confirm_clear(any(b.fill() for b in boxes), "clear_colors"):
            return
        for b in boxes:
            b.clear_colors()
        self._emit_colors()

    def _on_clear(self):
        boxes = self._all_boxes()
        if not self._confirm_clear(
                any(b.toPlainText().strip() or b.fill() for b in boxes), "clear"):
            return
        for b in boxes:
            b.clear_content()
        self._emit_colors()

    def _on_close_clicked(self):
        if self._on_close:
            self._on_close()

    # ── Skin ──
    def apply_skin(self, skin_mgr):
        if skin_mgr is None:
            return
        c = {
            "widget_bg":     skin_mgr.color("widget_bg",     "#363636"),
            "text":          skin_mgr.color("text",          "#f0f0f0"),
            "text_dim":      skin_mgr.color("text_dim",      "#999999"),
            "border":        skin_mgr.color("border",        "#555555"),
            "button_bg":     skin_mgr.color("button_bg",     "#615f8b"),
            "button_hover":  skin_mgr.color("button_hover",  "#7a78a5"),
            "button_text":   skin_mgr.color("button_text",   "#f7f7f7"),
            "input_bg":      skin_mgr.color("input_bg",      "#404040"),
            "input_text":    skin_mgr.color("input_text",    "#f0f0f0"),
            "warning":       skin_mgr.color("warning",       "#ef4444"),
            "warning_hover": skin_mgr.color("warning_hover", "#dc2626"),
        }
        self._colors = c

        for cell in self._couples.values():
            cell.apply_colors(c)
        for sw in self._swatches:
            sw.apply_colors(c)

        btn_style = (
            f"QPushButton {{ background: {c['button_bg']}; color: {c['button_text']}; "
            f"border: none; border-radius: 3px; padding: 6px 12px; }}"
            f"QPushButton:hover {{ background: {c['button_hover']}; }}")
        clear_style = (
            f"QPushButton {{ background: {c['warning']}; color: #fff; "
            f"border: none; border-radius: 3px; padding: 6px 12px; }}"
            f"QPushButton:hover {{ background: {c['warning_hover']}; }}")
        self._btn_close.setStyleSheet(btn_style)
        for btn in (self._btn_clear_names, self._btn_clear_colors,
                    self._btn_clear):
            btn.setStyleSheet(clear_style)
