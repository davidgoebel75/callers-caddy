"""PROTOTYP — Wegwerf-Code, nicht in develop mergen.

Issue: davidgoebel75/callers-caddy-intern#186
Frage: Wie soll das Sequenzen-Widget aussehen (Bedienfluss, Filter, Liste)?
Drei strukturell verschiedene Varianten, umschaltbar ueber die Leiste unten
(Pfeile oder Alt+Links/Alt+Rechts). Echte Sequenzen aus der DB, nur lesend;
Knoepfe wie +Notiz / -> Filter / Loeschen sind Attrappen.

Start:  .venv\\Scripts\\python tools\\prototype_sequences_widget.py [pfad\\zur.db] [A|B|C]
"""

import sqlite3
import sys
import zlib
from pathlib import Path

from PySide6.QtCore import (
    QItemSelectionModel,
    QAbstractListModel, QAbstractTableModel, QEvent, QModelIndex, QObject,
    Qt, Signal,
)
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox,
    QCompleter, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListView, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QPushButton, QSplitter, QStackedWidget, QTableView, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget, QWidgetAction,
)

NO_TYPE = "(ohne Typ)"
ARROW = " → "

STYLE = """
QWidget { background: #0b1a2e; color: #dfe7f1; font-size: 13px; }
QFrame#panel, QTableView, QListView, QTableWidget, QListWidget {
    background: #0f2340; border: 1px solid #24446b; }
QHeaderView::section { background: #13294a; color: #dfe7f1; border: 0;
    border-bottom: 1px solid #24446b; padding: 4px; font-weight: bold; }
QTableView::item:selected, QListView::item:selected, QTableWidget::item:selected,
QListWidget::item:selected { background: #2b5cb8; color: white; }
QComboBox, QLineEdit, QToolButton#pick { background: #13294a;
    border: 1px solid #2f5584; border-radius: 3px; padding: 3px 6px; }
QPushButton { background: #3d6fd6; color: white; border: 0; border-radius: 3px;
    padding: 5px 12px; font-weight: bold; }
QPushButton:disabled { background: #22395c; color: #6d84a3; }
QPushButton#danger { background: #8a2f3a; }
QPushButton#flat, QToolButton#flat { background: transparent; color: #9fb4d0;
    border: 0; padding: 2px 6px; font-weight: normal; }
QPushButton#seg { background: #13294a; border: 1px solid #2f5584; color: #dfe7f1;
    font-weight: normal; padding: 3px 10px; border-radius: 10px; }
QPushButton#seg:checked { background: #3d6fd6; border-color: #3d6fd6; color: white; }
QLabel#muted { color: #8aa0bf; font-size: 11px; }
QLabel#h { color: #9fb4d0; font-size: 11px; font-weight: bold; }
QFrame#switcher { background: #f5c542; border-radius: 16px; }
QFrame#switcher QLabel, QFrame#switcher QToolButton { background: transparent;
    color: #1a1a1a; font-weight: bold; border: 0; }
QToolTip { background: #fffbe6; color: #111; border: 1px solid #999; }
"""


# --------------------------------------------------------------------------
# Daten + Filterlogik (geteilt, nur das Layout unterscheidet die Varianten)
# --------------------------------------------------------------------------

class Data:
    def __init__(self, db_path):
        c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        ent_rows = c.execute(
            "SELECT entity_id, MIN(teaching_order), canonical_name "
            "FROM teaching_order_calls GROUP BY entity_id").fetchall()
        self.ent_to = {e: to for e, to, _ in ent_rows}
        self.ent_name = {e: n for e, _, n in ent_rows}
        text_ents = {}
        for t, e in c.execute("SELECT call_text, entity_id FROM call_text_mappings "
                              "WHERE entity_id IS NOT NULL"):
            text_ents.setdefault(t, set()).add(e)
        for t, e in c.execute("SELECT call_text, entity_id FROM call_text_figures_extra"):
            text_ents.setdefault(t, set()).add(e)
        seq_ents = {}
        for sid, t in c.execute("SELECT sequence_id, call_text FROM sequence_calls"):
            seq_ents.setdefault(sid, set()).update(text_ents.get(t, ()))

        cols = ", ".join(f"field_{i}" for i in range(1, 16))
        rows = c.execute(f"SELECT id, {cols}, type, difficulty, tags, max_teaching_order "
                         "FROM sequences WHERE max_teaching_order IS NOT NULL "
                         "ORDER BY id").fetchall()
        self.demo_tags = not any(r[18] for r in rows)
        demo = ["Teach", "Party", "Workshop", "Lieblinge", "Hex-tauglich"]
        self.seqs = []
        for r in rows:
            tags = {t.strip() for t in (r[18] or "").split(",") if t.strip()}
            if self.demo_tags:  # ponytail: DB ohne Tags -> Demo-Tags, nur fuers Gefuehl
                h = zlib.crc32(str(r[0]).encode())
                tags = {demo[h % 5]} if h % 3 else set()
            self.seqs.append(dict(
                id=r[0], calls=[f for f in r[1:16] if f], type=r[16] or NO_TYPE,
                diff=r[17] or "", tags=tags, max_to=r[19],
                ents=seq_ents.get(r[0], set())))
        used = set().union(*(s["ents"] for s in self.seqs))
        self.figures = sorted((e for e in used if e in self.ent_to),
                              key=lambda e: self.ent_to[e])
        order = ["Easy", "Medium", "Hard"]
        diffs = {s["diff"] for s in self.seqs if s["diff"]}
        self.diffs = [d for d in order if d in diffs] + sorted(diffs - set(order))
        self.tags = sorted(set().union(*(s["tags"] for s in self.seqs)))

    def label(self, e):
        return self.ent_name.get(e, e)

    def figures_until(self, limit):
        """Enthaelt-Liste: nur Figuren bis zur Limit-Figur."""
        if limit is None:
            return self.figures
        return [e for e in self.figures if self.ent_to[e] <= self.ent_to[limit]]

    def filter(self, st, skip=None):
        lim = self.ent_to.get(st["limit"]) if st["limit"] else None
        out = []
        for s in self.seqs:
            if lim is not None:
                if s["max_to"] > lim:
                    continue
                if st["only"] and s["max_to"] < int(lim):
                    continue
            if st["contains"]:
                hit = (st["contains"] <= s["ents"] if st["mode"] == "UND"
                       else st["contains"] & s["ents"])
                if not hit:
                    continue
            if skip != "diff" and st["diffs"] and s["diff"] not in st["diffs"]:
                continue
            if skip != "tags" and st["tags"] and not (st["tags"] & s["tags"]):
                continue
            if skip != "types" and st["types"] and s["type"] not in st["types"]:
                continue
            out.append(s)
        return out


def count_by(seqs, key):
    out = {}
    for s in seqs:
        vals = s[key] if isinstance(s[key], set) else [s[key]]
        for v in vals:
            out[v] = out.get(v, 0) + 1
    return out


def tooltip(s):
    head = f"<b>{s['type']}</b> · {s['diff'] or '–'} · {len(s['calls'])} Calls"
    body = "".join(f"<tr><td align=right style='color:#888'>{i}.</td><td>{c}</td></tr>"
                   for i, c in enumerate(s["calls"], 1))
    return f"{head}<table cellspacing=0 cellpadding=1>{body}</table>"


# --------------------------------------------------------------------------
# Modelle
# --------------------------------------------------------------------------

class SeqTableModel(QAbstractTableModel):
    HEAD = ["Sequenz", "Typ", "Schwierigkeit"]

    def __init__(self):
        super().__init__()
        self.rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, p=QModelIndex()):
        return 0 if p.isValid() else len(self.rows)

    def columnCount(self, p=QModelIndex()):
        return 3

    def headerData(self, sec, orient, role=Qt.DisplayRole):
        if orient == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEAD[sec]

    def data(self, idx, role=Qt.DisplayRole):
        s = self.rows[idx.row()]
        if role == Qt.DisplayRole:
            return [ARROW.join(s["calls"]), s["type"], s["diff"]][idx.column()]
        if role == Qt.ToolTipRole:
            return tooltip(s)


class SeqCardModel(QAbstractListModel):
    """Variante C: zweizeilige Karte, ganze Sequenz umbrochen."""

    def __init__(self):
        super().__init__()
        self.rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, p=QModelIndex()):
        return 0 if p.isValid() else len(self.rows)

    def data(self, idx, role=Qt.DisplayRole):
        s = self.rows[idx.row()]
        if role == Qt.DisplayRole:
            meta = f"{s['type']}  ·  {s['diff'] or '–'}  ·  {len(s['calls'])} Calls"
            return f"{meta}\n{ARROW.join(s['calls'])}"


# --------------------------------------------------------------------------
# Bausteine
# --------------------------------------------------------------------------

class MultiPick(QToolButton):
    """Knopf mit Popup: Suchfeld + Haekchen-Liste (+ optional ODER/UND)."""
    changed = Signal()

    def __init__(self, label, with_mode=False):
        super().__init__()
        self.setObjectName("pick")
        self.setPopupMode(QToolButton.InstantPopup)
        self.label, self.selected, self.mode = label, set(), "ODER"
        self._names = {}
        box = QWidget()
        lay = QVBoxLayout(box)
        self.search = QLineEdit(placeholderText="Suchen …")
        self.search.textChanged.connect(self._apply_search)
        lay.addWidget(self.search)
        if with_mode:
            row = QHBoxLayout()
            row.addWidget(QLabel("Verknuepfung:"))
            self.mode_box = QComboBox()
            self.mode_box.addItems(["ODER", "UND"])
            self.mode_box.currentTextChanged.connect(self._set_mode)
            row.addWidget(self.mode_box, 1)
            lay.addLayout(row)
        self.list = QListWidget()
        self.list.setMinimumSize(280, 320)
        self.list.itemChanged.connect(self._on_item)
        lay.addWidget(self.list)
        clear = QPushButton("Auswahl leeren", objectName="flat")
        clear.clicked.connect(self.clear)
        lay.addWidget(clear)
        menu = QMenu(self)
        act = QWidgetAction(menu)
        act.setDefaultWidget(box)
        menu.addAction(act)
        menu.aboutToShow.connect(self.search.setFocus)
        self.setMenu(menu)
        self._update_text()

    def set_options(self, opts):
        """opts: [(key, anzeige)] — Auswahl ausserhalb der Optionen faellt weg."""
        self.list.blockSignals(True)
        self.list.clear()
        self._names = dict(opts)
        for key, text in opts:
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, key)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if key in self.selected else Qt.Unchecked)
            self.list.addItem(it)
        self.list.blockSignals(False)
        self._apply_search(self.search.text())
        gone = self.selected - set(self._names)
        if gone:
            self.selected -= gone
            self._update_text()
            self.changed.emit()

    def clear(self):
        self.selected.clear()
        self.set_options(list(self._names.items()))
        self._update_text()
        self.changed.emit()

    def _set_mode(self, m):
        self.mode = m
        self._update_text()
        self.changed.emit()

    def _apply_search(self, txt):
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(txt.lower() not in it.text().lower())

    def _on_item(self, it):
        key = it.data(Qt.UserRole)
        (self.selected.add if it.checkState() == Qt.Checked else self.selected.discard)(key)
        self._update_text()
        self.changed.emit()

    def _update_text(self):
        if not self.selected:
            val = "(alle)"
        else:
            names = [self._names.get(k, k).split("  (")[0] for k in self.selected]
            sep = " und " if self.mode == "UND" else " oder "
            val = sep.join(sorted(names)) if len(names) <= 2 else f"{len(names)} gewaehlt"
        self.setText(f"{self.label}: {val}  ▾")


class TypeList(QTableWidget):
    """Typ-Liste mit Anzahl-Spalte; Klick / Strg-Klick waehlt."""
    changed = Signal()

    def __init__(self, with_all_row=False):
        super().__init__(0, 2)
        self.with_all = with_all_row
        self.setHorizontalHeaderLabels(["Typ", "Anz."])
        self.verticalHeader().hide()
        self.setShowGrid(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        h = self.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.verticalHeader().setDefaultSectionSize(22)
        self.itemSelectionChanged.connect(self.changed.emit)
        self.selected = set()

    def fill(self, counts, total):
        keep = self.selected
        self.blockSignals(True)
        self.clearSelection()
        self.clearContents()
        items = sorted(counts.items(), key=lambda kv: (kv[0] == NO_TYPE, kv[0]))
        if self.with_all:
            items = [(None, total)] + items
        self.setRowCount(len(items))
        for r, (t, n) in enumerate(items):
            a = QTableWidgetItem(t if t else "Alle Typen")
            a.setData(Qt.UserRole, t)
            b = QTableWidgetItem(str(n))
            b.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.setItem(r, 0, a)
            self.setItem(r, 1, b)
            if t in keep:
                self.selectRow(r) if len(keep) == 1 else self._add_row(r)
        self.blockSignals(False)
        self._read()

    def _add_row(self, r):
        self.selectionModel().select(
            self.model().index(r, 0),
            QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def _read(self):
        rows = {i.row() for i in self.selectedIndexes()}
        sel = {self.item(r, 0).data(Qt.UserRole) for r in rows}
        self.selected = set() if None in sel else sel

    def selectionChanged(self, a, b):
        super().selectionChanged(a, b)
        self._read()


class CheckGroup(QWidget):
    """Haekchen-Liste mit Anzahl (Variante A) oder Segment-Knoepfe (Variante C)."""
    changed = Signal()

    def __init__(self, segmented=False):
        super().__init__()
        self.segmented = segmented
        self.lay = (QHBoxLayout if segmented else QVBoxLayout)(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.boxes = {}
        self.selected = set()

    def fill(self, values, counts):
        if list(self.boxes) != list(values):
            for b in self.boxes.values():
                b.deleteLater()
            self.boxes = {}
            for v in values:
                b = QPushButton(objectName="seg") if self.segmented else QCheckBox()
                b.setCheckable(True)
                b.toggled.connect(lambda on, v=v: self._toggle(v, on))
                self.lay.addWidget(b)
                self.boxes[v] = b
            if self.segmented:
                self.lay.addStretch()
        for v, b in self.boxes.items():
            b.setText(f"{v}  ({counts.get(v, 0)})")

    def _toggle(self, v, on):
        (self.selected.add if on else self.selected.discard)(v)
        self.changed.emit()


def zoomable(view, status_label=None):
    """Strg+Mausrad zoomt die Schrift der Liste (wie heute install_ctrl_wheel_zoom)."""
    class F(QObject):
        def eventFilter(self, obj, ev):
            if ev.type() == QEvent.Wheel and ev.modifiers() & Qt.ControlModifier:
                step(1 if ev.angleDelta().y() > 0 else -1)
                return True
            return False

    def step(d):
        f = view.font()
        f.setPointSize(max(7, min(24, f.pointSize() + d)))
        view.setFont(f)
        if status_label:
            status_label.setText(f"{round(f.pointSize() / 10 * 100)}%")

    view._zoom_filter = F(view)
    view.viewport().installEventFilter(view._zoom_filter)
    return step


def seq_table():
    v = QTableView()
    v.setSelectionBehavior(QAbstractItemView.SelectRows)
    v.setSelectionMode(QAbstractItemView.ExtendedSelection)
    v.verticalHeader().hide()
    v.setShowGrid(False)
    v.setWordWrap(False)
    v.setTextElideMode(Qt.ElideRight)
    v.verticalHeader().setDefaultSectionSize(28)
    v.setModel(SeqTableModel())
    h = v.horizontalHeader()
    h.setSectionResizeMode(0, QHeaderView.Stretch)
    h.setSectionResizeMode(1, QHeaderView.Interactive)
    h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
    v.setColumnWidth(1, 170)
    f = v.font()
    f.setPointSize(10)
    v.setFont(f)
    return v


def limit_combo(data):
    cb = QComboBox()
    cb.setEditable(True)
    cb.setInsertPolicy(QComboBox.NoInsert)
    cb.addItem("(kein Limit)", None)
    all_ents = sorted(data.ent_to, key=data.ent_to.get)
    for e in all_ents:
        cb.addItem(data.label(e), e)
    comp = cb.completer()
    comp.setFilterMode(Qt.MatchContains)
    comp.setCompletionMode(QCompleter.PopupCompletion)
    return cb


# --------------------------------------------------------------------------
# Varianten-Basis: haelt Filter-Zustand und fuettert Widgets
# --------------------------------------------------------------------------

class Variant(QWidget):
    NAME = ""
    notify = Signal(str)

    def __init__(self, data):
        super().__init__()
        self.data = data
        self._busy = False

    def state(self):
        raise NotImplementedError

    def refresh(self):
        if self._busy:
            return
        self._busy = True
        st = self.state()
        d = self.data
        self.contains.set_options(
            [(e, d.label(e)) for e in d.figures_until(st["limit"])])
        st = self.state()
        rows = d.filter(st)
        self.type_list.fill(count_by(d.filter(st, skip="types"), "type"),
                            len(d.filter(st, skip="types")))
        self.fill_diff(count_by(d.filter(st, skip="diff"), "diff"))
        self.fill_tags(count_by(d.filter(st, skip="tags"), "tags"))
        self.list_model.set_rows(rows)
        tag_hint = " · Tags sind Demo-Werte" if d.demo_tags else ""
        self.count.setText(f"{len(rows)} von {len(d.seqs)} Sequenzen{tag_hint}")
        self._busy = False

    def stub(self, what):
        n = len(self.list_view.selectionModel().selectedRows())
        self.notify.emit(f"Attrappe: »{what}« fuer {n} markierte Sequenz(en)")


# ---------------- Variante A: Seitenleiste ----------------

class VariantA(Variant):
    NAME = "Filter-Seitenleiste"

    def __init__(self, data):
        super().__init__(data)
        root = QVBoxLayout(self)
        # Aktionen gebuendelt oben, wirken auf Markierung
        bar = QHBoxLayout()
        for txt, name in (("+ Notiz", ""), ("→ Filter", ""), ("Loeschen", "danger")):
            b = QPushButton(txt, objectName=name)
            b.clicked.connect(lambda _=0, t=txt: self.stub(t))
            bar.addWidget(b)
        bar.addStretch()
        self.count = QLabel(objectName="muted")
        bar.addWidget(self.count)
        root.addLayout(bar)

        split = QSplitter(Qt.Horizontal)
        side = QFrame(objectName="panel")
        sl = QVBoxLayout(side)
        sl.addWidget(QLabel("LIMIT", objectName="h"))
        self.limit = limit_combo(data)
        sl.addWidget(self.limit)
        self.only = QCheckBox("Nur dieses Programm")
        sl.addWidget(self.only)
        sl.addWidget(QLabel("ENTHAELT", objectName="h"))
        self.contains = MultiPick("Figuren", with_mode=True)
        sl.addWidget(self.contains)
        sl.addWidget(QLabel("SCHWIERIGKEIT", objectName="h"))
        self.diff = CheckGroup()
        sl.addWidget(self.diff)
        sl.addWidget(QLabel("TAGS", objectName="h"))
        self.tags = CheckGroup()
        sl.addWidget(self.tags)
        sl.addWidget(QLabel("TYP", objectName="h"))
        self.type_list = TypeList()
        sl.addWidget(self.type_list, 1)
        reset = QPushButton("Alle Filter zuruecksetzen", objectName="flat")
        reset.clicked.connect(self.reset)
        sl.addWidget(reset)
        split.addWidget(side)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.list_view = seq_table()
        self.list_model = self.list_view.model()
        rl.addWidget(self.list_view)
        zrow = QHBoxLayout()
        zrow.addWidget(QLabel("Tipp: Strg+Mausrad zoomt · Hover zeigt ganze Sequenz",
                              objectName="muted"))
        zrow.addStretch()
        zl = QLabel("100%", objectName="muted")
        step = zoomable(self.list_view, zl)
        for t, d in (("−", -1), ("+", 1)):
            b = QToolButton(text=t, objectName="flat")
            b.clicked.connect(lambda _=0, d=d: step(d))
            zrow.addWidget(b) if d < 0 else None
            if d > 0:
                zrow.addWidget(zl)
                zrow.addWidget(b)
        rl.addLayout(zrow)
        split.addWidget(right)
        side.setMaximumWidth(330)
        split.setSizes([290, 800])
        root.addWidget(split, 1)

        for sig in (self.limit.currentIndexChanged, self.only.toggled,
                    self.contains.changed, self.diff.changed, self.tags.changed,
                    self.type_list.changed):
            sig.connect(self.refresh)
        self.refresh()

    def fill_diff(self, c):
        self.diff.fill(self.data.diffs, c)

    def fill_tags(self, c):
        self.tags.fill(self.data.tags, c)

    def reset(self):
        self.limit.setCurrentIndex(0)
        self.only.setChecked(False)
        for g in (self.diff, self.tags):
            for b in g.boxes.values():
                b.setChecked(False)
        self.type_list.clearSelection()
        self.contains.clear()

    def state(self):
        return dict(limit=self.limit.currentData(), only=self.only.isChecked(),
                    contains=set(self.contains.selected), mode=self.contains.mode,
                    diffs=set(self.diff.selected), tags=set(self.tags.selected),
                    types=set(self.type_list.selected))


# ---------------- Variante B: Filterleiste + Typ-Leiste oben ----------------

class VariantB(Variant):
    NAME = "Filterleiste + Typ oben, Aktionen unten"

    def __init__(self, data):
        super().__init__(data)
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        self.limit = limit_combo(data)
        self.limit.setMinimumWidth(180)
        row.addWidget(QLabel("Limit:"))
        row.addWidget(self.limit)
        self.only = QCheckBox("Nur")
        row.addWidget(self.only)
        self.contains = MultiPick("Enthaelt", with_mode=True)
        self.diffp = MultiPick("Schwierigkeit")
        self.tagp = MultiPick("Tags")
        for w in (self.contains, self.diffp, self.tagp):
            row.addWidget(w)
        row.addStretch()
        gear = QToolButton(text="⚙", objectName="flat")
        gear.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(gear)
        gear.setMenu(m)
        row.addWidget(gear)
        root.addLayout(row)

        split = QSplitter(Qt.Vertical)
        self.type_list = TypeList(with_all_row=True)
        split.addWidget(self.type_list)
        self.list_view = seq_table()
        self.list_model = self.list_view.model()
        split.addWidget(self.list_view)
        split.setSizes([170, 600])
        root.addWidget(split, 1)
        step = zoomable(self.list_view)
        m.addAction("Groesser (Strg+Mausrad)", lambda: step(1))
        m.addAction("Kleiner", lambda: step(-1))
        m.addSeparator()
        m.addAction("Auch ausgeblendete Sequenzen anzeigen").setCheckable(True)

        bottom = QHBoxLayout()
        self.count = QLabel(objectName="muted")
        bottom.addWidget(self.count)
        bottom.addStretch()
        self.sel = QLabel(objectName="muted")
        bottom.addWidget(self.sel)
        self.actions = []
        for txt, name in (("+ Notiz", ""), ("→ Filter", ""), ("Loeschen", "danger")):
            b = QPushButton(txt, objectName=name)
            b.clicked.connect(lambda _=0, t=txt: self.stub(t))
            bottom.addWidget(b)
            self.actions.append(b)
        root.addLayout(bottom)
        self.list_view.selectionModel().selectionChanged.connect(self._sel_changed)
        self._sel_changed()

        for sig in (self.limit.currentIndexChanged, self.only.toggled,
                    self.contains.changed, self.diffp.changed, self.tagp.changed,
                    self.type_list.changed):
            sig.connect(self.refresh)
        self.refresh()

    def _sel_changed(self, *_):
        n = len(self.list_view.selectionModel().selectedRows())
        self.sel.setText(f"{n} markiert" if n else "nichts markiert")
        for b in self.actions:
            b.setEnabled(bool(n))

    def refresh(self):
        super().refresh()
        if hasattr(self, "sel"):
            self._sel_changed()

    def fill_diff(self, c):
        self.diffp.set_options([(v, f"{v}  ({c.get(v, 0)})") for v in self.data.diffs])

    def fill_tags(self, c):
        self.tagp.set_options([(v, f"{v}  ({c.get(v, 0)})") for v in self.data.tags])

    def state(self):
        return dict(limit=self.limit.currentData(), only=self.only.isChecked(),
                    contains=set(self.contains.selected), mode=self.contains.mode,
                    diffs=set(self.diffp.selected), tags=set(self.tagp.selected),
                    types=set(self.type_list.selected))


# ---------------- Variante C: Typ-Spalte + Karten ----------------

class ChipInput(QWidget):
    """Enthaelt als Chips: Figur tippen, Enter -> Chip; x entfernt."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.selected, self.mode, self._opts = set(), "ODER", {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.chips = QHBoxLayout()
        lay.addLayout(self.chips)
        self.edit = QLineEdit(placeholderText="Figur hinzufuegen …")
        self.comp = QCompleter([])
        self.comp.setFilterMode(Qt.MatchContains)
        self.comp.setCaseSensitivity(Qt.CaseInsensitive)
        self.comp.activated.connect(self._add)
        self.edit.setCompleter(self.comp)
        lay.addWidget(self.edit, 1)
        self.mode_btn = QPushButton("ODER", objectName="seg")
        self.mode_btn.setToolTip("Verknuepfung umschalten: ODER / UND")
        self.mode_btn.clicked.connect(self._toggle_mode)
        lay.addWidget(self.mode_btn)

    def set_options(self, opts):
        self._opts = {name: key for key, name in opts}
        self.comp.model().setStringList(list(self._opts))
        valid = set(self._opts.values())
        if self.selected - valid:
            self.selected &= valid
            self._redraw()
            self.changed.emit()

    def clear(self):
        self.selected.clear()
        self._redraw()
        self.changed.emit()

    def _add(self, name):
        key = self._opts.get(name)
        if key:
            self.selected.add(key)
            self._redraw()
            self.changed.emit()
        self.edit.clear()

    def _toggle_mode(self):
        self.mode = "UND" if self.mode == "ODER" else "ODER"
        self.mode_btn.setText(self.mode)
        self.changed.emit()

    def _redraw(self):
        while self.chips.count():
            self.chips.takeAt(0).widget().deleteLater()
        names = {v: k for k, v in self._opts.items()}
        for key in sorted(self.selected, key=lambda k: names.get(k, k)):
            b = QPushButton(f"{names.get(key, key)}  ✕", objectName="seg")
            b.setCheckable(True)
            b.setChecked(True)
            b.clicked.connect(lambda _=0, k=key: self._remove(k))
            self.chips.addWidget(b)

    def _remove(self, key):
        self.selected.discard(key)
        self._redraw()
        self.changed.emit()


class VariantC(Variant):
    NAME = "Typ-Spalte links, Karten-Liste"

    def __init__(self, data):
        super().__init__(data)
        root = QHBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        self.type_list = TypeList(with_all_row=True)
        split.addWidget(self.type_list)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Bis:"))
        self.limit = limit_combo(data)
        self.limit.setMinimumWidth(170)
        r1.addWidget(self.limit)
        self.only = QCheckBox("Nur")
        r1.addWidget(self.only)
        r1.addWidget(QLabel("Enthaelt:"))
        self.contains = ChipInput()
        r1.addWidget(self.contains, 1)
        rl.addLayout(r1)
        r2 = QHBoxLayout()
        self.diff = CheckGroup(segmented=True)
        self.tags = CheckGroup(segmented=True)
        r2.addWidget(self.diff, 1)
        r2.addWidget(QLabel("|", objectName="muted"))
        r2.addWidget(self.tags, 1)
        rl.addLayout(r2)

        self.list_view = QListView()
        self.list_view.setWordWrap(True)
        self.list_view.setSpacing(3)
        self.list_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_view.setLayoutMode(QListView.Batched)
        self.list_view.setUniformItemSizes(False)
        self.list_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list_model = SeqCardModel()
        self.list_view.setModel(self.list_model)
        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._ctx)
        f = self.list_view.font()
        f.setPointSize(10)
        self.list_view.setFont(f)
        rl.addWidget(self.list_view, 1)
        bottom = QHBoxLayout()
        self.count = QLabel(objectName="muted")
        bottom.addWidget(self.count)
        bottom.addStretch()
        zl = QLabel("100% · Strg+Mausrad · Rechtsklick fuer Aktionen", objectName="muted")
        zoomable(self.list_view, zl)
        bottom.addWidget(zl)
        rl.addLayout(bottom)
        split.addWidget(right)
        self.type_list.setMinimumWidth(230)
        split.setSizes([250, 800])
        root.addWidget(split)

        for sig in (self.limit.currentIndexChanged, self.only.toggled,
                    self.contains.changed, self.diff.changed, self.tags.changed,
                    self.type_list.changed):
            sig.connect(self.refresh)
        self.refresh()

    def _ctx(self, pos):
        m = QMenu(self)
        for t in ("+ Notiz", "→ Filter"):
            m.addAction(t, lambda t=t: self.stub(t))
        m.addSeparator()
        m.addAction("Loeschen …", lambda: self.stub("Loeschen"))
        m.exec(self.list_view.viewport().mapToGlobal(pos))

    def fill_diff(self, c):
        self.diff.fill(self.data.diffs, c)

    def fill_tags(self, c):
        self.tags.fill(self.data.tags, c)

    def state(self):
        return dict(limit=self.limit.currentData(), only=self.only.isChecked(),
                    contains=set(self.contains.selected), mode=self.contains.mode,
                    diffs=set(self.diff.selected), tags=set(self.tags.selected),
                    types=set(self.type_list.selected))


# --------------------------------------------------------------------------
# Fenster + Varianten-Umschalter
# --------------------------------------------------------------------------

class Window(QMainWindow):
    def __init__(self, data, start):
        super().__init__()
        self.setWindowTitle("PROTOTYP — Sequenzen-Widget")
        self.resize(1150, 820)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.variants = [VariantA(data), VariantB(data), VariantC(data)]
        for v in self.variants:
            self.stack.addWidget(v)
            v.notify.connect(self._flash)

        self.bar = QFrame(self, objectName="switcher")
        bl = QHBoxLayout(self.bar)
        bl.setContentsMargins(10, 4, 10, 4)
        prev = QToolButton(text="◀")
        nxt = QToolButton(text="▶")
        self.lbl = QLabel()
        prev.clicked.connect(lambda: self.go(-1))
        nxt.clicked.connect(lambda: self.go(1))
        for w in (prev, self.lbl, nxt):
            bl.addWidget(w)
        QShortcut(QKeySequence("Alt+Left"), self, lambda: self.go(-1))
        QShortcut(QKeySequence("Alt+Right"), self, lambda: self.go(1))
        self.stack.setCurrentIndex("ABC".index(start))
        self.go(0)

    def go(self, d):
        i = (self.stack.currentIndex() + d) % 3
        self.stack.setCurrentIndex(i)
        self.lbl.setText(f"{'ABC'[i]}  ({self.variants[i].NAME})")
        self._place()

    def _flash(self, msg):
        self.lbl.setText(msg)

    def _place(self):
        self.bar.adjustSize()
        self.bar.move((self.width() - self.bar.width()) // 2,
                      self.height() - self.bar.height() - 46)
        self.bar.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()


if __name__ == "__main__":
    args = sys.argv[1:]
    start = next((a.upper() for a in args if a.upper() in ("A", "B", "C")), "A")
    paths = [a for a in args if a.upper() not in ("A", "B", "C")]
    db = Path(paths[0]) if paths else Path(__file__).resolve().parents[1] / "src" / "callers_caddy.db"
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    w = Window(Data(db), start)
    w.show()
    sys.exit(app.exec())
