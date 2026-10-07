"""Rueckfrage bei einer abweichenden gleichnamigen Lyrics-Datei (intern#167).

Zwei Formen: eine Meldung mit drei Knoepfen fuer eine einzelne Datei (Auswahl
in den Song-Daten) und ein Listen-Dialog fuer mehrere Dateien nach einem
Import. Die Regel selbst steht in lyrics_files. Zirkelfrei: keine
Rueckbezuege auf main.py.
"""
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QComboBox, QHeaderView, QDialogButtonBox, QMessageBox, QAbstractItemView,
)

from i18n import _t
import lyrics_files
from lyrics_files import (
    REPLACE, KEEP_BOTH, USE_EXISTING, NEWER, OLDER, LyricsConflict,
)

_DECISIONS = (
    (REPLACE, "lyrics_conflict_btn_replace"),
    (KEEP_BOTH, "lyrics_conflict_btn_keep_both"),
    (USE_EXISTING, "lyrics_conflict_btn_use_existing"),
)


def _stamp(mtime: float, size: int) -> str:
    """Aenderungsdatum und Groesse einer Datei als kurze Zeile."""
    when = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    return f"{when} · {size / 1024:.1f} KB"


def _guess_key(conflict: LyricsConflict) -> str:
    return {NEWER: "newer", OLDER: "older"}.get(conflict.guess, "unclear")


def default_decision(conflict: LyricsConflict) -> str:
    """Vorauswahl aus der Vermutung: nur eine juengere Datei ersetzt."""
    return REPLACE if conflict.guess == NEWER else USE_EXISTING


def ask_lyrics_conflict(parent, conflict: LyricsConflict):
    """Fragt fuer eine einzelne Datei. Gibt REPLACE, KEEP_BOTH oder
    USE_EXISTING zurueck, bei Abbrechen None."""
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Question)
    msg.setWindowTitle(_t("lyrics_conflict_title"))
    msg.setText(_t("lyrics_conflict_text", name=conflict.name))
    msg.setInformativeText("\n".join([
        _t("lyrics_conflict_existing",
           stamp=_stamp(conflict.dest_mtime, conflict.dest_size)),
        _t("lyrics_conflict_new",
           stamp=_stamp(conflict.src_mtime, conflict.src_size)),
        "",
        _t(f"lyrics_conflict_guess_{_guess_key(conflict)}"),
        "",
        _t("lyrics_conflict_bak_hint", name=conflict.name),
    ]))
    buttons = {
        msg.addButton(_t(key), QMessageBox.AcceptRole): decision
        for decision, key in _DECISIONS}
    msg.addButton(_t("btn_cancel"), QMessageBox.RejectRole)
    preferred = default_decision(conflict)
    msg.setDefaultButton(
        next(b for b, d in buttons.items() if d == preferred))
    msg.exec()
    return buttons.get(msg.clickedButton())


class LyricsConflictDialog(QDialog):
    """Liste abweichender Lyrics-Dateien nach einem Import; je Zeile waehlt
    der Caller, was mit der Datei geschieht."""

    _COL_FILE, _COL_EXISTING, _COL_NEW, _COL_GUESS, _COL_ACTION = range(5)

    def __init__(self, conflicts: list, parent=None):
        super().__init__(parent)
        self._conflicts = list(conflicts)
        self.setWindowTitle(_t("lyrics_conflict_title"))
        self.resize(820, 360)

        layout = QVBoxLayout(self)
        intro = QLabel(_t("lyrics_conflict_list_intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._table = QTableWidget(len(self._conflicts), 5)
        self._table.setHorizontalHeaderLabels([
            _t("lyrics_conflict_col_file"), _t("lyrics_conflict_col_existing"),
            _t("lyrics_conflict_col_new"), _t("lyrics_conflict_col_guess"),
            _t("lyrics_conflict_col_action")])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.NoSelection)
        self._combos = []
        for row, c in enumerate(self._conflicts):
            cells = (
                c.name,
                _stamp(c.dest_mtime, c.dest_size),
                _stamp(c.src_mtime, c.src_size),
                _t(f"lyrics_conflict_guess_short_{_guess_key(c)}"),
            )
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(c.src if col == self._COL_NEW else text)
                self._table.setItem(row, col, item)
            combo = self._decision_combo()
            combo.setCurrentIndex(combo.findData(default_decision(c)))
            self._table.setCellWidget(row, self._COL_ACTION, combo)
            self._combos.append(combo)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self._COL_FILE, QHeaderView.Stretch)
        layout.addWidget(self._table, 1)

        all_row = QHBoxLayout()
        all_row.addWidget(QLabel(_t("lyrics_conflict_for_all")))
        self._combo_all = self._decision_combo()
        self._combo_all.insertItem(0, _t("lyrics_conflict_for_all_choose"), None)
        self._combo_all.setCurrentIndex(0)
        self._combo_all.activated.connect(self._apply_to_all)
        all_row.addWidget(self._combo_all)
        all_row.addStretch(1)
        layout.addLayout(all_row)

        hint = QLabel(_t("lyrics_conflict_list_bak_hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText(_t("btn_ok"))
        box.button(QDialogButtonBox.Cancel).setText(_t("btn_cancel"))
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    @staticmethod
    def _decision_combo() -> QComboBox:
        combo = QComboBox()
        for decision, key in _DECISIONS:
            combo.addItem(_t(key), decision)
        return combo

    def _apply_to_all(self, _index):
        decision = self._combo_all.currentData()
        if decision is None:
            return
        for combo in self._combos:
            combo.setCurrentIndex(combo.findData(decision))

    def decisions(self) -> list:
        """Entscheidung je Datei, in der Reihenfolge der uebergebenen Liste."""
        return [combo.currentData() for combo in self._combos]


def resolve_with_dialog(parent, conflicts: list) -> list:
    """Zeigt den Listen-Dialog und fuehrt die Entscheidungen aus.

    Returns: je Konflikt der Dateiname im Lyrics-Ordner, der danach gilt.
    Abbrechen laesst alles, wie es ist (die vorhandenen Dateien)."""
    names = [c.name for c in conflicts]
    if not conflicts:
        return names
    dlg = LyricsConflictDialog(conflicts, parent)
    if dlg.exec() != QDialog.Accepted:
        return names
    for i, (conflict, decision) in enumerate(zip(conflicts, dlg.decisions())):
        try:
            names[i] = lyrics_files.resolve(conflict, decision)
        except OSError as e:
            print(f"[Lyrics] {conflict.name}: {decision} fehlgeschlagen: {e}")
    return names
