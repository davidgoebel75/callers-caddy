"""Notizen-Widget — andockbare Aufgaben- und Notizverwaltung pro Lokation.

Zwei Bereiche: Offen (oben) + Erledigt (unten).
Jede Notiz hat einen Done-Toggle (Stift offen / gruen erledigt+Haken) und
eine Auswahl-Markierung links fuer den JSON-Export.
Drag & Drop innerhalb und zwischen beiden Listen.
Trennzeilen fuer Tages-Abgrenzungen (aus Class-Import, BL-078).
Laden/Speichern als neutrale JSON-Datei (Default-Ordner: notes/).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QPoint, QSize
from PySide6.QtGui import QIcon, QFont, QPainter, QColor, QTextLayout
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QLineEdit, QSizePolicy, QFileDialog, QMessageBox,
    QDialog, QTextEdit, QDialogButtonBox)

from zoom_wheel import install_ctrl_wheel_zoom


# ── Tight-Label ───────────────────────────────────────────────────────────────

class _TightLabel(QLabel):
    """QLabel das Text per QTextLayout selbst rendert — Zeilenabstand ist
    exakt ``ascent+descent`` (ohne Leading, ohne lineSpacing-Aufschlag).
    QLabel-Standardrendering nutzt intern immer ``fm.lineSpacing()`` und liesse
    sich ueber sizeHint nicht enger stellen.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._tl_color: str | None = None  # None → Palette

    def setTightColor(self, color: str | None):
        self._tl_color = color
        self.update()

    def _tight_line_height(self) -> int:
        # Zeilenhoehe aggressiv auf ~80% der Font-Hoehe ziehen.
        # Verwendet fontMetrics() (reflektiert Stylesheet-Groesse zuverlaessig)
        # und zieht Leading + einen Teil des ueberfluessigen Ascent/Descent ab.
        fm = self.fontMetrics()
        f = self.font()
        px = f.pixelSize() if f.pixelSize() > 0 else fm.height()
        # 90% der Font-Pixelgroesse ~ kompakter Zeilenvorschub mit etwas Luft
        return max(1, int(round(px * 0.9)))

    def _wrap_lines(self, width: int) -> list[str]:
        """Bricht Text manuell auf Wort-Ebene um — volle Kontrolle ueber Zeilen."""
        fm = self.fontMetrics()
        text = self.text() or ""
        if not self.wordWrap() or width <= 0:
            return [text] if text else [""]
        lines: list[str] = []
        # Explizite Umbrueche respektieren (\n)
        for para in text.split("\n"):
            if not para:
                lines.append("")
                continue
            words = para.split(" ")
            current = ""
            for w in words:
                candidate = w if not current else current + " " + w
                if fm.horizontalAdvance(candidate) <= width:
                    current = candidate
                else:
                    if current:
                        lines.append(current)
                    # Einzelwort zu lang? Hart abbrechen lassen, nicht endlos
                    current = w
            if current:
                lines.append(current)
        return lines if lines else [""]

    def sizeHint(self) -> QSize:
        w = self.width() if self.width() > 0 else super().sizeHint().width()
        return QSize(w, self.heightForWidth(w))

    def minimumSizeHint(self) -> QSize:
        fm = self.fontMetrics()
        return QSize(0, fm.ascent() + fm.descent() + 1)

    def heightForWidth(self, w: int) -> int:
        if w <= 0:
            return self._tight_line_height()
        lines = self._wrap_lines(w)
        n = max(1, len(lines))
        fm = self.fontMetrics()
        lh = self._tight_line_height()
        # Benoetigt: (n-1) Zeilenabstaende + Ascent + Descent der letzten Zeile
        # Damit der Descender der letzten Zeile nicht abgeschnitten wird.
        return (n - 1) * lh + fm.ascent() + fm.descent() + 1

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self.font())
        if self._tl_color:
            painter.setPen(QColor(self._tl_color))
        else:
            painter.setPen(self.palette().color(self.foregroundRole()))

        fm = self.fontMetrics()
        ascent = fm.ascent()
        lh = self._tight_line_height()
        lines = self._wrap_lines(self.width())
        y = ascent  # Baseline der ersten Zeile
        for line in lines:
            painter.drawText(0, y, line)
            y += lh

from i18n import _t

_BTN_H = 26  # Hoehe fuer sekundaere Toolbar-Buttons


# ── Hilfs-Label mit Klick-Callback ───────────────────────────────────────────

class _ClickLabel(QLabel):
    """QLabel das Klicks als Callback weitergibt (vermeidet QPushButton-QSS-Konflikte)."""

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._cb = callback
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._cb()


# ── Export-Auswahl-Toggle ─────────────────────────────────────────────────────

class _SelectToggle(QLabel):
    """Anklickbarer Export-Marker: ○ (unmarkiert) / ✓ (markiert in Akzentfarbe).

    Ersetzt QCheckBox fuer die Auswahl-Markierung — Qt kann in inline-QSS kein
    sichtbares Checkmark-Bild zeichnen ohne externe SVG-Datei.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self._color_checked = "#615f8b"
        self._color_unchecked = "#888888"
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(16, 16)
        self.setAlignment(Qt.AlignCenter)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip(_t("note.tooltip_select"))
        self._refresh()

    def _refresh(self):
        if self._checked:
            self.setText("✓")
            self.setStyleSheet(
                f"color: {self._color_checked}; font-size: 13px; font-weight: bold;")
        else:
            self.setText("○")
            self.setStyleSheet(
                f"color: {self._color_unchecked}; font-size: 12px;")

    def apply_colors(self, colors: dict):
        self._color_checked = colors.get("button_bg", "#615f8b")
        self._color_unchecked = colors.get("text_dim", "#888888")
        self._refresh()

    def setChecked(self, checked: bool):
        self._checked = checked
        self._refresh()

    def isChecked(self) -> bool:
        return self._checked

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._checked = not self._checked
            self._refresh()


# ── Drag-Handle ───────────────────────────────────────────────────────────────

class _DragHandle(QLabel):
    """Drag-Handle (⠿) zum Verschieben von Zeilen per Maus."""

    def __init__(self, notes_widget: "NotesWidget", row: QWidget, parent=None):
        super().__init__("⠿", parent)
        self._nw = notes_widget
        self._row = row
        self._dragging = False
        self.setCursor(Qt.SizeVerCursor)
        self.setFixedWidth(16)
        self.setAlignment(Qt.AlignCenter)
        self.setToolTip(_t("note.drag_tooltip"))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._nw._on_note_drag(self._row,
                                   event.globalPosition().toPoint().y())

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self._nw._on_note_drop(self._row)


# ── Note Row ──────────────────────────────────────────────────────────────────

class _NoteRow(QWidget):
    """Eine einzelne Notiz-Zeile.

    Layout: [Auswahl ○/✓] [≡] [Status ✎/☑] [Text  (Timestamp wenn erledigt)]
    - Auswahl:  _SelectToggle fuer JSON-Export-Markierung
    - Status:   klickbares Label — Stift (offen) / gruener Haken (erledigt)
    """

    def __init__(self, note_id: int, text: str, is_done: bool,
                 notes_widget: "NotesWidget", done_at: str = None):
        super().__init__()
        self.note_id = note_id
        self._text = text
        self._is_done = is_done
        self._done_at = done_at
        self._nw = notes_widget
        self._font_size = 12  # px, wird per Zoom angepasst
        self._size_factor = 1.0  # Multiplikator fuer die oberste offene Notiz
        # Fallback-Farben (werden von apply_skin ueberschrieben)
        self._colors: dict = {
            "text": "#f0f0f0", "text_dim": "#888888",
            "indicator_check": "#22c55e", "border": "#555555"
        }
        self._build_ui()
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 4, 0)
        layout.setSpacing(3)

        # Auswahl-Toggle (○/✓, links)
        self._sel_tog = _SelectToggle()
        layout.addWidget(self._sel_tog)

        # Drag-Handle
        self._handle = _DragHandle(self._nw, self)
        layout.addWidget(self._handle)

        # Done-Toggle (als ClickLabel, kein Button → keine QSS-Konflikte)
        self._done_lbl = _ClickLabel(lambda: self._nw._on_row_toggled(self))
        self._done_lbl.setFixedSize(24, 24)
        self._done_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._done_lbl)

        # Text-Label (auch Timestamp-Anzeige)
        self._label = _TightLabel(self._text)
        self._label.setWordWrap(True)
        self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._label.setContentsMargins(0, 0, 0, 0)
        self._label.setTextFormat(Qt.PlainText)
        layout.addWidget(self._label, stretch=1)

        # Initiale Darstellung mit Fallback-Farben
        self._apply_done_style()

    @property
    def is_done(self) -> bool:
        return self._is_done

    @property
    def is_selected(self) -> bool:
        return self._sel_tog.isChecked()

    @property
    def note_type(self) -> str:
        return "normal"

    def set_done(self, done: bool, done_at: str = None):
        self._is_done = done
        if done_at is not None:
            self._done_at = done_at
        elif not done:
            self._done_at = None
        self._apply_done_style()

    def set_text(self, text: str):
        """Aktualisiert den Text der Notiz und das Label."""
        self._text = text or ""
        self._apply_done_style()
        self._label.updateGeometry()
        self.updateGeometry()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._nw._on_row_edit(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def apply_skin(self, colors: dict):
        self._colors = colors
        dim = colors.get("text_dim", "#888")
        self._handle.setStyleSheet(f"color: {dim}; font-size: 13px;")
        self._sel_tog.apply_colors(colors)
        self._apply_done_style()

    def set_font_size(self, px: int):
        self._font_size = px
        self._apply_done_style()

    def set_size_factor(self, factor: float):
        """Multiplikator fuer die Label-Schriftgroesse (oberste offene Notiz)."""
        if factor <= 0:
            factor = 1.0
        if abs(self._size_factor - factor) < 0.001:
            return
        self._size_factor = factor
        self._apply_done_style()
        # Layout neu berechnen — Label hat jetzt andere sizeHint-Hoehe
        self._label.updateGeometry()
        self.updateGeometry()

    def set_dragging(self, dragging: bool):
        """Hebt die Zeile waehrend des Drag-Vorgangs farblich hervor."""
        if dragging:
            hl = self._colors.get("button_bg", "#615f8b")
            self.setStyleSheet(
                f"QWidget {{ background-color: {hl}33; "
                f"border-left: 2px solid {hl}; border-radius: 2px; }}")
        else:
            self.setStyleSheet("")

    def _apply_done_style(self):
        c = self._colors
        text  = c.get("text",            "#f0f0f0")
        dim   = c.get("text_dim",        "#888888")
        green = c.get("indicator_check", "#22c55e")

        if self._is_done:
            # ☑ + Farbe + Durchstreichung → drei unabhaengige Signale (barrierearm)
            self._done_lbl.setText("☑")
            self._done_lbl.setToolTip(_t("note.tooltip_reopen"))
            self._done_lbl.setStyleSheet(
                f"color: {green}; font-size: 16px;")
            # Timestamp: "DD.MM.YY HH:MM" ans Label anfuegen
            if self._done_at:
                try:
                    dt = datetime.fromisoformat(self._done_at)
                    ts = dt.strftime("%d.%m.%y %H:%M")
                except ValueError:
                    ts = self._done_at[:16]
                body = f"{self._text}  [{ts}]"
            else:
                body = self._text
            px = max(8, int(self._font_size))
            self._label.setText(body)
            # Font-Size/Weight via Stylesheet (wirkt trotz Parent-Stylesheets),
            # Strikeout muss ueber die Font-Instanz gesetzt werden.
            self._label.setStyleSheet(
                f"QLabel {{ font-size: {px}px; font-weight: normal; "
                f"padding: 0px; margin: 0px; }}")
            f = QFont(self._label.font())
            f.setStrikeOut(True)
            self._label.setFont(f)
            self._label.setTightColor(dim)
        else:
            self._done_lbl.setText("☐")
            self._done_lbl.setToolTip(_t("note.tooltip_done"))
            self._done_lbl.setStyleSheet(
                f"color: {dim}; font-size: 16px;")
            # Oberste offene Notiz: Faktor fuer bessere Sichtbarkeit aus Distanz.
            # _TightLabel rendert Text per QTextLayout → Zeilenabstand = ascent+descent.
            px = max(8, int(self._font_size * self._size_factor))
            weight = "bold" if self._size_factor > 1.01 else "normal"
            self._label.setText(self._text)
            self._label.setStyleSheet(
                f"QLabel {{ font-size: {px}px; font-weight: {weight}; "
                f"padding: 0px; margin: 0px; }}")
            f = QFont(self._label.font())
            f.setStrikeOut(False)
            self._label.setFont(f)
            self._label.setTightColor(text)
        # Stylesheet erzwingt polish damit fontMetrics() die neue Groesse hat
        self._label.style().unpolish(self._label)
        self._label.style().polish(self._label)
        self._label.updateGeometry()
        self._label.update()


# ── Separator Row ─────────────────────────────────────────────────────────────

class _SepRow(QWidget):
    """Trennzeile zwischen Tages-Abschnitten."""

    def __init__(self, note_id: int, label: str, notes_widget: "NotesWidget"):
        super().__init__()
        self.note_id = note_id
        self._label_text = label or ""
        self._nw = notes_widget
        self._is_done = False
        self._colors: dict = {}
        self._font_size = 12
        self._build_ui()
        self.setMinimumHeight(22)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 4, 0)
        layout.setSpacing(4)

        # Platz-Halter fuer Auswahl-Toggle (alignment)
        spacer = QWidget()
        spacer.setFixedSize(16, 16)
        layout.addWidget(spacer)

        self._handle = _DragHandle(self._nw, self)
        layout.addWidget(self._handle)

        line_l = QFrame()
        line_l.setFrameShape(QFrame.HLine)
        line_l.setFixedWidth(16)
        layout.addWidget(line_l)

        self._lbl = QLabel(self._label_text)
        layout.addWidget(self._lbl)

        line_r = QFrame()
        line_r.setFrameShape(QFrame.HLine)
        line_r.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(line_r)

    @property
    def is_done(self) -> bool:
        return self._is_done

    @property
    def is_selected(self) -> bool:
        return False  # Trennzeilen werden immer mitexportiert wenn sichtbar

    @property
    def note_type(self) -> str:
        return "separator"

    def set_done(self, done: bool, done_at: str = None):
        self._is_done = done

    def apply_skin(self, colors: dict):
        self._colors = colors
        dim = colors.get("text_dim", "#888")
        self._lbl.setStyleSheet(
            f"color: {dim}; font-size: {self._font_size}px;")
        self._handle.setStyleSheet(f"color: {dim}; font-size: 13px;")

    def set_font_size(self, px: int):
        self._font_size = px
        dim = self._colors.get("text_dim", "#888")
        self._lbl.setStyleSheet(
            f"color: {dim}; font-size: {self._font_size}px;")

    def set_dragging(self, dragging: bool):
        if dragging:
            hl = self._colors.get("button_bg", "#615f8b")
            self.setStyleSheet(
                f"QWidget {{ background-color: {hl}33; "
                f"border-left: 2px solid {hl}; border-radius: 2px; }}")
        else:
            self.setStyleSheet("")


# ── Section Header ────────────────────────────────────────────────────────────

class _SectionHeader(QWidget):
    """Farbig hinterlegter Abschnitts-Header (OFFEN / ERLEDIGT)."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setAutoFillBackground(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        self._lbl = QLabel(title)
        self._lbl.setStyleSheet("font-size: 10px; font-weight: bold;")
        layout.addWidget(self._lbl)
        layout.addStretch()

    def apply_skin(self, colors: dict):
        bg  = colors.get("title_bg",  "#424242")
        txt = colors.get("text_dim",  "#bbbbbb")
        self.setStyleSheet(
            f"_SectionHeader {{ background-color: {bg}; border-radius: 3px; }}")
        self._lbl.setStyleSheet(
            f"font-size: 10px; font-weight: bold; color: {txt};")


# ── Notes List ────────────────────────────────────────────────────────────────

class _NotesList(QScrollArea):
    """Scrollbare Liste von Notiz- und Trennzeilen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch()
        self.setWidget(self._container)

    def add_row(self, row: QWidget, index: Optional[int] = None):
        n = self._layout.count() - 1
        ins = n if (index is None or index >= n) else max(0, index)
        self._layout.insertWidget(ins, row)
        row.show()

    def remove_row(self, row: QWidget):
        self._layout.removeWidget(row)
        row.hide()

    def row_count(self) -> int:
        return self._layout.count() - 1

    def rows(self) -> list:
        result = []
        for i in range(self._layout.count() - 1):
            item = self._layout.itemAt(i)
            if item and item.widget():
                result.append(item.widget())
        return result

    def index_of(self, row: QWidget) -> int:
        for i in range(self._layout.count() - 1):
            item = self._layout.itemAt(i)
            if item and item.widget() is row:
                return i
        return -1

    def clear_rows(self):
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def insert_at_global_y(self, row: QWidget, global_y: int):
        n = self._layout.count() - 1
        target_idx = n
        for i in range(n):
            item = self._layout.itemAt(i)
            if not item:
                continue
            w = item.widget()
            if w is None or w is row:
                continue
            mid_y = w.mapToGlobal(w.rect().center()).y()
            if global_y < mid_y:
                target_idx = i
                break
        src_idx = self.index_of(row)
        if src_idx < 0 or src_idx == target_idx:
            return
        self._layout.removeWidget(row)
        ins = target_idx if target_idx <= src_idx else target_idx - 1
        self._layout.insertWidget(max(0, ins), row)

    def contains_global_y(self, global_y: int) -> bool:
        top = self.mapToGlobal(QPoint(0, 0)).y()
        return top <= global_y <= top + self.height()

    def apply_skin(self, bg_color: str, border_color: str):
        """Setzt Hintergrundfarbe der Liste (farblich vom Widget-Hintergrund abgesetzt)."""
        self._container.setStyleSheet(
            f"QWidget {{ background-color: {bg_color}; }}")
        self.setStyleSheet(
            f"QScrollArea {{ background-color: {bg_color}; "
            f"border: 1px solid {border_color}; border-radius: 3px; }}")


# ── Edit-Dialog ───────────────────────────────────────────────────────────────

class _NoteEditDialog(QDialog):
    """Kleiner Dialog zum Bearbeiten des Notiz-Textes (mehrzeilig)."""

    def __init__(self, parent, text: str, colors: dict):
        super().__init__(parent)
        self.setWindowTitle(_t("note.edit_title"))
        self.setModal(True)
        self.resize(480, 220)

        c = colors or {}
        bg = c.get("widget_bg", "#363636")
        fg = c.get("text", "#f0f0f0")
        inp_bg = c.get("input_bg", "#404040")
        inp_fg = c.get("input_text", "#f0f0f0")
        btn_bg = c.get("button_bg", "#615f8b")
        btn_hov = c.get("button_hover", "#7a78a5")
        btn_fg = c.get("button_text", "#f7f7f7")
        border = c.get("border", "#555555")
        self.setStyleSheet(
            f"QDialog {{ background-color: {bg}; color: {fg}; }} "
            f"QLabel {{ color: {fg}; background: transparent; }} "
            f"QTextEdit {{ background: {inp_bg}; color: {inp_fg}; "
            f"border: 1px solid {border}; border-radius: 3px; padding: 4px; }} "
            f"QPushButton {{ background: {btn_bg}; color: {btn_fg}; "
            f"border: none; border-radius: 3px; padding: 6px 14px; }} "
            f"QPushButton:hover {{ background: {btn_hov}; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self._edit = QTextEdit()
        self._edit.setPlainText(text or "")
        self._edit.setAcceptRichText(False)
        self._edit.selectAll()
        lay.addWidget(self._edit, stretch=1)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        # Ctrl+Enter = OK
        self._edit.setFocus()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and \
                event.modifiers() & Qt.ControlModifier:
            self.accept()
            return
        super().keyPressEvent(event)

    def text(self) -> str:
        return self._edit.toPlainText()

    @staticmethod
    def edit(parent, text: str, colors: dict) -> "str | None":
        """Zeigt den Dialog. Gibt neuen Text oder None (bei Cancel) zurueck."""
        dlg = _NoteEditDialog(parent, text, colors)
        if dlg.exec() == QDialog.Accepted:
            return dlg.text()
        return None


# ── Main Widget ───────────────────────────────────────────────────────────────

class NotesWidget(QWidget):
    """Notizen-Widget: offene + erledigte Aufgaben pro Lokation."""

    _ZOOM_DEFAULT = 100
    _ZOOM_MIN = 50
    _ZOOM_MAX = 200
    _ZOOM_STEP = 10
    _FONT_BASE = 12  # px bei 100 %
    _FIRST_FACTOR_DEFAULT = 4.0  # Oberste offene Notiz: 4x Schriftgroesse

    def __init__(self, db, app_dir: str = "", parent=None):
        super().__init__(parent)
        self._db = db
        self._notes_dir = os.path.join(app_dir, "notes") if app_dir else ""
        self._location_id: Optional[int] = None
        self._colors: dict = {}
        self._skin_mgr = None
        self._zoom_pct = self._ZOOM_DEFAULT
        self._first_note_factor = self._FIRST_FACTOR_DEFAULT
        self._dragging_row: Optional[QWidget] = None
        self._drag_current_list: Optional[_NotesList] = None
        # Shortcode-Callback: wird von MainWindow gesetzt
        self.on_shortcode_execute = None   # Callable[[str, dict], None]
        self._build_ui()

    # ── UI Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)

        # Kopfzeile: Lokations-Info (links) + Zoom-Controls (rechts)
        head_row = QHBoxLayout()
        head_row.setSpacing(4)

        self._loc_label = QLabel(_t("note.no_location_hint"))
        self._loc_label.setStyleSheet("font-size: 10px; padding: 0px;")
        head_row.addWidget(self._loc_label, stretch=1)

        self._btn_zoom_out = QPushButton("−")
        self._btn_zoom_out.setFixedSize(24, 22)
        self._btn_zoom_out.setToolTip(_t("tooltip_zoom_out"))
        self._btn_zoom_out.clicked.connect(self._on_zoom_out)
        head_row.addWidget(self._btn_zoom_out)

        self._label_zoom = QLabel(f"{self._zoom_pct}%")
        self._label_zoom.setAlignment(Qt.AlignCenter)
        self._label_zoom.setFixedWidth(40)
        self._label_zoom.setStyleSheet("font-size: 11px;")
        head_row.addWidget(self._label_zoom)

        self._btn_zoom_in = QPushButton("+")
        self._btn_zoom_in.setFixedSize(24, 22)
        self._btn_zoom_in.setToolTip(_t("tooltip_zoom_in"))
        self._btn_zoom_in.clicked.connect(self._on_zoom_in)
        head_row.addWidget(self._btn_zoom_in)

        root.addLayout(head_row)

        # Eingabe-Zeile
        input_row = QHBoxLayout()
        input_row.setSpacing(4)
        self._input = QLineEdit()
        self._input.setPlaceholderText(_t("note.placeholder"))
        self._input.setFixedHeight(_BTN_H)
        self._input.returnPressed.connect(self._on_add_note)
        input_row.addWidget(self._input, stretch=1)

        self._btn_add = QPushButton(_t("note.btn_add"))
        self._btn_add.setFixedSize(32, _BTN_H)
        self._btn_add.setToolTip(_t("note.btn_add_tooltip"))
        self._btn_add.clicked.connect(self._on_add_note)
        input_row.addWidget(self._btn_add)

        root.addLayout(input_row)

        # Aktions-Buttons
        actions = QHBoxLayout()
        actions.setSpacing(4)
        self._btn_load = QPushButton(_t("note.btn_load"))
        self._btn_load.setFixedHeight(_BTN_H)
        self._btn_load.setToolTip(_t("note.btn_load_tooltip"))
        self._btn_load.clicked.connect(self._on_load_json)
        actions.addWidget(self._btn_load)

        self._btn_save = QPushButton(_t("note.btn_save"))
        self._btn_save.setFixedHeight(_BTN_H)
        self._btn_save.setToolTip(_t("note.btn_save_tooltip"))
        self._btn_save.clicked.connect(self._on_save_json)
        actions.addWidget(self._btn_save)

        self._btn_sel_all = QPushButton(_t("note.btn_select_all"))
        self._btn_sel_all.setFixedHeight(_BTN_H)
        self._btn_sel_all.setToolTip(_t("note.btn_select_all_tooltip"))
        self._btn_sel_all.clicked.connect(self._on_select_all)
        actions.addWidget(self._btn_sel_all)

        self._btn_desel_all = QPushButton(_t("note.btn_deselect_all"))
        self._btn_desel_all.setFixedHeight(_BTN_H)
        self._btn_desel_all.setToolTip(_t("note.btn_deselect_all_tooltip"))
        self._btn_desel_all.clicked.connect(self._on_deselect_all)
        actions.addWidget(self._btn_desel_all)

        actions.addStretch()

        self._btn_done_all = QPushButton(_t("note.btn_done_all"))
        self._btn_done_all.setFixedHeight(_BTN_H)
        self._btn_done_all.setToolTip(_t("note.btn_done_all_tooltip"))
        self._btn_done_all.clicked.connect(self._on_done_all)
        actions.addWidget(self._btn_done_all)

        self._btn_delete = QPushButton(_t("note.btn_delete"))
        self._btn_delete.setFixedHeight(_BTN_H)
        self._btn_delete.setToolTip(_t("note.btn_delete_tooltip"))
        self._btn_delete.clicked.connect(self._on_delete_done)
        actions.addWidget(self._btn_delete)
        root.addLayout(actions)

        # Bereich Offen
        self._open_header = _SectionHeader(_t("note.section_open"))
        root.addWidget(self._open_header)
        self._open_list = _NotesList()
        self._open_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self._open_list, stretch=3)

        # Bereich Erledigt
        self._done_header = _SectionHeader(_t("note.section_done"))
        root.addWidget(self._done_header)
        self._done_list = _NotesList()
        self._done_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self._done_list, stretch=1)

        # BL-166: STRG + Mausrad zoomt wie die +/- Buttons
        for _lst in (self._open_list, self._done_list):
            install_ctrl_wheel_zoom(_lst, self._on_zoom_in, self._on_zoom_out)

    # ── Data Loading ──────────────────────────────────────────────────────────

    def refresh(self, location_id: Optional[int] = None):
        """Laedt Notizen fuer die angegebene Lokation neu."""
        if location_id is not None:
            self._location_id = location_id
        self._open_list.clear_rows()
        self._done_list.clear_rows()

        if self._location_id is None:
            self._loc_label.setText(_t("note.no_location_hint"))
            return

        # Lokationsname ermitteln
        loc_name = self._get_location_name(self._location_id)
        self._loc_label.setText(_t("note.location_hint").format(name=loc_name))

        notes = self._db.get_notes(self._location_id)
        for n in notes:
            row = self._make_row(n["id"], n["text"],
                                 n["note_type"], n["status"] == "done",
                                 n.get("done_at"))
            if n["status"] == "done":
                self._done_list.add_row(row)
            else:
                self._open_list.add_row(row)

        self._apply_skin_to_rows()
        self._apply_zoom()
        self._update_sep_visibility()

    def _get_location_name(self, location_id: int) -> str:
        try:
            row = self._db._conn.execute(
                "SELECT name FROM locations WHERE id = ?", (location_id,)
            ).fetchone()
            return row[0] if row else str(location_id)
        except Exception:
            return str(location_id)

    def _make_row(self, note_id: int, text: str,
                  note_type: str, is_done: bool,
                  done_at: str = None) -> QWidget:
        if note_type == "separator":
            return _SepRow(note_id, text, self)
        return _NoteRow(note_id, text, is_done, self, done_at=done_at)

    # ── Toggle ────────────────────────────────────────────────────────────────

    def _on_row_toggled(self, row: QWidget):
        now = datetime.now().isoformat(timespec="seconds")
        if row.is_done:
            self._db.set_note_status(row.note_id, "open", done_at=None)
            row.set_done(False)
            self._done_list.remove_row(row)
            self._open_list.add_row(row, index=0)
        else:
            # Shortcodes ausfuehren wenn eine offene Notiz abgehakt wird
            if self.on_shortcode_execute and getattr(row, "note_type", "") == "normal":
                from shortcode_parser import parse_shortcodes
                for sc in parse_shortcodes(getattr(row, '_text', '')):
                    try:
                        self.on_shortcode_execute(sc.action_id, sc.params)
                    except Exception:
                        pass
            self._db.set_note_status(row.note_id, "done", done_at=now)
            row.set_done(True, done_at=now)
            self._open_list.remove_row(row)
            self._done_list.add_row(row, index=0)
        row.apply_skin(self._colors)
        self._save_order()
        self._update_sep_visibility()
        self._refresh_first_highlight()

    # ── Edit per Doppelklick ──────────────────────────────────────────────────

    def _on_row_edit(self, row: "_NoteRow"):
        """Oeffnet den Edit-Dialog fuer die Notiz und speichert bei OK."""
        if not isinstance(row, _NoteRow):
            return
        new_text = _NoteEditDialog.edit(self, row._text, self._colors)
        if new_text is None:
            return
        new_text = new_text.strip()
        if not new_text or new_text == row._text:
            return
        self._db.update_note_text(row.note_id, new_text)
        row.set_text(new_text)
        self._refresh_first_highlight()

    # ── Drag & Drop ───────────────────────────────────────────────────────────

    def _on_note_drag(self, row: QWidget, global_y: int):
        if self._dragging_row is None:
            self._dragging_row = row
            self._drag_current_list = (
                self._open_list if self._open_list.index_of(row) >= 0
                else self._done_list)
            if hasattr(row, "set_dragging"):
                row.set_dragging(True)

        if self._open_list.contains_global_y(global_y):
            target_list = self._open_list
        elif self._done_list.contains_global_y(global_y):
            target_list = self._done_list
        else:
            return

        if target_list is not self._drag_current_list:
            self._drag_current_list.remove_row(row)
            target_list.add_row(row, index=0)
            self._drag_current_list = target_list
            row.show()

        self._drag_current_list.insert_at_global_y(row, global_y)

    def _on_note_drop(self, row: QWidget):
        if self._dragging_row is None:
            return
        if hasattr(row, "set_dragging"):
            row.set_dragging(False)
        dropped_in_done = self._drag_current_list is self._done_list
        if row.is_done != dropped_in_done:
            now = datetime.now().isoformat(timespec="seconds")
            if dropped_in_done:
                self._db.set_note_status(row.note_id, "done", done_at=now)
                row.set_done(True, done_at=now)
            else:
                self._db.set_note_status(row.note_id, "open", done_at=None)
                row.set_done(False)
            row.apply_skin(self._colors)
        self._dragging_row = None
        self._drag_current_list = None
        self._save_order()
        self._update_sep_visibility()
        self._refresh_first_highlight()

    # ── Add Note ──────────────────────────────────────────────────────────────

    def _on_add_note(self):
        text = self._input.text().strip()
        if not text or self._location_id is None:
            return
        is_sep = text.startswith("---")
        label = text[3:].strip() if is_sep else text
        note_type = "separator" if is_sep else "normal"
        note_id = self._db.add_note(
            label, self._location_id, note_type=note_type, sort_order=0)
        row = self._make_row(note_id, label, note_type, False)
        row.apply_skin(self._colors)
        px = max(8, int(self._FONT_BASE * self._zoom_pct / 100))
        if hasattr(row, "set_font_size"):
            row.set_font_size(px)
        self._open_list.add_row(row, index=0)
        self._input.clear()
        self._save_order()
        self._refresh_first_highlight()

    def add_note(self, text: str):
        """Fuegt eine Notiz oben in die offene Liste ein (API fuer externe Aufrufer)."""
        if not text or self._location_id is None:
            return
        note_id = self._db.add_note(text, self._location_id, note_type="normal", sort_order=0)
        row = self._make_row(note_id, text, "normal", False)
        row.apply_skin(self._colors)
        px = max(8, int(self._FONT_BASE * self._zoom_pct / 100))
        if hasattr(row, "set_font_size"):
            row.set_font_size(px)
        self._open_list.add_row(row, index=0)
        self._save_order()
        self._refresh_first_highlight()

    # ── JSON Laden/Speichern ──────────────────────────────────────────────────

    def _get_notes_dir(self) -> str:
        """Gibt den notes/-Ordner zurueck, legt ihn bei Bedarf an."""
        if self._notes_dir:
            os.makedirs(self._notes_dir, exist_ok=True)
            return self._notes_dir
        return ""

    def _on_load_json(self):
        if self._location_id is None:
            QMessageBox.warning(self, _t("note.no_location_title"),
                                _t("note.no_location_msg"))
            return
        start_dir = self._get_notes_dir()
        path, _ = QFileDialog.getOpenFileName(
            self, _t("note.load_title"), start_dir, "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                items = json.load(f)
            if not isinstance(items, list):
                raise ValueError("Keine Liste")
        except Exception as e:
            QMessageBox.critical(self, _t("note.load_error_title"),
                                 _t("note.load_error_msg").format(error=str(e)))
            return

        source_ref = os.path.basename(path)
        imported = 0
        # Reihenfolge beibehalten: ersten importierten oben, letzten darunter
        for item in items:
            text = item.get("text", "").strip()
            note_type = "separator" if item.get("type") == "separator" else "normal"
            if not text:
                continue
            note_id = self._db.add_note(
                text, self._location_id,
                note_type=note_type, sort_order=0,
                source="import", source_ref=source_ref)
            row = self._make_row(note_id, text, note_type, False)
            row.apply_skin(self._colors)
            px = max(8, int(self._FONT_BASE * self._zoom_pct / 100))
            if hasattr(row, "set_font_size"):
                row.set_font_size(px)
            # Jede Zeile oben einfuegen, danach die naechste darunter
            self._open_list.add_row(row, index=imported)
            imported += 1

        self._save_order()
        self._update_sep_visibility()
        QMessageBox.information(self, _t("note.load_ok_title"),
                                _t("note.load_ok_msg").format(count=imported))

    def _on_save_json(self):
        """Exportiert markierte offene Notizen (oder alle, wenn nichts markiert)."""
        all_rows = self._open_list.rows()
        selected = [r for r in all_rows if r.is_selected]
        export_rows = selected if selected else all_rows

        if not export_rows:
            QMessageBox.information(self, _t("note.save_empty_title"),
                                    _t("note.save_empty_msg"))
            return

        start_dir = self._get_notes_dir()
        default_file = os.path.join(start_dir, "notizen.json") if start_dir else "notizen.json"
        path, _ = QFileDialog.getSaveFileName(
            self, _t("note.save_title"), default_file, "JSON (*.json)")
        if not path:
            return

        data = []
        for row in export_rows:
            data.append({
                "text": row._label_text if isinstance(row, _SepRow) else row._text,
                "type": row.note_type
            })
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, _t("note.save_error_title"),
                                 _t("note.save_error_msg").format(error=str(e)))
            return
        # Auswahl zuruecksetzen
        for row in selected:
            if hasattr(row, '_sel_tog'):
                row._sel_tog.setChecked(False)
        QMessageBox.information(self, _t("note.save_ok_title"),
                                _t("note.save_ok_msg").format(path=path))

    # ── Alle erledigen / Papierkorb ───────────────────────────────────────────

    def _on_done_all(self):
        if self._location_id is None:
            return
        now = datetime.now().isoformat(timespec="seconds")
        for row in self._open_list.rows()[:]:
            self._db.set_note_status(row.note_id, "done", done_at=now)
            row.set_done(True, done_at=now)
            self._open_list.remove_row(row)
            self._done_list.add_row(row, index=0)
            row.apply_skin(self._colors)
        self._save_order()
        self._update_sep_visibility()

    # ── Zoom ─────────────────────────────────────────────────────────────────

    def set_zoom(self, pct: int):
        """Setzt Zoom-Level ohne Schreiben in INI (fuer Restore beim Start)."""
        self._zoom_pct = max(self._ZOOM_MIN, min(self._ZOOM_MAX, pct))
        self._apply_zoom()

    def _on_zoom_out(self):
        self._zoom_pct = max(self._ZOOM_MIN, self._zoom_pct - self._ZOOM_STEP)
        self._apply_zoom()

    def _on_zoom_in(self):
        self._zoom_pct = min(self._ZOOM_MAX, self._zoom_pct + self._ZOOM_STEP)
        self._apply_zoom()

    def _apply_zoom(self):
        self._label_zoom.setText(f"{self._zoom_pct}%")
        px = max(8, int(self._FONT_BASE * self._zoom_pct / 100))
        for row in self._open_list.rows() + self._done_list.rows():
            if hasattr(row, "set_font_size"):
                row.set_font_size(px)
        self._refresh_first_highlight()

    def _refresh_first_highlight(self):
        """Wendet den Vergroesserungsfaktor auf die erste offene Notiz an.
        Separatoren werden uebersprungen. Alle anderen Rows laufen mit 1.0."""
        first_applied = False
        for row in self._open_list.rows():
            if not hasattr(row, "set_size_factor"):
                continue
            is_first_note = (
                not first_applied
                and getattr(row, "note_type", "") == "normal"
                and not getattr(row, "is_done", False)
            )
            if is_first_note:
                row.set_size_factor(self._first_note_factor)
                first_applied = True
            else:
                row.set_size_factor(1.0)
        for row in self._done_list.rows():
            if hasattr(row, "set_size_factor"):
                row.set_size_factor(1.0)

    def set_first_note_factor(self, factor: float):
        """Setzt den Multiplikator fuer die oberste offene Notiz (aus INI)."""
        try:
            f = float(factor)
        except (TypeError, ValueError):
            f = self._FIRST_FACTOR_DEFAULT
        self._first_note_factor = max(1.0, min(10.0, f))
        self._refresh_first_highlight()

    def tick_top_open_note(self) -> bool:
        """Markiert die oberste offene Notiz als erledigt.
        Shortcodes in der Notiz werden vorher ausgefuehrt.
        Gibt True zurueck wenn getickt; False bei leerer Liste."""
        for row in self._open_list.rows():
            if (getattr(row, "note_type", "") == "normal"
                    and not getattr(row, "is_done", False)):
                self._on_row_toggled(row)
                return True
        return False

    def _on_select_all(self):
        """Alle offenen Notizen fuer Export markieren."""
        for row in self._open_list.rows():
            if hasattr(row, '_sel_tog'):
                row._sel_tog.setChecked(True)

    def _on_deselect_all(self):
        """Alle Export-Markierungen aufheben."""
        for row in self._open_list.rows():
            if hasattr(row, '_sel_tog'):
                row._sel_tog.setChecked(False)

    def _on_delete_done(self):
        if self._location_id is None:
            return
        done_rows = self._done_list.rows()
        if not done_rows:
            return
        reply = QMessageBox.question(
            self, _t("note.delete_confirm_title"),
            _t("note.delete_confirm_msg").format(count=len(done_rows)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self._db.delete_notes([r.note_id for r in done_rows])
        self._done_list.clear_rows()

    # ── Hilfsmethoden ────────────────────────────────────────────────────────

    def _save_order(self):
        orders = []
        for idx, row in enumerate(self._open_list.rows()):
            orders.append((row.note_id, idx))
        offset = len(orders)
        for idx, row in enumerate(self._done_list.rows()):
            orders.append((row.note_id, offset + idx))
        if orders:
            self._db.update_notes_order(orders)

    def _update_sep_visibility(self):
        """Trennzeile ausblenden wenn keine offenen Notizen darueber existieren."""
        rows = self._open_list.rows()
        has_open_above = False
        for row in rows:
            if isinstance(row, _SepRow):
                row.setVisible(has_open_above)
                has_open_above = False
            else:
                has_open_above = True

    # ── Skin ─────────────────────────────────────────────────────────────────

    def apply_skin(self, skin_mgr):
        if skin_mgr is None:
            return
        self._skin_mgr = skin_mgr
        c = {
            "widget_bg":       skin_mgr.color("widget_bg",       "#363636"),
            "title_bg":        skin_mgr.color("title_bg",        "#424242"),
            "text":            skin_mgr.color("text",             "#f0f0f0"),
            "text_dim":        skin_mgr.color("text_dim",         "#999999"),
            "border":          skin_mgr.color("border",           "#555555"),
            "button_bg":       skin_mgr.color("button_bg",        "#615f8b"),
            "button_hover":    skin_mgr.color("button_hover",     "#7a78a5"),
            "button_text":     skin_mgr.color("button_text",      "#f7f7f7"),
            "input_bg":        skin_mgr.color("input_bg",         "#404040"),
            "input_text":      skin_mgr.color("input_text",       "#f0f0f0"),
            "indicator_check": skin_mgr.color("indicator_check",  "#22c55e"),
            "warning":         skin_mgr.color("warning",          "#ef4444"),
            "warning_hover":   skin_mgr.color("warning_hover",    "#dc2626"),
        }
        self._colors = c

        # Lokations-Label — gleiche Farbe wie Songtitel, lesbare Größe
        self._loc_label.setStyleSheet(
            f"color: {c['text']}; font-size: 12px;")

        # Zoom-Buttons: Icons aus dem zentralen Icon-Cache, Fallback Text
        skin_dir = skin_mgr.icon_dir.replace("\\", "/") if skin_mgr.icon_dir else ""
        if skin_dir:
            self._btn_zoom_out.setIcon(QIcon(f"{skin_dir}/zoom-out.svg"))
            self._btn_zoom_out.setText("")
            self._btn_zoom_in.setIcon(QIcon(f"{skin_dir}/zoom-in.svg"))
            self._btn_zoom_in.setText("")
        self._label_zoom.setStyleSheet(f"font-size: 11px; color: {c['text_dim']};")

        # Input
        self._input.setStyleSheet(
            f"QLineEdit {{ background: {c['input_bg']}; color: {c['input_text']}; "
            f"border: 1px solid {c['border']}; border-radius: 3px; "
            f"padding: 2px 4px; }}")

        # Standard-Buttons
        btn_style = (
            f"QPushButton {{ background: {c['button_bg']}; color: {c['button_text']}; "
            f"border: none; border-radius: 3px; padding: 2px 8px; }}"
            f"QPushButton:hover {{ background: {c['button_hover']}; }}")
        del_style = (
            f"QPushButton {{ background: {c['warning']}; color: #fff; "
            f"border: none; border-radius: 3px; padding: 2px 8px; }}"
            f"QPushButton:hover {{ background: {c['warning_hover']}; }}")
        for btn in (self._btn_add, self._btn_load, self._btn_save,
                    self._btn_sel_all, self._btn_desel_all, self._btn_done_all,
                    self._btn_zoom_out, self._btn_zoom_in):
            btn.setStyleSheet(btn_style)
        self._btn_delete.setStyleSheet(del_style)

        # Section-Header
        self._open_header.apply_skin(c)
        self._done_header.apply_skin(c)

        # Beide Listen gleiche Hintergrundfarbe (input_bg) — einheitliches Erscheinungsbild
        list_bg = c.get("input_bg", "#404040")
        border  = c.get("border", "#555555")
        self._open_list.apply_skin(bg_color=list_bg, border_color=border)
        self._done_list.apply_skin(bg_color=list_bg, border_color=border)

        self._apply_skin_to_rows()

    def _apply_skin_to_rows(self):
        for row in self._open_list.rows() + self._done_list.rows():
            if hasattr(row, "apply_skin"):
                row.apply_skin(self._colors)
