"""Class Designer — Standalone-Tool für Callers Caddy.

Planung von Square Dance Classes:
  - Linke Spalte:   Figurenliste (TXT-Datei, editierbar) + globaler Zoom
  - Mittlere Spalte: Planungsliste mit Aufwand, Abhängigkeiten, Wiederholungen
  - Rechte Spalte:   Automatisch erzeugter und manuell anpassbarer Class-Plan

Aufruf: python class_designer.py [app_dir] [--lang de|en]
        class_designer.exe  (im gleichen Ordner wie callers_caddy.exe)
"""

from __future__ import annotations

import json
import os
import sys

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from PySide6.QtCore import Qt, Signal, QObject, QThread, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter,
    QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QLineEdit,
    QListWidget, QListWidgetItem,
    QTreeWidget, QTreeWidgetItem,
    QAbstractItemView,
    QDialog, QDialogButtonBox, QInputDialog,
    QMessageBox, QFileDialog,
    QFrame, QProgressBar,
)

from i18n import _t, set_language
from zoom_wheel import install_ctrl_wheel_zoom

# ── Konstanten ────────────────────────────────────────────────────────────────

_VERSION = "0.1"
_APP_NAME = "Class Designer"
_FIBONACCI = [1, 2, 3, 5, 8, 13]
_DEFAULT_EFFORT = 3
_DEFAULT_REPEAT_EFFORT = 1
_COL2_TYPE = "class_plan_config"
_COL3_TYPE = "class_plan_result"
_DEFAULT_TXT_FILENAME = "teaching_order.txt"

_ZOOM_DEFAULT = 100
_ZOOM_MIN = 70
_ZOOM_MAX = 200
_ZOOM_STEP = 10
_FONT_BASE_PX = 12

_ROLE = Qt.UserRole


# ── Skin-Farben ───────────────────────────────────────────────────────────────

def _load_colors(app_dir: str) -> dict:
    fallback = {
        "widget_bg": "#2b2b2b", "title_bg": "#424242",
        "text": "#f0f0f0", "text_dim": "#999999",
        "border": "#555555", "button_bg": "#615f8b",
        "button_hover": "#7a78a5", "button_text": "#f7f7f7",
        "input_bg": "#404040", "input_text": "#f0f0f0",
        "indicator_check": "#22c55e", "warning": "#ef4444",
        "list_bg": "#363636", "selected_bg": "#4a4870",
    }
    try:
        skin_path = os.path.join(app_dir, "skins", "default", "skin.json")
        with open(skin_path, encoding="utf-8") as f:
            data = json.load(f)
        fallback.update(data.get("colors", {}))
    except Exception:
        pass
    return fallback


def _build_qss(c: dict) -> str:
    return f"""
QMainWindow, QDialog, QWidget {{
    background-color: {c['widget_bg']};
    color: {c['text']};
    font-size: 12px;
}}
QSplitter::handle {{ background-color: {c['border']}; width: 2px; height: 2px; }}
QPushButton {{
    background: {c['button_bg']}; color: {c['button_text']};
    border: none; border-radius: 3px; padding: 3px 10px;
    min-height: 24px;
}}
QPushButton:hover {{ background: {c['button_hover']}; }}
QPushButton:disabled {{ background: {c['title_bg']}; color: {c['text_dim']}; }}
QPushButton#icon_btn {{
    font-size: 16px;
    padding: 0px;
    font-weight: bold;
}}
QPushButton#filter_btn {{
    font-size: 11px;
    padding: 1px 8px;
    min-height: 22px;
    background: transparent;
    color: {c['text_dim']};
    border: 1px solid {c['text_dim']};
    border-radius: 3px;
}}
QPushButton#filter_btn:checked {{
    background: {c['button_bg']};
    color: {c['button_text']};
    border: 1px solid {c['button_bg']};
}}
QComboBox, QSpinBox, QLineEdit {{
    background: {c['input_bg']}; color: {c['input_text']};
    border: 1px solid {c['border']}; border-radius: 3px;
    padding: 2px 4px; min-height: 22px;
}}
QComboBox::drop-down {{ border: none; }}
QListWidget, QTreeWidget {{
    background: {c['list_bg']}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 3px;
    outline: none;
}}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background: {c['selected_bg']}; color: {c['text']};
}}
QListWidget::item:hover, QTreeWidget::item:hover {{
    background: {c['title_bg']};
}}
QTreeWidget::branch {{ background: {c['list_bg']}; }}
QLabel {{ color: {c['text']}; }}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {c['border']};
}}
QScrollBar:vertical {{
    background: {c['widget_bg']}; width: 10px;
}}
QScrollBar::handle:vertical {{
    background: {c['border']}; border-radius: 4px; min-height: 20px;
}}
QDialogButtonBox QPushButton {{ min-width: 80px; }}
"""


# ── Datenmodell ───────────────────────────────────────────────────────────────

def make_figure_item(name: str, effort: int = _DEFAULT_EFFORT,
                     repeat_count: int = 0,
                     repeat_effort: int = _DEFAULT_REPEAT_EFFORT,
                     prerequisites: list | None = None) -> dict:
    return {
        "type": "figure",
        "name": name,
        "effort": effort,
        "repeat_count": repeat_count,
        "repeat_effort": repeat_effort,
        "prerequisites": prerequisites or [],
    }


def make_info_item(name: str, effort: int = 0,
                   prerequisites: list | None = None) -> dict:
    return {"type": "info", "name": name, "effort": effort,
            "repeat_count": 0, "repeat_effort": 0,
            "prerequisites": prerequisites or []}


def _normalize_item(data: dict) -> dict:
    """Ergänzt fehlende Felder in geladenen JSON-Einträgen (Abwärtskompatibilität)."""
    typ = data.get("type", "figure")
    if typ == "figure":
        return {
            "type": "figure",
            "name": data.get("name", ""),
            "effort": data.get("effort", _DEFAULT_EFFORT),
            "repeat_count": data.get("repeat_count", 0),
            "repeat_effort": data.get("repeat_effort", _DEFAULT_REPEAT_EFFORT),
            "prerequisites": data.get("prerequisites", []),
        }
    else:  # info
        return {
            "type": "info",
            "name": data.get("name", ""),
            "effort": data.get("effort", 0),
            "repeat_count": 0,
            "repeat_effort": 0,
            "prerequisites": data.get("prerequisites", []),
        }


# ── Planungs-Algorithmus ──────────────────────────────────────────────────────

class ClassScheduler:
    def __init__(self, items: list[dict], n_evenings: int):
        self._items = items
        self._n = max(1, n_evenings)

    def generate(self) -> tuple[list[list[dict]], list[int]]:
        n = self._n
        evenings: list[list[dict]] = [[] for _ in range(n)]
        loads: list[int] = [0] * n
        scheduled_at: dict[str, int] = {}

        figures = [it for it in self._items if it.get("type") == "figure"]

        # ── Phase 1: Teaches und Infos strikt in Planungslisten-Reihenfolge ──
        #
        # Jedes Element wird in der Reihenfolge der Planungsliste eingetragen.
        # current_day rückt vor, sobald die Slot-Anzahl (Anzahl Items pro Tag,
        # unabhängig vom Aufwand) die Zielgröße items_per_day erreicht.
        # Dadurch landen auch Infos (effort=0) gleichmäßig über alle Abende.
        #
        # Prereq-Delays setzen eine harte Untergrenze (earliest).
        #
        # Figuren mit k Wiederholungen dürfen höchstens auf Tag n-1-k gesetzt
        # werden, damit alle Wiederholungen noch Platz finden.

        teach_effort = sum(
            it.get("effort", _DEFAULT_EFFORT if it.get("type") == "figure" else 0)
            for it in self._items
            if it.get("type") in ("figure", "info")
        )

        # Slot-basierter Tagesvorschub: Anzahl Items (nicht Aufwand)
        n_items = sum(1 for it in self._items
                      if it.get("type") in ("figure", "info"))
        items_per_day = max(1.0, n_items / n)
        slot_count = [0] * n
        current_day = 0

        # ── Kritischer Pfad: Latest-Start für jedes Element berechnen ────────
        #
        # Jedes Element erhält einen spätestmöglichen Teach-Tag (latest_start).
        # Direkte Deadline: Figur mit k Repeats → latest = n-1-k.
        # Kettenregel (Bellman-Ford rückwärts): Wenn Successor B mit Delay d
        # nach Predecessor A folgt und latest_start[B] = L, dann gilt:
        #   latest_start[A] ≤ L - d - 1
        # Mehrere Successorketten konkurrieren → Minimum gewinnt.
        # Dadurch werden Figuren wie "Fold" automatisch früh genug platziert,
        # damit die gesamte Kette Fold→CrossFold→Recycle→[Repeats] reinpasst.

        # Nachfolger-Graph aufbauen: predecessor_name → [(successor_name, delay)]
        _succ_graph: dict[str, list[tuple[str, int]]] = {
            it.get("name", ""): [] for it in self._items
        }
        for _it in self._items:
            for _p in _it.get("prerequisites", []):
                _pn = _p.get("name", "")
                _d  = max(0, int(_p.get("delay", 0)))
                if _pn in _succ_graph:
                    _succ_graph[_pn].append((_it.get("name", ""), _d))

        # Startwert: direkte Repeat-Deadline für jedes Element
        latest_start: dict[str, int] = {}
        for _it in self._items:
            _nm = _it.get("name", "")
            _rc = _it.get("repeat_count", 0) if _it.get("type") == "figure" else 0
            latest_start[_nm] = n - 1 - _rc

        # Bellman-Ford: Deadlines rückwärts durch Predecessor-Ketten propagieren
        for _ in range(len(self._items)):
            _changed = False
            for _it in self._items:
                _nm = _it.get("name", "")
                for (_succ_nm, _d) in _succ_graph.get(_nm, []):
                    _deadline = latest_start.get(_succ_nm, n - 1) - _d - 1
                    if _deadline < latest_start.get(_nm, n - 1):
                        latest_start[_nm] = _deadline
                        _changed = True
            if not _changed:
                break  # konvergiert

        for it in self._items:
            typ     = it.get("type")
            if typ not in ("figure", "info"):
                continue
            name    = it.get("name", "")
            effort  = it.get("effort",
                             _DEFAULT_EFFORT if typ == "figure" else 0)
            prereqs = it.get("prerequisites", [])

            # Frühestmöglicher Tag durch Prereq-Delays (Vorwärts-Constraint)
            earliest = 0
            for p in prereqs:
                pname = p.get("name", "")
                delay = max(0, int(p.get("delay", 0)))
                if pname in scheduled_at:
                    earliest = max(earliest, scheduled_at[pname] + delay + 1)

            place_at = max(current_day, earliest)
            # Vorwärts springen, wenn der aktuelle Tag bereits voll ist
            while place_at < n - 1 and slot_count[place_at] >= items_per_day:
                place_at += 1

            # Kritischer-Pfad-Deadline anwenden (Rückwärts-Constraint).
            # Darf earliest nicht unterschreiten — unmögliche Constraints
            # (Kette zu lang für verfügbare Tage) werden ignoriert.
            ls = max(earliest, latest_start.get(name, n - 1))
            ls = min(ls, n - 1)  # niemals außerhalb des Zeitrahmens
            if place_at > ls:
                # Rückwärts ab ls nach einem noch nicht überfüllten Tag suchen
                for earlier_day in range(ls, earliest - 1, -1):
                    if slot_count[earlier_day] < items_per_day * 1.5:
                        place_at = earlier_day
                        break
                else:
                    place_at = ls  # erzwingen, auch wenn Slot überfüllt

            place_at = min(place_at, n - 1)
            kind = "teach" if typ == "figure" else "info"
            evenings[place_at].append({"kind": kind, "name": name,
                                       "effort": effort})
            loads[place_at] += effort
            slot_count[place_at] += 1
            scheduled_at[name] = place_at

            # current_day vorspulen, sobald aktueller Tag Slot-Ziel erreicht
            while current_day < n - 1 and slot_count[current_day] >= items_per_day:
                current_day += 1

        # ── Phase 2: Wiederholungen einstreuen ────────────────────────────────
        #
        # Jede Wdhlg. muss mindestens 1 Tag nach dem Teach und 1 Tag nach
        # der vorherigen Wdhlg. derselben Figur liegen.
        # Platzierungsziel: erster unterlasteter Tag ab frühest-erlaubt;
        # bei Gleichstand der Tag mit minimaler Last.
        # Kann eine Wdhlg. nicht mehr legal platziert werden (Teach zu spät
        # und kein Folgetag vorhanden), wird sie verworfen — unvermeidbar.

        repeat_effort = sum(
            it.get("repeat_count", 0) *
            it.get("repeat_effort", _DEFAULT_REPEAT_EFFORT)
            for it in figures
        )
        target2 = max(1.0, (teach_effort + repeat_effort) / n)
        last_repeat_at: dict[str, int] = {}

        for it in figures:
            name      = it.get("name", "")
            rc        = it.get("repeat_count", 0)
            re_effort = it.get("repeat_effort", _DEFAULT_REPEAT_EFFORT)
            teach_day = scheduled_at.get(name)
            if teach_day is None or rc == 0:
                continue
            for _ in range(rc):
                earliest_r = max(teach_day + 1,
                                 last_repeat_at.get(name, -1) + 1)
                if earliest_r > n - 1:
                    continue  # kein legaler Tag verfügbar
                # Erster Tag ab earliest_r unter Zielauslastung
                best_day = n - 1
                for d in range(earliest_r, n):
                    if loads[d] < target2:
                        best_day = d
                        break
                else:
                    best_day = min(range(earliest_r, n),
                                   key=lambda d: loads[d])
                evenings[best_day].append({"kind": "repeat", "name": name,
                                           "effort": re_effort})
                loads[best_day] += re_effort
                last_repeat_at[name] = best_day

        return evenings, loads


# ── Drag&Drop-Tree für Spalte 2 ───────────────────────────────────────────────

class _PlanTree(QTreeWidget):
    """QTreeWidget für Spalte 2 — Drag&Drop nur für Top-Level-Items.

    Vollständig manuelles Drop-Handling: Qt's super().dropEvent() wird NICHT aufgerufen.
    Stattdessen wird das Item mit takeTopLevelItem() extrahiert und an der
    korrekten Position mit insertTopLevelItem() neu eingefügt.
    Dadurch können Items NIEMALS verschwinden oder als Kind-Element enden.
    """

    def __init__(self, make_item_fn, parent=None):
        super().__init__(parent)
        self._make_item_fn = make_item_fn
        self._saved_data: dict | None = None

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropOverwriteMode(False)

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if item is None or item.parent() is not None:
            return  # Kind-Items nicht draggbar
        self._saved_data = item.data(0, _ROLE)
        super().startDrag(supported_actions)

    def dragMoveEvent(self, event):
        # Qt.ItemIsDropEnabled wurde entfernt → OnItem-Indikator erscheint nie mehr.
        # super() reicht für den "Zwischen-Einfügen"-Indikator.
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        dragged = self.currentItem()
        if dragged is None or dragged.parent() is not None:
            event.ignore()
            return

        pos    = self.dropIndicatorPosition()
        target = self.itemAt(event.position().toPoint())
        # Ziel darf kein Kind-Item sein (Prereq-Zeilen)
        if target is not None and target.parent() is not None:
            event.ignore()
            self._saved_data = None
            return

        # OnItem → als BelowItem behandeln (einfügen nach dem Ziel, nie überschreiben)
        if pos == QAbstractItemView.DropIndicatorPosition.OnItem:
            pos = QAbstractItemView.DropIndicatorPosition.BelowItem

        data    = self._saved_data
        src_idx = self.indexOfTopLevelItem(dragged)
        n       = self.topLevelItemCount()

        if src_idx < 0:
            event.ignore()
            self._saved_data = None
            return

        # Ziel-Index berechnen
        if target is None:
            dst_idx = n - 1
        else:
            tgt_idx = self.indexOfTopLevelItem(target)
            if tgt_idx < 0:
                event.ignore()
                self._saved_data = None
                return
            if pos == QAbstractItemView.DropIndicatorPosition.AboveItem:
                dst_idx = tgt_idx
            else:
                dst_idx = tgt_idx + 1

        # Index nach Entfernen des Source-Items anpassen
        if src_idx < dst_idx:
            dst_idx -= 1
        dst_idx = max(0, min(dst_idx, n - 1))

        if src_idx == dst_idx:
            # Nichts zu tun — aber trotzdem als IgnoreAction markieren,
            # damit Qt kein clearOrRemove() aufruft!
            event.setDropAction(Qt.IgnoreAction)
            event.accept()
            self._saved_data = None
            return

        # MANUELLES Verschieben — Qt's InternalMove wird nie aufgerufen
        taken = self.takeTopLevelItem(src_idx)
        if data is not None:
            taken.setData(0, _ROLE, data)
        self.insertTopLevelItem(dst_idx, taken)
        self.setCurrentItem(taken)

        # KRITISCH: DropAction auf IgnoreAction setzen!
        # Qt's QAbstractItemView::startDrag() ruft nach drag->exec() ein
        # clearOrRemove() auf, wenn exec() Qt.MoveAction zurückgibt. Das würde
        # model->removeRows() auf der Selection auslösen und unser gerade
        # verschobenes Item erneut löschen (oder ein anderes Item am alten
        # src_idx). Mit IgnoreAction denkt Qt: "Drop fehlgeschlagen, nichts
        # aufzuräumen" — die manuelle Verschiebung bleibt bestehen.
        event.setDropAction(Qt.IgnoreAction)
        event.accept()
        self._saved_data = None


# ── Drag&Drop-Tree für Spalte 3 ───────────────────────────────────────────────

class _Col3Tree(QTreeWidget):
    """QTreeWidget für Spalte 3 — Child-Items (Einträge) per DnD verschiebbar.

    Tag-Header (Top-Level) können NICHT gedraggt werden.
    Einträge können innerhalb und zwischen Tagen verschoben werden.

    Vollständig manuelles Drop-Handling mit takeChild()/insertChild():
    Qt's super().dropEvent() wird NICHT aufgerufen — Items können NIEMALS verschwinden.
    """

    items_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._saved_entry: dict | None = None

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropOverwriteMode(False)

    def _is_entry(self, item) -> bool:
        return item is not None and item.parent() is not None

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if not self._is_entry(item):
            return  # Tag-Header nicht draggbar
        self._saved_entry = item.data(0, _ROLE)
        super().startDrag(supported_actions)

    def dragMoveEvent(self, event):
        super().dragMoveEvent(event)
        # Items mit ~ItemIsDropEnabled: Qt wandelt OnItem intern zu AboveItem um
        # → Linien-Indikator statt Box.  Super() ignoriert den Drop manchmal dennoch
        # (canDropMimeData-Check), daher hier explizit accept(), damit kein
        # Verbots-Cursor erscheint.
        if not event.isAccepted():
            event.accept()

    def dropEvent(self, event):
        dragged = self.currentItem()
        if not self._is_entry(dragged):
            event.ignore()
            return

        saved = self._saved_entry
        if saved is None:
            event.ignore()
            return

        pos    = self.dropIndicatorPosition()
        target = self.itemAt(event.position().toPoint())

        # OnItem auf einem Eintrag → als BelowItem behandeln (einfügen nach dem Ziel)
        if (pos == QAbstractItemView.DropIndicatorPosition.OnItem
                and self._is_entry(target)):
            pos = QAbstractItemView.DropIndicatorPosition.BelowItem

        # Quelle merken
        fg         = dragged.foreground(0)
        tip        = dragged.toolTip(0)
        src_parent = dragged.parent()
        src_idx    = src_parent.indexOfChild(dragged)

        if src_idx < 0:
            event.ignore()
            self._saved_entry = None
            return

        # Ziel-Parent und Index bestimmen
        if target is None:
            # Leerer Bereich → letzter Tag, ans Ende
            dst_parent = self.topLevelItem(self.topLevelItemCount() - 1)
            if dst_parent is None:
                event.ignore()
                self._saved_entry = None
                return
            dst_idx = dst_parent.childCount()
        elif not self._is_entry(target):
            # Drop neben Tag-Header (OnItem nicht mehr möglich):
            #   BelowItem → Anfang dieses Tages (Index 0)
            #   AboveItem → Ende des vorherigen Tages
            day_idx = self.indexOfTopLevelItem(target)
            if pos == QAbstractItemView.DropIndicatorPosition.BelowItem:
                dst_parent = target
                dst_idx    = 0
            else:
                if day_idx > 0:
                    dst_parent = self.topLevelItem(day_idx - 1)
                    dst_idx    = dst_parent.childCount()
                else:
                    dst_parent = target
                    dst_idx    = 0
        else:
            # Drop above/below einem Entry
            dst_parent = target.parent()
            tgt_idx    = dst_parent.indexOfChild(target)
            if pos == QAbstractItemView.DropIndicatorPosition.AboveItem:
                dst_idx = tgt_idx
            else:
                dst_idx = tgt_idx + 1

        # Index nach Entfernen anpassen (nur bei gleichem Parent)
        if dst_parent is src_parent and src_idx < dst_idx:
            dst_idx -= 1

        if dst_parent is src_parent and src_idx == dst_idx:
            # Nichts zu tun — aber trotzdem IgnoreAction, damit Qt kein
            # clearOrRemove() triggert.
            event.setDropAction(Qt.IgnoreAction)
            event.accept()
            self._saved_entry = None
            return

        # MANUELLES Verschieben — Qt's InternalMove wird nie aufgerufen
        taken = src_parent.takeChild(src_idx)
        taken.setData(0, _ROLE, saved)
        taken.setForeground(0, fg)
        taken.setToolTip(0, tip)
        dst_parent.insertChild(dst_idx, taken)
        self.setCurrentItem(taken)

        # KRITISCH: IgnoreAction verhindert Qt's source-side clearOrRemove().
        # Siehe _PlanTree.dropEvent() für ausführliche Erklärung.
        event.setDropAction(Qt.IgnoreAction)
        event.accept()
        self._saved_entry = None
        self.items_changed.emit()


# ── Edit-Dialoge ──────────────────────────────────────────────────────────────

class _ValueButtonRow(QWidget):
    """Button-Reihe für diskrete Werte (z.B. Fibonacci-Effort).
    Genau ein Button bleibt aktiv — Klick auf den aktiven Button ignoriert die
    Deselektion, sofern nicht allow_none=True gesetzt ist."""

    def __init__(self, values: list[int], current: int,
                 allow_none: bool = False, parent=None):
        super().__init__(parent)
        self._values = list(values)
        self._allow_none = allow_none
        self._btns: list[QPushButton] = []

        row = QHBoxLayout(self)
        row.setSpacing(4)
        row.setContentsMargins(0, 0, 0, 0)

        for v in self._values:
            btn = QPushButton(str(v))
            btn.setCheckable(True)
            btn.setChecked(v == current)
            btn.setFixedSize(36, 26)
            btn.setObjectName("filter_btn")
            btn.clicked.connect(lambda checked, b=btn: self._on_click(b, checked))
            row.addWidget(btn)
            self._btns.append(btn)
        row.addStretch()

        # Fallback: falls current nicht in values → ersten Button aktivieren
        if not allow_none and not any(b.isChecked() for b in self._btns) and self._btns:
            self._btns[0].setChecked(True)

    def _on_click(self, clicked_btn: QPushButton, checked: bool):
        if checked:
            for b in self._btns:
                if b is not clicked_btn:
                    b.setChecked(False)
        elif not self._allow_none:
            # Klick auf aktiven Button: Deselektion verhindern
            clicked_btn.setChecked(True)

    def value(self) -> int:
        for btn, v in zip(self._btns, self._values):
            if btn.isChecked():
                return v
        return 0


class FigureEditDialog(QDialog):

    def __init__(self, data: dict, all_names: list[str], parent=None):
        super().__init__(parent)
        self._data = dict(data)
        self._all_names = all_names
        self._is_info = data.get("type") == "info"
        title_key = "cd.dialog_info_title" if self._is_info else "cd.dialog_figure_title"
        self.setWindowTitle(_t(title_key))
        self.setMinimumWidth(440)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        form = QFormLayout()
        form.setSpacing(6)

        self._name_edit = QLineEdit(self._data.get("name", ""))
        self._name_edit.setStyleSheet("font-weight: bold;")
        form.addRow(_t("cd.col2_header_name") + ":", self._name_edit)

        effort_vals = ([0] + _FIBONACCI) if self._is_info else _FIBONACCI
        effort_default = self._data.get("effort", 0 if self._is_info else _DEFAULT_EFFORT)
        self._effort_box = _ValueButtonRow(effort_vals, effort_default)
        form.addRow(_t("cd.effort_label") + ":", self._effort_box)

        # Wiederholungs-Zeilen nur für Calls (nicht für Info-Elemente)
        self._repeat_btns: list[QPushButton] = []
        self._rep_effort_box = None
        if not self._is_info:
            # Wiederholungs-Anzahl: 4 Toggle-Buttons (0–4), gegenseitig exklusiv,
            # erneutes Klicken des aktiven Buttons deselektiert → 0 Wiederholungen.
            repeat_row = QHBoxLayout()
            repeat_row.setSpacing(4)
            repeat_row.setContentsMargins(0, 0, 0, 0)
            current_count = self._data.get("repeat_count", 0)
            for n in [0, 1, 2, 3, 4]:
                btn = QPushButton(str(n))
                btn.setCheckable(True)
                btn.setChecked(n == current_count)
                btn.setFixedSize(36, 26)
                btn.setObjectName("filter_btn")
                btn.clicked.connect(lambda checked, v=n: self._on_repeat_btn(v, checked))
                repeat_row.addWidget(btn)
                self._repeat_btns.append(btn)
            repeat_row.addStretch()
            form.addRow(_t("cd.repeats_label") + ":", repeat_row)

            self._rep_effort_box = _ValueButtonRow(
                _FIBONACCI, self._data.get("repeat_effort", _DEFAULT_REPEAT_EFFORT))
            form.addRow(_t("cd.repeat_effort_label") + ":", self._rep_effort_box)

        layout.addLayout(form)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        # Voraussetzungen Header
        prereq_header = QHBoxLayout()
        prereq_header.addWidget(QLabel(_t("cd.prereqs_label") + ":"))
        prereq_header.addStretch()
        btn_add_pre = QPushButton(_t("cd.btn_add_prereq"))
        btn_add_pre.setFixedHeight(24)
        btn_add_pre.clicked.connect(self._add_prereq)
        prereq_header.addWidget(btn_add_pre)
        layout.addLayout(prereq_header)

        self._prereq_list = QTreeWidget()
        self._prereq_list.setHeaderLabels([
            _t("cd.col2_header_name"), _t("cd.delay_label")])
        self._prereq_list.setRootIsDecorated(False)
        self._prereq_list.setMaximumHeight(120)
        self._prereq_list.setColumnWidth(0, 240)
        self._prereq_list.itemDoubleClicked.connect(self._edit_prereq)
        layout.addWidget(self._prereq_list)

        # Voraussetzungen Toolbar (↑ ↓ Entfernen)
        pre_tb = QHBoxLayout(); pre_tb.setSpacing(4)
        btn_pre_up = QPushButton("↑")
        btn_pre_up.setFixedSize(28, 24)
        btn_pre_up.setObjectName("icon_btn")
        btn_pre_up.clicked.connect(self._move_prereq_up)
        pre_tb.addWidget(btn_pre_up)

        btn_pre_down = QPushButton("↓")
        btn_pre_down.setFixedSize(28, 24)
        btn_pre_down.setObjectName("icon_btn")
        btn_pre_down.clicked.connect(self._move_prereq_down)
        pre_tb.addWidget(btn_pre_down)

        btn_rm = QPushButton(_t("cd.btn_remove_prereq"))
        btn_rm.setFixedHeight(24)
        btn_rm.clicked.connect(self._remove_prereq)
        pre_tb.addWidget(btn_rm)
        pre_tb.addStretch()
        layout.addLayout(pre_tb)

        # Vorhandene Einträge laden
        for p in self._data.get("prerequisites", []):
            self._add_prereq_row(p.get("name", ""), p.get("delay", 1))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _edit_prereq(self, item):
        curr_name  = item.text(0)
        curr_delay = int(item.text(1))
        existing = {self._prereq_list.topLevelItem(i).text(0)
                    for i in range(self._prereq_list.topLevelItemCount())}
        own = self._data.get("name", "")
        available = [n for n in self._all_names
                     if n != own and (n not in existing or n == curr_name)]
        if not available:
            return
        dlg = _PrereqPickDialog(available, initial_name=curr_name,
                                initial_delay=curr_delay, parent=self)
        if dlg.exec() == QDialog.Accepted:
            item.setText(0, dlg.result_name)
            item.setText(1, str(dlg.result_delay))

    def _add_prereq(self):
        existing = {self._prereq_list.topLevelItem(i).text(0)
                    for i in range(self._prereq_list.topLevelItemCount())}
        own = self._data.get("name", "")
        available = [n for n in self._all_names if n != own and n not in existing]
        if not available:
            QMessageBox.information(self, _t("cd.dialog_figure_title"),
                                    _t("cd.no_more_prereqs"))
            return
        dlg = _PrereqPickDialog(available, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._add_prereq_row(dlg.result_name, dlg.result_delay)

    def _add_prereq_row(self, name: str, delay: int):
        it = QTreeWidgetItem([name, str(delay)])
        it.setData(0, _ROLE, {"name": name, "delay": delay})
        self._prereq_list.addTopLevelItem(it)

    def _remove_prereq(self):
        for it in self._prereq_list.selectedItems():
            self._prereq_list.takeTopLevelItem(
                self._prereq_list.indexOfTopLevelItem(it))

    def _move_prereq_up(self):
        sel = self._prereq_list.currentItem()
        if sel is None:
            return
        idx = self._prereq_list.indexOfTopLevelItem(sel)
        if idx <= 0:
            return
        data = sel.data(0, _ROLE)
        if data is None:
            return
        # Rückgabewert explizit nutzen — PySide6 kann das Item sonst freigeben
        taken = self._prereq_list.takeTopLevelItem(idx)
        taken.setData(0, _ROLE, data)
        self._prereq_list.insertTopLevelItem(idx - 1, taken)
        self._prereq_list.setCurrentItem(taken)

    def _move_prereq_down(self):
        sel = self._prereq_list.currentItem()
        if sel is None:
            return
        idx = self._prereq_list.indexOfTopLevelItem(sel)
        if idx < 0 or idx >= self._prereq_list.topLevelItemCount() - 1:
            return
        data = sel.data(0, _ROLE)
        if data is None:
            return
        taken = self._prereq_list.takeTopLevelItem(idx)
        taken.setData(0, _ROLE, data)
        self._prereq_list.insertTopLevelItem(idx + 1, taken)
        self._prereq_list.setCurrentItem(taken)

    def _on_repeat_btn(self, value: int, checked: bool):
        """Exklusives Toggle: nur ein Button darf aktiv sein; erneutes Klicken = 0."""
        if checked:
            for btn in self._repeat_btns:
                if btn.text() != str(value):
                    btn.setChecked(False)

    def _repeat_count(self) -> int:
        for btn in self._repeat_btns:
            if btn.isChecked():
                return int(btn.text())
        return 0

    def result_data(self) -> dict:
        prereqs = []
        for i in range(self._prereq_list.topLevelItemCount()):
            it = self._prereq_list.topLevelItem(i)
            prereqs.append({"name": it.text(0), "delay": int(it.text(1))})
        result = {
            **self._data,
            "name": self._name_edit.text().strip() or self._data.get("name", ""),
            "effort": self._effort_box.value(),
            "prerequisites": prereqs,
        }
        if not self._is_info:
            result["repeat_count"] = self._repeat_count()
            result["repeat_effort"] = self._rep_effort_box.value()
        return result


class _PrereqPickDialog(QDialog):

    def __init__(self, names: list[str], initial_name: str = "",
                 initial_delay: int = 1, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("cd.btn_add_prereq"))
        self.setFixedSize(320, 175)
        self.result_name  = initial_name or (names[0] if names else "")
        self.result_delay = initial_delay
        layout = QFormLayout(self)
        layout.setSpacing(8)

        self._combo = QComboBox()
        for n in names:
            self._combo.addItem(n)
        if initial_name and initial_name in names:
            self._combo.setCurrentText(initial_name)
        layout.addRow(_t("cd.col2_header_name") + ":", self._combo)

        self._delay_btns: list[QPushButton] = []
        delay_row = QHBoxLayout()
        delay_row.setSpacing(4)
        delay_row.setContentsMargins(0, 0, 0, 0)
        for v in [0, 1, 2, 3]:
            btn = QPushButton(str(v))
            btn.setCheckable(True)
            btn.setChecked(v == initial_delay)
            btn.setFixedSize(36, 26)
            btn.setObjectName("filter_btn")
            btn.clicked.connect(lambda checked, val=v: self._on_delay_btn(val, checked))
            delay_row.addWidget(btn)
            self._delay_btns.append(btn)
        delay_row.addStretch()
        layout.addRow(_t("cd.delay_label") + ":", delay_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_delay_btn(self, value: int, checked: bool):
        if checked:
            for btn in self._delay_btns:
                if btn.text() != str(value):
                    btn.setChecked(False)
        else:
            self._delay_btns[value].setChecked(True)  # Deselektieren verhindern

    def _delay_value(self) -> int:
        for btn in self._delay_btns:
            if btn.isChecked():
                return int(btn.text())
        return 1

    def _on_ok(self):
        self.result_name  = self._combo.currentText()
        self.result_delay = self._delay_value()
        self.accept()


# ── Spalte 1: Figurenliste ────────────────────────────────────────────────────

class Col1Widget(QWidget):
    """Linke Spalte: Editierbare Figurenliste + Abend-Anzahl + globaler Zoom."""

    zoom_changed = Signal(int)  # pct (70–200)

    def __init__(self, cd_dir: str, parent=None):
        super().__init__(parent)
        self._cd_dir      = cd_dir
        self._default_txt = os.path.join(cd_dir, _DEFAULT_TXT_FILENAME)
        self._zoom_pct    = _ZOOM_DEFAULT
        self._build_ui()
        self._auto_load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        title = QLabel(_t("cd.col1_title"))
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        # ── Zoom-Zeile ──────────────────────────────────────────────────────
        zoom_row = QHBoxLayout(); zoom_row.setSpacing(4)

        btn_zoom_out = QPushButton("−")
        btn_zoom_out.setFixedSize(28, 22)
        btn_zoom_out.setObjectName("icon_btn")
        btn_zoom_out.clicked.connect(self._on_zoom_out)
        zoom_row.addWidget(btn_zoom_out)

        self._zoom_lbl = QLabel(f"{_ZOOM_DEFAULT}%")
        self._zoom_lbl.setAlignment(Qt.AlignCenter)
        self._zoom_lbl.setFixedWidth(42)
        zoom_row.addWidget(self._zoom_lbl)

        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedSize(28, 22)
        btn_zoom_in.setObjectName("icon_btn")
        btn_zoom_in.clicked.connect(self._on_zoom_in)
        zoom_row.addWidget(btn_zoom_in)

        zoom_row.addStretch()
        layout.addLayout(zoom_row)

        # ── Abend-Anzahl ────────────────────────────────────────────────────
        form = QFormLayout(); form.setSpacing(4)
        self._evenings_spin = QSpinBox()
        self._evenings_spin.setRange(1, 60)
        self._evenings_spin.setValue(20)
        form.addRow(_t("cd.evenings_label") + ":", self._evenings_spin)
        layout.addLayout(form)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        # ── Figurenliste Toolbar (links: Listenmanipulation | rechts: IO) ────
        tb = QHBoxLayout(); tb.setSpacing(4)

        btn_add = QPushButton("+")
        btn_add.setFixedSize(30, 26)
        btn_add.setObjectName("icon_btn")
        btn_add.setToolTip(_t("cd.btn_add_figure"))
        btn_add.clicked.connect(self._on_add)
        tb.addWidget(btn_add)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(30, 26)
        btn_del.setObjectName("icon_btn")
        btn_del.setToolTip(_t("cd.btn_delete"))
        btn_del.clicked.connect(self._on_delete)
        tb.addWidget(btn_del)

        btn_up = QPushButton("↑")
        btn_up.setFixedSize(30, 26)
        btn_up.setObjectName("icon_btn")
        btn_up.clicked.connect(self._on_move_up)
        tb.addWidget(btn_up)

        btn_down = QPushButton("↓")
        btn_down.setFixedSize(30, 26)
        btn_down.setObjectName("icon_btn")
        btn_down.clicked.connect(self._on_move_down)
        tb.addWidget(btn_down)

        tb.addStretch()

        # Load / Save rechts in derselben Zeile
        for label, slot in [(_t("cd.btn_load"), self._on_load),
                             (_t("cd.btn_save"), self._on_save)]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.clicked.connect(slot)
            tb.addWidget(btn)

        layout.addLayout(tb)

        # ── Figurenliste (mit DnD) ──────────────────────────────────────────
        self._list = QListWidget()
        self._list.setDragEnabled(True)
        self._list.setAcceptDrops(True)
        self._list.setDragDropMode(QAbstractItemView.InternalMove)
        self._list.setDefaultDropAction(Qt.MoveAction)
        self._list.setDropIndicatorShown(True)
        self._list.setDragDropOverwriteMode(False)
        self._list.itemDoubleClicked.connect(self._on_rename)
        layout.addWidget(self._list, stretch=1)

        # BL-166: STRG + Mausrad zoomt wie die +/- Buttons
        install_ctrl_wheel_zoom(self._list, self._on_zoom_in, self._on_zoom_out)

    # ── Zoom ───────────────────────────────────────────────────────────────

    def _on_zoom_out(self):
        if self._zoom_pct > _ZOOM_MIN:
            self._zoom_pct = max(_ZOOM_MIN, self._zoom_pct - _ZOOM_STEP)
            self._zoom_lbl.setText(f"{self._zoom_pct}%")
            self.zoom_changed.emit(self._zoom_pct)

    def _on_zoom_in(self):
        if self._zoom_pct < _ZOOM_MAX:
            self._zoom_pct = min(_ZOOM_MAX, self._zoom_pct + _ZOOM_STEP)
            self._zoom_lbl.setText(f"{self._zoom_pct}%")
            self.zoom_changed.emit(self._zoom_pct)

    # ── TXT-Datei ──────────────────────────────────────────────────────────

    def _auto_load(self):
        if os.path.isfile(self._default_txt):
            self._load_from_file(self._default_txt)

    def _load_from_file(self, path: str):
        self._list.clear()
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    name = line.strip()
                    if name and not name.startswith("#"):
                        self._list.addItem(QListWidgetItem(name))
        except Exception as e:
            QMessageBox.critical(self, _t("cd.col1_title"), str(e))

    def _save_to_file(self, path: str):
        try:
            names = [self._list.item(i).text() for i in range(self._list.count())]
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(names) + "\n")
        except Exception as e:
            QMessageBox.critical(self, _t("cd.col1_title"), str(e))

    # ── Actions ────────────────────────────────────────────────────────────

    def _on_add(self):
        name, ok = QInputDialog.getText(
            self, _t("cd.btn_add_figure"), _t("cd.col1_add_name_prompt"))
        if ok and name.strip():
            row = self._list.currentRow()
            if row < 0:
                self._list.addItem(QListWidgetItem(name.strip()))
            else:
                self._list.insertItem(row + 1, QListWidgetItem(name.strip()))
                self._list.setCurrentRow(row + 1)

    def _on_rename(self, item: QListWidgetItem):
        name, ok = QInputDialog.getText(
            self, _t("cd.btn_edit"), _t("cd.col1_add_name_prompt"),
            text=item.text())
        if ok and name.strip():
            item.setText(name.strip())

    def _on_delete(self):
        row = self._list.currentRow()
        if row >= 0:
            self._list.takeItem(row)

    def _on_move_up(self):
        row = self._list.currentRow()
        if row <= 0:
            return
        item = self._list.takeItem(row)
        self._list.insertItem(row - 1, item)
        self._list.setCurrentRow(row - 1)

    def _on_move_down(self):
        row = self._list.currentRow()
        if row < 0 or row >= self._list.count() - 1:
            return
        item = self._list.takeItem(row)
        self._list.insertItem(row + 1, item)
        self._list.setCurrentRow(row + 1)

    def _on_load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, _t("cd.col1_load_txt"), self._cd_dir, "Text (*.txt);;Alle (*.*)")
        if path:
            self._load_from_file(path)

    def _on_save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, _t("cd.col1_save_txt"), self._default_txt, "Text (*.txt)")
        if path:
            self._save_to_file(path)

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def n_evenings(self) -> int:
        return self._evenings_spin.value()

    def teaching_order_items(self) -> list[dict]:
        return [make_figure_item(self._list.item(i).text())
                for i in range(self._list.count())]


# ── Spalte 2: Planungsliste ───────────────────────────────────────────────────

class Col2Widget(QWidget):

    _FILTER_VALUES = [0, 1, 2, 3, 5, 8, 13]

    def __init__(self, cd_dir: str = "", parent=None):
        super().__init__(parent)
        self._cd_dir = cd_dir
        self._effort_filter: set[int] = set(self._FILTER_VALUES)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        title = QLabel(_t("cd.col2_title"))
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        # Toolbar (links: Listenmanipulation | rechts: IO)
        tb = QHBoxLayout(); tb.setSpacing(4)

        btn_add_call = QPushButton(_t("cd.btn_add_call"))
        btn_add_call.setFixedHeight(26)
        btn_add_call.clicked.connect(self._on_add_call)
        tb.addWidget(btn_add_call)

        self._btn_add_info = QPushButton(_t("cd.btn_add_info"))
        self._btn_add_info.setFixedHeight(26)
        self._btn_add_info.clicked.connect(self._on_add_info)
        tb.addWidget(self._btn_add_info)

        self._btn_edit = QPushButton(_t("cd.btn_edit"))
        self._btn_edit.setFixedHeight(26)
        self._btn_edit.clicked.connect(self._on_edit)
        tb.addWidget(self._btn_edit)

        for symbol, slot in [("↑", self._on_move_up), ("↓", self._on_move_down),
                              ("✕", self._on_delete)]:
            btn = QPushButton(symbol)
            btn.setFixedSize(30, 26)
            btn.setObjectName("icon_btn")
            if symbol == "✕":
                btn.setToolTip(_t("cd.btn_delete"))
            btn.clicked.connect(slot)
            tb.addWidget(btn)

        tb.addStretch()

        # Load / Save rechts in derselben Zeile
        for label, slot in [(_t("cd.btn_load"), self._on_load),
                             (_t("cd.btn_save"), self._on_save)]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.clicked.connect(slot)
            tb.addWidget(btn)

        layout.addLayout(tb)

        # ── Filter-Zeile (Effort-Werte, reiner Anzeigefilter) ────────────────
        filter_row = QHBoxLayout(); filter_row.setSpacing(4)
        filter_row.addWidget(QLabel("Filter:"))
        self._effort_filter_btns: dict[int, QPushButton] = {}
        for v in self._FILTER_VALUES:
            btn = QPushButton(str(v))
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedSize(36, 26)
            btn.setObjectName("filter_btn")
            btn.toggled.connect(
                lambda on, val=v: self._toggle_effort_filter(val, on))
            filter_row.addWidget(btn)
            self._effort_filter_btns[v] = btn
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Tree mit DnD
        self._tree = _PlanTree(self._make_tree_item)
        self._tree.setHeaderLabels([
            _t("cd.col2_header_name"),
            _t("cd.col2_header_effort"),
            _t("cd.col2_header_repeats"),
        ])
        self._tree.setColumnWidth(0, 220)
        self._tree.setColumnWidth(1, 55)
        self._tree.setColumnWidth(2, 55)
        self._tree.setRootIsDecorated(True)
        self._tree.itemDoubleClicked.connect(self._on_edit)
        self._tree.setSelectionMode(QTreeWidget.SingleSelection)
        layout.addWidget(self._tree, stretch=1)

    # ── Datenzugriff ──────────────────────────────────────────────────────

    def items(self) -> list[dict]:
        result = []
        for i in range(self._tree.topLevelItemCount()):
            data = self._tree.topLevelItem(i).data(0, _ROLE)
            if data:
                result.append(data)
        return result

    def all_figure_names(self) -> list[str]:
        return [it["name"] for it in self.items() if it.get("type") == "figure"]

    def all_item_names(self) -> list[str]:
        return [it["name"] for it in self.items()]

    def set_items(self, items: list[dict]):
        self._tree.clear()
        for data in items:
            self._tree.addTopLevelItem(self._make_tree_item(_normalize_item(data)))
        self._apply_effort_filter()

    def _toggle_effort_filter(self, value: int, on: bool):
        if on:
            self._effort_filter.add(value)
        else:
            self._effort_filter.discard(value)
        self._apply_effort_filter()

    def _apply_effort_filter(self):
        for i in range(self._tree.topLevelItemCount()):
            it = self._tree.topLevelItem(i)
            data = it.data(0, _ROLE) or {}
            effort = int(data.get("effort", 0))
            it.setHidden(effort not in self._effort_filter)

    def _make_tree_item(self, data: dict) -> QTreeWidgetItem:
        if data is None:
            data = make_info_item("???")
        typ     = data.get("type", "figure")
        name    = data.get("name", "")
        effort  = data.get("effort", _DEFAULT_EFFORT)
        repeats = data.get("repeat_count", 0)

        prefix   = "ℹ " if typ == "info" else ""
        rep_text = "" if typ == "info" else (str(repeats) if repeats > 0 else "")

        it = QTreeWidgetItem([prefix + name, str(effort), rep_text])
        it.setData(0, _ROLE, data)

        if typ == "figure":
            for prereq in data.get("prerequisites", []):
                child = QTreeWidgetItem([
                    f"  ↳ {prereq['name']}",
                    "",
                    _t("cd.delay_label") + f": {prereq['delay']}"
                ])
                child.setFlags(child.flags() & ~Qt.ItemIsSelectable)
                it.addChild(child)
            if data.get("prerequisites"):
                it.setExpanded(True)

        return it

    def _refresh_item(self, it: QTreeWidgetItem, data: dict):
        idx = self._tree.indexOfTopLevelItem(it)
        if idx < 0:
            return
        new_it = self._make_tree_item(data)
        self._tree.takeTopLevelItem(idx)
        self._tree.insertTopLevelItem(idx, new_it)
        self._tree.setCurrentItem(new_it)
        self._apply_effort_filter()

    # ── Actions ───────────────────────────────────────────────────────────

    def _selected_top(self) -> QTreeWidgetItem | None:
        sel = self._tree.currentItem()
        if sel is None:
            return None
        if self._tree.indexOfTopLevelItem(sel) >= 0:
            return sel
        return sel.parent()

    def _insert_after_selected(self, new_data: dict):
        """Fügt Element hinter dem aktuell markierten ein (oder hängt an)."""
        new_it = self._make_tree_item(new_data)
        it = self._selected_top()
        if it is None:
            self._tree.addTopLevelItem(new_it)
        else:
            idx = self._tree.indexOfTopLevelItem(it)
            self._tree.insertTopLevelItem(idx + 1, new_it)
        self._tree.setCurrentItem(new_it)
        self._apply_effort_filter()

    def _on_add_call(self):
        name, ok = QInputDialog.getText(
            self, _t("cd.btn_add_call"), _t("cd.col1_add_name_prompt"))
        if ok and name.strip():
            self._insert_after_selected(make_figure_item(name.strip()))

    def _on_add_info(self):
        dlg = FigureEditDialog(make_info_item(""), self.all_item_names(), parent=self)
        if dlg.exec() == QDialog.Accepted:
            new_data = dlg.result_data()
            if new_data["name"]:
                self._insert_after_selected(new_data)

    def _rename_prereq_refs(self, old_name: str, new_name: str):
        """Aktualisiert Voraussetzungs-Referenzen in allen anderen Elementen."""
        for i in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(i)
            d = top.data(0, _ROLE)
            if not d:
                continue
            prereqs = d.get("prerequisites", [])
            changed = False
            for p in prereqs:
                if p.get("name") == old_name:
                    p["name"] = new_name
                    changed = True
            if changed:
                top.setData(0, _ROLE, d)
                # Kindzeilen-Texte aktualisieren
                for c in range(top.childCount()):
                    child = top.child(c)
                    if old_name in child.text(0):
                        child.setText(0, child.text(0).replace(old_name, new_name))

    def _on_edit(self, *_):
        it = self._selected_top()
        if it is None:
            return
        data = it.data(0, _ROLE)
        if data is None:
            return
        dlg = FigureEditDialog(data, self.all_item_names(), parent=self)
        if dlg.exec() == QDialog.Accepted:
            new_data = dlg.result_data()
            old_name = data.get("name", "")
            new_name = new_data.get("name", "")
            if old_name and new_name and old_name != new_name:
                self._rename_prereq_refs(old_name, new_name)
            self._refresh_item(it, new_data)

    def _on_move_up(self):
        it = self._selected_top()
        if it is None:
            return
        data = it.data(0, _ROLE)
        if data is None:
            return
        idx = self._tree.indexOfTopLevelItem(it)
        if idx <= 0:
            return
        self._tree.takeTopLevelItem(idx)
        new_it = self._make_tree_item(data)
        self._tree.insertTopLevelItem(idx - 1, new_it)
        self._tree.setCurrentItem(new_it)

    def _on_move_down(self):
        it = self._selected_top()
        if it is None:
            return
        data = it.data(0, _ROLE)
        if data is None:
            return
        idx = self._tree.indexOfTopLevelItem(it)
        if idx < 0 or idx >= self._tree.topLevelItemCount() - 1:
            return
        self._tree.takeTopLevelItem(idx)
        new_it = self._make_tree_item(data)
        self._tree.insertTopLevelItem(idx + 1, new_it)
        self._tree.setCurrentItem(new_it)

    def _on_delete(self):
        it = self._selected_top()
        if it is not None:
            self._tree.takeTopLevelItem(self._tree.indexOfTopLevelItem(it))

    def _on_load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, _t("cd.load_title_config"), self._cd_dir, "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("type") != _COL2_TYPE:
                QMessageBox.warning(self, _t("cd.load_title_config"), _t("cd.wrong_file_type"))
                return
            self.set_items(data.get("items", []))
        except Exception as e:
            QMessageBox.critical(self, _t("cd.load_title_config"), str(e))

    def _on_save(self):
        default = os.path.join(self._cd_dir, "planungsstand.json")
        path, _ = QFileDialog.getSaveFileName(
            self, _t("cd.save_title_config"), default, "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"type": _COL2_TYPE, "items": self.items()},
                          f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, _t("cd.save_title_config"), str(e))


# ── Optimierungs-Worker (läuft in QThread) ────────────────────────────────────

class _OptimizeWorker(QObject):
    """Führt die bidirektionale Sweep-Optimierung im Hintergrund-Thread aus."""

    progress = Signal(int, float)   # (iteration, aktuelle Kostenfunktion)
    finished = Signal(list)         # (fertige days-Liste)

    def __init__(self, days: list, meta: dict,
                 plan_cost_fn, sweep_fn, max_iters: int):
        super().__init__()
        self._days      = days
        self._meta      = meta
        self._cost_fn   = plan_cost_fn
        self._sweep_fn  = sweep_fn
        self._max_iters = max_iters

    def run(self):
        """Wechselt zwischen Vorwärts- und Rückwärts-Sweep.
        Konvergenz: zwei aufeinanderfolgende Sweeps ohne Verbesserung."""
        cost = self._cost_fn(self._days, self._meta)
        self.progress.emit(0, cost)
        no_improve = 0
        for i in range(1, self._max_iters + 1):
            reverse  = (i % 2 == 0)   # ungerade = vorwärts, gerade = rückwärts
            improved = self._sweep_fn(self._days, self._meta, reverse)
            no_improve = 0 if improved else no_improve + 1
            cost = self._cost_fn(self._days, self._meta)
            self.progress.emit(i, cost)
            if no_improve >= 2:        # fwd + bwd ohne Verbesserung → fertig
                break
        self.finished.emit(self._days)


# ── Optimierungs-Overlay ──────────────────────────────────────────────────────

class _OptimizeOverlay(QWidget):
    """Halbtransparentes Overlay mit rotierendem Status-Text und Kostenfunktion."""

    _TEXTS = [
        "Elemente verschieben …",
        "Tagessumme prüfen …",
        "Abhängigkeiten berücksichtigen …",
        "Lastverteilung berechnen …",
        "Bessere Anordnung suchen …",
        "Reihenfolge optimieren …",
        "Einzelne Moves bewerten …",
        "Verletzungen auflösen …",
    ]

    def __init__(self, max_iters: int, parent=None):
        super().__init__(parent)
        self._text_idx  = 0
        self._max_iters = max_iters
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_text)
        self._timer.start(2500)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)

        frame = QFrame()
        frame.setFixedWidth(360)
        frame.setStyleSheet(
            "QFrame { background-color: #2b2b2b; border-radius: 10px;"
            " border: 1px solid #555; }")
        inner = QVBoxLayout(frame)
        inner.setSpacing(10)
        inner.setContentsMargins(28, 22, 28, 22)

        title = QLabel(_t("cd_optimizing"))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "color: #ffffff; font-weight: bold; font-size: 14px; border: none;")
        inner.addWidget(title)

        self._status_lbl = QLabel(self._TEXTS[0])
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setStyleSheet(
            "color: #aaaaaa; font-size: 12px; border: none;")
        inner.addWidget(self._status_lbl)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, self._max_iters)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setStyleSheet(
            "QProgressBar { background: #444; border-radius: 4px; border: none; }"
            "QProgressBar::chunk { background: #5a9fd4; border-radius: 4px; }")
        inner.addWidget(self._progress_bar)

        bottom_row = QHBoxLayout()
        self._iter_lbl = QLabel(f"0 / {self._max_iters}")
        self._iter_lbl.setStyleSheet(
            "color: #777777; font-size: 11px; border: none;")
        bottom_row.addWidget(self._iter_lbl)
        bottom_row.addStretch()
        self._cost_lbl = QLabel(f"{_t('cd_cost_points')}: …")
        self._cost_lbl.setStyleSheet(
            "color: #777777; font-size: 11px; border: none;")
        bottom_row.addWidget(self._cost_lbl)
        inner.addLayout(bottom_row)

        outer.addWidget(frame)

    def update_progress(self, iteration: int, cost: float):
        self._progress_bar.setValue(iteration)
        self._iter_lbl.setText(f"{iteration} / {self._max_iters}")
        self._cost_lbl.setText(f"{_t('cd_cost_points')}: {cost:.0f}")

    def _next_text(self):
        self._text_idx = (self._text_idx + 1) % len(self._TEXTS)
        self._status_lbl.setText(self._TEXTS[self._text_idx])

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 160))
        p.end()


# ── Spalte 3: Class-Plan ──────────────────────────────────────────────────────

class Col3Widget(QWidget):
    """Rechte Spalte: Erzeugter und manuell anpassbarer Class-Plan.

    Farben:
      - Ersteinführungen (teach): helle Textfarbe (skin text)
      - Wiederholungen   (repeat): gedimmtes Hellgrau
      - Infos            (info): helle Textfarbe
    Konflikte (Delay-Verletzungen) werden rot markiert.
    """

    def __init__(self, cd_dir: str = "", parent=None):
        super().__init__(parent)
        self._cd_dir          = cd_dir
        self._conflict_color  = "#ef4444"
        self._distance_color  = "#f97316"   # Orange: Abstandregel-Verstoß
        self._text_color      = "#f0f0f0"
        self._repeat_color    = "#a0a0a0"
        self._list_bg         = "#363636"
        self._over_color      = "#5a2020"   # Rot: Tag erheblich über Durchschnitt
        self._under_color     = "#1a2a40"   # Blau: Tag erheblich unter Durchschnitt
        self._plan_items: list[dict] = []
        self._n_evenings: int = 0
        # Filter-Zustand (Anzeige, keine Auswirkung auf Kalkulation)
        self._show_teach  = True
        self._show_repeat = True
        self._show_info   = True
        self._build_ui()

    def set_colors(self, text_color: str, repeat_color: str, conflict_color: str,
                   list_bg: str = "#363636"):
        self._text_color     = text_color
        self._repeat_color   = repeat_color
        self._conflict_color = conflict_color
        self._list_bg        = list_bg

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        title = QLabel(_t("cd.col3_title"))
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        # ── Toolbar (links: Manipulation | rechts: IO) ──────────────────────
        tb = QHBoxLayout(); tb.setSpacing(4)

        for symbol, attr, tip_key in [
            ("↑", "_btn_up",   "cd.btn_move_up"),
            ("↓", "_btn_down", "cd.btn_move_down"),
        ]:
            btn = QPushButton(symbol)
            btn.setFixedSize(30, 26)
            btn.setObjectName("icon_btn")
            btn.setToolTip(_t(tip_key))
            setattr(self, attr, btn)
            tb.addWidget(btn)

        self._btn_expand = QPushButton("⊞")
        self._btn_expand.setFixedSize(28, 26)
        self._btn_expand.setObjectName("icon_btn")
        self._btn_expand.setToolTip(_t("cd.btn_expand_all"))
        tb.addWidget(self._btn_expand)

        self._btn_collapse = QPushButton("⊟")
        self._btn_collapse.setFixedSize(28, 26)
        self._btn_collapse.setObjectName("icon_btn")
        self._btn_collapse.setToolTip(_t("cd.btn_collapse_all"))
        tb.addWidget(self._btn_collapse)

        tb.addStretch()

        # Prüfen / Optimieren
        self._btn_check = QPushButton(_t("cd.btn_check"))
        self._btn_check.setFixedHeight(26)
        tb.addWidget(self._btn_check)

        self._btn_optimize = QPushButton(_t("cd.btn_optimize"))
        self._btn_optimize.setFixedHeight(26)
        tb.addWidget(self._btn_optimize)

        tb.addSpacing(8)

        # Load / Save / Export rechts in derselben Zeile
        for label, slot in [(_t("cd.btn_load"),         self._on_load),
                             (_t("cd.btn_save"),         self._on_save),
                             (_t("cd.btn_export_notes"), self._on_export_notes)]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.clicked.connect(slot)
            tb.addWidget(btn)

        layout.addLayout(tb)

        # ── Filter-Zeile (Anzeige-Toggles, keine Auswirkung auf Kalkulation) ─
        filter_row = QHBoxLayout(); filter_row.setSpacing(4)
        filter_row.addWidget(QLabel("Filter:"))

        self._btn_filter_teach = QPushButton(_t("cd.filter_teach"))
        self._btn_filter_teach.setCheckable(True)
        self._btn_filter_teach.setChecked(True)
        self._btn_filter_teach.setObjectName("filter_btn")
        self._btn_filter_teach.toggled.connect(
            lambda on: self._set_filter("teach", on))
        filter_row.addWidget(self._btn_filter_teach)

        self._btn_filter_repeat = QPushButton(_t("cd.filter_repeat"))
        self._btn_filter_repeat.setCheckable(True)
        self._btn_filter_repeat.setChecked(True)
        self._btn_filter_repeat.setObjectName("filter_btn")
        self._btn_filter_repeat.toggled.connect(
            lambda on: self._set_filter("repeat", on))
        filter_row.addWidget(self._btn_filter_repeat)

        self._btn_filter_info = QPushButton(_t("cd.filter_info"))
        self._btn_filter_info.setCheckable(True)
        self._btn_filter_info.setChecked(True)
        self._btn_filter_info.setObjectName("filter_btn")
        self._btn_filter_info.toggled.connect(
            lambda on: self._set_filter("info", on))
        filter_row.addWidget(self._btn_filter_info)

        filter_row.addStretch()
        layout.addLayout(filter_row)

        # ── Tree ────────────────────────────────────────────────────────────
        self._tree = _Col3Tree()
        self._tree.setHeaderLabels([_t("cd.col3_title"), _t("cd.col2_header_effort")])
        self._tree.setColumnWidth(0, 230)
        self._tree.setRootIsDecorated(True)
        self._tree.items_changed.connect(self._recalc_all_stats)
        layout.addWidget(self._tree, stretch=1)

        # Buttons verbinden (Tree muss zuerst existieren)
        self._btn_up.clicked.connect(self._on_move_up)
        self._btn_down.clicked.connect(self._on_move_down)
        self._btn_expand.clicked.connect(self._tree.expandAll)
        self._btn_collapse.clicked.connect(self._tree.collapseAll)
        self._btn_check.clicked.connect(self._on_check)
        self._btn_optimize.clicked.connect(self._on_optimize)

        # Stats
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)
        self._stats_lbl = QLabel("—")
        self._stats_lbl.setStyleSheet("font-size: 11px;")
        self._stats_lbl.setWordWrap(True)
        layout.addWidget(self._stats_lbl)

    # ── Plan setzen ───────────────────────────────────────────────────────

    def set_plan(self, evenings: list[list[dict]], loads: list[int],
                 plan_items: list[dict] | None = None, n_evenings: int = 0):
        if plan_items is not None:
            self._plan_items = plan_items
        self._n_evenings = n_evenings or len(evenings)
        self._tree.clear()

        kind_prefix  = {"teach": "→ ", "repeat": "↻ ", "info": "ℹ "}
        text_brush    = QColor(self._text_color)
        repeat_brush  = QColor(self._repeat_color)

        for day_idx, (day_items, load) in enumerate(zip(evenings, loads), 1):
            day_text = _t("cd.day_label").format(n=day_idx, pts=load)
            day_item = QTreeWidgetItem([day_text, ""])
            day_item.setData(0, _ROLE, {"_type": "day", "day": day_idx})
            font = day_item.font(0)
            font.setBold(True)
            day_item.setFont(0, font)
            # Tag-Header: nicht draggbar, kein "Drop-ON"-Indikator
            day_item.setFlags(day_item.flags()
                              & ~Qt.ItemIsDragEnabled
                              & ~Qt.ItemIsDropEnabled)

            for entry in day_items:
                kind   = entry.get("kind", "teach")
                name   = entry.get("name", "")
                effort = entry.get("effort", 0)
                prefix = kind_prefix.get(kind, "")
                child  = QTreeWidgetItem([prefix + name, str(effort) if effort else ""])
                child.setData(0, _ROLE, {**entry, "_type": "entry", "_day": day_idx - 1})
                # ~ItemIsDropEnabled: Qt wandelt OnItem → AboveItem um → Linien-Indikator
                child.setFlags(child.flags() & ~Qt.ItemIsDropEnabled)
                # Farbe je Kind-Typ
                color = repeat_brush if kind == "repeat" else text_brush
                child.setForeground(0, color)
                child.setForeground(1, color)
                day_item.addChild(child)

            self._tree.addTopLevelItem(day_item)
            day_item.setExpanded(True)

        self._update_stats(loads)
        self._update_day_colors(loads)
        self._check_conflicts()
        self._apply_filters()

    # ── Konflikt-Erkennung ────────────────────────────────────────────────

    def _check_conflicts(self):
        if not self._plan_items:
            return
        prereq_map: dict[str, list[dict]] = {
            it["name"]: it["prerequisites"]
            for it in self._plan_items
            if it and it.get("type") == "figure" and it.get("prerequisites")
        }

        taught_on: dict[str, int] = {}
        for i in range(self._tree.topLevelItemCount()):
            day = self._tree.topLevelItem(i)
            for j in range(day.childCount()):
                entry = day.child(j).data(0, _ROLE) or {}
                if entry.get("kind") == "teach":
                    taught_on[entry.get("name", "")] = i

        conflicts: set[str] = set()
        for fig_name, prereqs in prereq_map.items():
            if fig_name not in taught_on:
                continue
            fig_day = taught_on[fig_name]
            for p in prereqs:
                pname = p.get("name", "")
                delay = p.get("delay", 0)
                if pname not in taught_on or fig_day <= taught_on[pname] + delay:
                    conflicts.add(fig_name)

        distance_brush = QColor(self._distance_color)
        text_brush     = QColor(self._text_color)
        repeat_brush   = QColor(self._repeat_color)

        for i in range(self._tree.topLevelItemCount()):
            day = self._tree.topLevelItem(i)
            for j in range(day.childCount()):
                child = day.child(j)
                entry = child.data(0, _ROLE) or {}
                kind  = entry.get("kind", "teach")
                name  = entry.get("name", "")
                if kind == "teach" and name in conflicts:
                    child.setForeground(0, distance_brush)
                    child.setForeground(1, distance_brush)
                    child.setToolTip(0, _t("cd.conflict_tooltip"))
                else:
                    color = repeat_brush if kind == "repeat" else text_brush
                    child.setForeground(0, color)
                    child.setForeground(1, color)
                    child.setToolTip(0, "")

    # ── Stats / Neuberechnung ─────────────────────────────────────────────

    def _update_stats(self, loads: list[int]):
        if not loads:
            self._stats_lbl.setText("—")
            return
        non_empty = [l for l in loads if l > 0] or loads
        total = sum(loads)
        self._stats_lbl.setText(
            _t("cd.stats_label").format(
                total=total, avg=total / len(loads),
                min=min(non_empty), max=max(non_empty)))

    def _recalc_day_header(self, day_item: QTreeWidgetItem):
        load = sum(
            (day_item.child(i).data(0, _ROLE) or {}).get("effort", 0)
            for i in range(day_item.childCount())
        )
        day_n = self._tree.indexOfTopLevelItem(day_item) + 1
        day_item.setText(0, _t("cd.day_label").format(n=day_n, pts=load))
        day_item.setData(0, _ROLE, {"_type": "day", "day": day_n})
        return load

    def _recalc_all_stats(self):
        loads = []
        for i in range(self._tree.topLevelItemCount()):
            day  = self._tree.topLevelItem(i)
            load = sum(
                (day.child(j).data(0, _ROLE) or {}).get("effort", 0)
                for j in range(day.childCount())
            )
            self._recalc_day_header(day)
            loads.append(load)
        self._update_stats(loads)
        self._update_day_colors(loads)
        self._check_conflicts()

    # ── Prüfen / Optimieren ───────────────────────────────────────────────
    #
    # Optimieren = iterative Local Search auf dem aktuellen Plan (nicht neu
    # erzeugen!). Klassisches Muster aus RCPSP / Sprint-Rebalancing:
    #   1) Zielfunktion = Distanz-Verstöße (hart gewichtet) + Σ(Last − Ø)²
    #   2) Pro Iteration: bester legaler Single-Move von Tag i → Tag k
    #   3) Legalität = harte Constraints (Prereq-Delay, Nachfolger-Delay,
    #      Repeat nach Teach, kein doppelter Repeat am selben Tag)
    #   4) Stopp, sobald kein Move mehr Kosten senkt (Hill-Climbing-Konvergenz)

    def _on_check(self):
        self._recalc_all_stats()

    _MAX_OPTIM_ITERS = 200

    def _on_optimize(self):
        if not self._plan_items or self._tree.topLevelItemCount() < 1:
            return
        days = self._extract_days_from_tree()
        if not days:
            return
        meta = self._build_constraint_meta()

        # Overlay anzeigen
        self._overlay = _OptimizeOverlay(self._MAX_OPTIM_ITERS, parent=self)
        self._overlay.setGeometry(self.rect())
        self._overlay.show()
        self._overlay.raise_()
        self._btn_optimize.setEnabled(False)

        # Worker in eigenem Thread starten
        self._opt_thread = QThread(self)
        self._opt_worker = _OptimizeWorker(
            days, meta,
            self._plan_cost, self._optimize_sweep,
            self._MAX_OPTIM_ITERS)
        self._opt_worker.moveToThread(self._opt_thread)
        self._opt_thread.started.connect(self._opt_worker.run)
        self._opt_worker.progress.connect(self._overlay.update_progress)
        self._opt_worker.finished.connect(self._on_optimize_done)
        self._opt_worker.finished.connect(self._opt_thread.quit)
        self._opt_thread.start()

    def _on_optimize_done(self, days: list):
        if hasattr(self, "_overlay") and self._overlay:
            self._overlay.hide()
            self._overlay.deleteLater()
            self._overlay = None
        self._btn_optimize.setEnabled(True)
        loads = [sum(e.get("effort", 0) for e in d) for d in days]
        self.set_plan(days, loads,
                      plan_items=self._plan_items,
                      n_evenings=len(days))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_overlay") and self._overlay and self._overlay.isVisible():
            self._overlay.setGeometry(self.rect())

    def _extract_days_from_tree(self) -> list[list[dict]]:
        """Liest aktuellen Plan aus dem Tree (inkl. manueller Drag-Änderungen)."""
        days: list[list[dict]] = []
        for i in range(self._tree.topLevelItemCount()):
            day = self._tree.topLevelItem(i)
            entries = []
            for j in range(day.childCount()):
                data = day.child(j).data(0, _ROLE) or {}
                entry = {k: v for k, v in data.items() if not k.startswith("_")}
                entries.append(entry)
            days.append(entries)
        return days

    def _build_constraint_meta(self) -> dict:
        """Baut Prereq-/Nachfolger-Maps aus _plan_items für Constraint-Checks.
        Infos werden gleichberechtigt behandelt: sie können Voraussetzungen
        haben und auch selbst Voraussetzung anderer Items sein."""
        prereqs_of: dict[str, list[tuple[str, int]]] = {}
        successors_of: dict[str, list[tuple[str, int]]] = {}
        info_names: set[str] = set()
        for item in self._plan_items:
            if not item:
                continue
            typ = item.get("type")
            if typ not in ("figure", "info"):
                continue
            name = item.get("name", "")
            if typ == "info":
                info_names.add(name)
            cleaned = [(p.get("name", ""), max(0, int(p.get("delay", 0))))
                       for p in item.get("prerequisites", [])
                       if p.get("name")]
            prereqs_of[name] = cleaned
            for pname, delay in cleaned:
                successors_of.setdefault(pname, []).append((name, delay))
        return {"prereqs_of": prereqs_of, "successors_of": successors_of,
                "info_names": info_names}

    @staticmethod
    def _item_days(days: list[list[dict]]) -> dict[str, int]:
        """Tagespositionen aller fixen Elemente (teach + info).
        Wiederholungen zählen hier NICHT — sie sind keine Bezugspunkte für
        Abhängigkeiten und ihr Name kann mehrfach auftauchen."""
        return {e.get("name", ""): i
                for i, d in enumerate(days)
                for e in d if e.get("kind") in ("teach", "info")}

    def _can_move(self, days: list[list[dict]], entry: dict,
                  from_i: int, to_k: int, meta: dict) -> bool:
        if from_i == to_k or to_k < 0 or to_k >= len(days):
            return False

        kind = entry.get("kind", "teach")
        name = entry.get("name", "")
        item_days = self._item_days(days)

        if kind in ("teach", "info"):
            # Voraussetzungen müssen früh genug zurückliegen
            for pname, delay in meta["prereqs_of"].get(name, []):
                if pname in item_days and to_k <= item_days[pname] + delay:
                    return False
            # Nachfolger dürfen nicht zu nah/vor uns liegen
            for sname, delay in meta["successors_of"].get(name, []):
                if sname in item_days and item_days[sname] <= to_k + delay:
                    return False
            if kind == "teach":
                # Alle Wdhlg. dieser Figur müssen nach dem neuen Teach-Tag liegen
                for i, d in enumerate(days):
                    for e in d:
                        if e is entry:
                            continue
                        if e.get("kind") == "repeat" and e.get("name") == name:
                            if i <= to_k:
                                return False
        elif kind == "repeat":
            # Repeat muss nach dem Teach der Figur liegen
            if name in item_days and to_k <= item_days[name]:
                return False
            # Keine zweite Wdhlg. derselben Figur am selben Zieltag
            for i, d in enumerate(days):
                if i == from_i:
                    continue
                for e in d:
                    if e is entry:
                        continue
                    if e.get("kind") == "repeat" and e.get("name") == name:
                        if i == to_k:
                            return False
        return True

    def _plan_cost(self, days: list[list[dict]], meta: dict) -> float:
        loads = [sum(e.get("effort", 0) for e in d) for d in days]
        n = len(loads)
        total = sum(loads)
        target = total / n if n > 0 else 0
        load_cost = sum((l - target) ** 2 for l in loads)

        # Harte Verletzungen (Prereq-Delay)
        violations = 0
        item_days = self._item_days(days)
        for name, prereqs in meta["prereqs_of"].items():
            if name not in item_days:
                continue
            d = item_days[name]
            for pname, delay in prereqs:
                if pname in item_days and d <= item_days[pname] + delay:
                    violations += 1

        # Gummiband für Infos: möglichst nah (aber legal) vor ihrem ersten
        # Einsatz. Verhindert, dass Infos alle auf Tag 1 landen, wo sie bis
        # zum Call schon wieder vergessen sind.
        # Gewichtung 50 × Abstand² — schwächer als harte Verletzungen (10000),
        # aber stark genug, um Lastausgleich zu überstimmen.
        info_dist_cost = 0.0
        for info_name in meta.get("info_names", ()):
            if info_name not in item_days:
                continue
            info_day = item_days[info_name]
            consumers = meta["successors_of"].get(info_name, [])
            latest_legal = None  # spätester legaler Tag für die Info
            for cname, delay in consumers:
                if cname in item_days:
                    cand = item_days[cname] - delay - 1
                    if latest_legal is None or cand < latest_legal:
                        latest_legal = cand
            if latest_legal is not None and info_day < latest_legal:
                gap = latest_legal - info_day
                info_dist_cost += gap * gap

        return violations * 10000.0 + load_cost + info_dist_cost * 50.0

    def _optimize_sweep(self, days: list[list[dict]], meta: dict,
                        reverse: bool = False) -> bool:
        """Sweep-Optimierung: jeden Tag durchgehen und für jedes Item den
        besten Ziel-Tag finden und sofort anwenden (First-Improvement pro Item,
        Best-of-Targets). Mehrere Moves pro Aufruf möglich.
        reverse=True → Rückwärts-Sweep, hilft Items vom letzten Tag zu befreien."""
        improved = False
        n = len(days)
        day_range = range(n - 1, -1, -1) if reverse else range(n)
        for i in day_range:
            for entry in list(days[i]):  # Snapshot: items vom Start dieses Tags
                base_cost = self._plan_cost(days, meta)
                best_cost = base_cost
                best_k    = None
                for k in range(n):
                    if k == i or not self._can_move(days, entry, i, k, meta):
                        continue
                    days[i].remove(entry)
                    days[k].append(entry)
                    c = self._plan_cost(days, meta)
                    days[k].remove(entry)
                    days[i].append(entry)
                    if c < best_cost:
                        best_cost = c
                        best_k    = k
                if best_k is not None:
                    days[i].remove(entry)
                    days[best_k].append(entry)
                    improved = True
        return improved

    def _update_day_colors(self, loads: list[int]):
        """Färbt Tag-Header rot (Überlast) oder blau (Unterlast) relativ zum Ø."""
        if not loads:
            return
        total = sum(loads)
        n     = len(loads)
        avg   = total / n if n > 0 else 0

        over_brush   = QColor(self._over_color)
        under_brush  = QColor(self._under_color)
        normal_brush = QColor(self._list_bg)

        for i, load in enumerate(loads):
            day = self._tree.topLevelItem(i)
            if day is None:
                continue
            if avg > 0 and load > avg * 1.25:
                bg = over_brush
            elif avg > 0 and load < avg * 0.75:
                bg = under_brush
            else:
                bg = normal_brush
            day.setBackground(0, bg)
            day.setBackground(1, bg)

    def _set_filter(self, kind: str, visible: bool):
        """Setzt Filter-Flag und aktualisiert Sichtbarkeit — keine Kalkulations-Auswirkung."""
        if kind == "teach":
            self._show_teach  = visible
        elif kind == "repeat":
            self._show_repeat = visible
        elif kind == "info":
            self._show_info   = visible
        self._apply_filters()

    def _apply_filters(self):
        """Zeigt/versteckt Einträge je nach Filter-Zustand."""
        for i in range(self._tree.topLevelItemCount()):
            day = self._tree.topLevelItem(i)
            for j in range(day.childCount()):
                child = day.child(j)
                entry = child.data(0, _ROLE) or {}
                kind  = entry.get("kind", "teach")
                show  = (
                    (kind == "teach"  and self._show_teach)  or
                    (kind == "repeat" and self._show_repeat) or
                    (kind == "info"   and self._show_info)
                )
                child.setHidden(not show)

    # ── Manuelle Bearbeitung (Buttons) ────────────────────────────────────

    def _selected_entry(self):
        sel = self._tree.currentItem()
        if sel is None or sel.parent() is None:
            return None, None
        return sel, sel.parent()

    def _on_move_up(self):
        child, parent = self._selected_entry()
        if child is None:
            return
        idx = parent.indexOfChild(child)
        if idx <= 0:
            return
        # Rückgabewert explizit nutzen — PySide6 kann das Item sonst freigeben
        taken = parent.takeChild(idx)
        parent.insertChild(idx - 1, taken)
        self._tree.setCurrentItem(taken)

    def _on_move_down(self):
        child, parent = self._selected_entry()
        if child is None:
            return
        idx = parent.indexOfChild(child)
        if idx >= parent.childCount() - 1:
            return
        taken = parent.takeChild(idx)
        parent.insertChild(idx + 1, taken)
        self._tree.setCurrentItem(taken)

    def _move_to_day(self, direction: int):
        child, parent = self._selected_entry()
        if child is None:
            return
        day_idx    = self._tree.indexOfTopLevelItem(parent)
        target_idx = day_idx + direction
        if target_idx < 0 or target_idx >= self._tree.topLevelItemCount():
            return
        target_day = self._tree.topLevelItem(target_idx)
        parent.takeChild(parent.indexOfChild(child))
        if direction < 0:
            target_day.addChild(child)
        else:
            target_day.insertChild(0, child)
        self._recalc_day_header(parent)
        self._recalc_day_header(target_day)
        self._recalc_all_stats()
        self._tree.setCurrentItem(child)

    # ── Export nach Notizen ───────────────────────────────────────────────

    def _on_export_notes(self):
        """Exportiert den Plan als Notizen-JSON für Callers Caddy."""
        default = os.path.join(self._cd_dir, "class_plan_notes.json")
        path, _ = QFileDialog.getSaveFileName(
            self, _t("cd.btn_export_notes"), default, "JSON (*.json)")
        if not path:
            return
        try:
            kind_prefix = {"teach": "N", "repeat": "R", "info": "I"}
            notes = []
            for i in range(self._tree.topLevelItemCount()):
                day = self._tree.topLevelItem(i)
                # Tag-Header als Trenner
                notes.append({"text": day.text(0), "type": "separator"})
                for j in range(day.childCount()):
                    entry  = day.child(j).data(0, _ROLE) or {}
                    kind   = entry.get("kind", "teach")
                    name   = entry.get("name", "")
                    prefix = kind_prefix.get(kind, "N")
                    notes.append({"text": f"{prefix}: {name}", "type": "normal"})
            with open(path, "w", encoding="utf-8") as f:
                json.dump(notes, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, _t("cd.btn_export_notes"), str(e))

    # ── JSON Load/Save ────────────────────────────────────────────────────

    def _to_dict(self) -> dict:
        evenings = []
        for i in range(self._tree.topLevelItemCount()):
            day   = self._tree.topLevelItem(i)
            items = []
            for j in range(day.childCount()):
                entry = day.child(j).data(0, _ROLE) or {}
                items.append({k: v for k, v in entry.items()
                              if not k.startswith("_")})
            evenings.append(items)
        return {"type": _COL3_TYPE, "evenings": evenings}

    def _from_dict(self, data: dict):
        evenings = data.get("evenings", [])
        loads    = [sum(e.get("effort", 0) for e in day) for day in evenings]
        self.set_plan(evenings, loads, n_evenings=len(evenings))

    def _on_load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, _t("cd.load_title_result"), self._cd_dir, "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("type") != _COL3_TYPE:
                QMessageBox.warning(self, _t("cd.load_title_result"), _t("cd.wrong_file_type"))
                return
            self._from_dict(data)
        except Exception as e:
            QMessageBox.critical(self, _t("cd.load_title_result"), str(e))

    def _on_save(self):
        default = os.path.join(self._cd_dir, "class_plan.json")
        path, _ = QFileDialog.getSaveFileName(
            self, _t("cd.save_title_result"), default, "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, _t("cd.save_title_result"), str(e))


# ── Hauptfenster ──────────────────────────────────────────────────────────────

class ClassDesignerWindow(QMainWindow):

    def __init__(self, app_dir: str):
        super().__init__()
        self._app_dir = app_dir
        self._cd_dir  = os.path.join(app_dir, "class_designer")
        os.makedirs(self._cd_dir, exist_ok=True)
        self.setWindowTitle(f"{_APP_NAME} v{_VERSION}")
        self.setMinimumSize(1100, 650)
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Übergangs-Buttons
        trans_row = QHBoxLayout(); trans_row.setSpacing(6)
        trans_row.addStretch(3)

        self._btn_copy = QPushButton(_t("cd.btn_copy_to_plan"))
        self._btn_copy.setFixedHeight(28)
        self._btn_copy.clicked.connect(self._on_copy_teaching_order)
        trans_row.addWidget(self._btn_copy)

        trans_row.addStretch(3)

        self._btn_generate = QPushButton(_t("cd.btn_generate"))
        self._btn_generate.setFixedHeight(28)
        self._btn_generate.setStyleSheet("QPushButton { font-weight: bold; padding: 3px 14px; }")
        self._btn_generate.clicked.connect(self._on_generate)
        trans_row.addWidget(self._btn_generate)

        trans_row.addStretch(3)
        root.addLayout(trans_row)

        # Dreispaltiger Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._col1 = Col1Widget(self._cd_dir)
        self._col1.zoom_changed.connect(self._apply_zoom)
        splitter.addWidget(self._col1)

        self._col2 = Col2Widget(self._cd_dir)
        splitter.addWidget(self._col2)

        self._col3 = Col3Widget(self._cd_dir)
        splitter.addWidget(self._col3)

        splitter.setSizes([300, 380, 380])
        root.addWidget(splitter, stretch=1)

        # Einheitliche Startschrift für alle drei Listen erzwingen
        self._apply_zoom(_ZOOM_DEFAULT)

    # ── Zoom ──────────────────────────────────────────────────────────────

    def _apply_zoom(self, pct: int):
        """Wendet Zoom-Prozentsatz auf alle drei Listen an."""
        px = max(8, int(_FONT_BASE_PX * pct / 100))
        # Schrift aus aktuellem Widget-Font ableiten (erhält Familie aus QSS)
        base = self._col1._list.font()
        base.setPixelSize(px)
        self._col1._list.setFont(base)
        base2 = self._col2._tree.font()
        base2.setPixelSize(px)
        self._col2._tree.setFont(base2)
        base3 = self._col3._tree.font()
        base3.setPixelSize(px)
        self._col3._tree.setFont(base3)

    # ── Übergänge ─────────────────────────────────────────────────────────

    def _on_copy_teaching_order(self):
        items = self._col1.teaching_order_items()
        if not items:
            return

        msg = QMessageBox(self)
        msg.setWindowTitle(_t("cd.btn_copy_to_plan"))
        msg.setText(_t("cd.confirm_copy").format(n=len(items)))
        btn_replace = msg.addButton(_t("cd.copy_mode_replace"), QMessageBox.AcceptRole)
        btn_append  = msg.addButton(_t("cd.copy_mode_append"),  QMessageBox.AcceptRole)
        msg.addButton(_t("cd.btn_cancel"), QMessageBox.RejectRole)
        msg.setDefaultButton(btn_replace)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == btn_replace:
            self._col2.set_items(items)
        elif clicked == btn_append:
            self._col2.set_items(self._col2.items() + items)

    def _on_generate(self):
        items = self._col2.items()
        if not items:
            QMessageBox.information(self, _t("cd.btn_generate"),
                                    _t("cd.nothing_to_generate"))
            return
        n = self._col1.n_evenings
        evenings, loads = ClassScheduler(items, n).generate()
        self._col3.set_plan(evenings, loads, plan_items=items, n_evenings=n)


# ── Einstiegspunkt ────────────────────────────────────────────────────────────

def main():
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()

    lang = "de"
    ini_path = os.path.join(app_dir, "callers_caddy.ini")
    if os.path.isfile(ini_path):
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(ini_path, encoding="utf-8")
        lang = cfg.get("display", "language", fallback="de")
    if "--lang" in sys.argv:
        idx = sys.argv.index("--lang")
        if idx + 1 < len(sys.argv):
            lang = sys.argv[idx + 1]
    set_language(lang)

    app = QApplication(sys.argv)
    app.setApplicationName(_APP_NAME)

    colors = _load_colors(app_dir)
    app.setStyleSheet(_build_qss(colors))

    win = ClassDesignerWindow(app_dir)
    win._col3.set_colors(
        text_color     = colors.get("text",      "#f0f0f0"),
        repeat_color   = colors.get("text_dim",  "#999999"),
        conflict_color = colors.get("warning",   "#ef4444"),
        list_bg        = colors.get("list_bg",   "#363636"),
    )
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
