"""Konfliktklaerung beim Call-Map-Import (intern#79).

Je Call-Text, dessen importierte Figuren-Menge von der lokalen abweicht:
A = lokal behalten, B = Import uebernehmen, C = selbst waehlen (Figuren-
Picker, vorbelegt mit beiden Seiten). Vorausgewaehlt ist die Empfehlung aus
mapping_io.recommend (Detailliertheit, dann Quelle). Massen-Buttons setzen
alle Zeilen auf einmal; selbst gewaehlte Zeilen (C) bleiben dabei stehen.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QPushButton, QDialogButtonBox, QAbstractItemView,
)

import mapping_io
from i18n import _t

_COL_TEXT, _COL_A, _COL_B, _COL_CHOICE, _COL_RESULT = range(5)
_CHOICES = ("A", "B", "C")


def _source_label(mapped_by: str) -> str:
    """Uebersetzte Quelle (call_mapping_source_*, intern#88), sonst der
    interne Wert."""
    mb = str(mapped_by or "auto")
    key = f"call_mapping_source_{mb}"
    txt = _t(key)
    return mb if txt == key else txt


class MappingConflictDialog(QDialog):
    """Tabelle Call-Text | Lokal (A) | Import (B) | Auswahl | Ergebnis.

    Args:
        conflicts: [(call_text, lokal, lokal_mb, import, import_mb)]
            (SongDatabase.diff_call_text_figures()["conflicts"])
        entities: [(label, entity_id)] fuer den Figuren-Picker
        eid_to_label: entity_id -> Anzeigename
        suggest_fn: callable(call_text) -> Figuren der Mustererkennung
            (fuer "Naeher an der Mustererkennung"); None blendet den
            Button aus
        unknown_fn: callable(ids) -> ids ohne calls-Zeile (Picker-Markierung)
    """

    def __init__(self, conflicts, entities, eid_to_label, suggest_fn=None,
                 unknown_fn=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("mapping_conflict_title"))
        self.resize(980, 560)
        self._conflicts = list(conflicts)
        self._entities = entities
        self._labels = eid_to_label
        self._suggest_fn = suggest_fn
        self._unknown_fn = unknown_fn
        self._recommended = [mapping_io.recommend(loc, lmb, imp, imb)
                             for _ct, loc, lmb, imp, imb in self._conflicts]
        self._choice = list(self._recommended)
        self._custom = [None] * len(self._conflicts)   # Menge bei C

        layout = QVBoxLayout(self)
        intro = QLabel(_t("mapping_conflict_intro", count=len(self._conflicts)))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._table = QTableWidget(len(self._conflicts), 5)
        self._table.setHorizontalHeaderLabels([
            _t("mapping_conflict_col_text"), _t("mapping_conflict_col_local"),
            _t("mapping_conflict_col_import"), _t("mapping_conflict_col_choice"),
            _t("mapping_conflict_col_result")])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setWordWrap(True)
        hdr = self._table.horizontalHeader()
        for col in (_COL_TEXT, _COL_A, _COL_B, _COL_RESULT):
            hdr.setSectionResizeMode(col, QHeaderView.Stretch)
        hdr.setSectionResizeMode(_COL_CHOICE, QHeaderView.ResizeToContents)
        self._combos = []
        for i, (ct, loc, lmb, imp, imb) in enumerate(self._conflicts):
            self._table.setItem(i, _COL_TEXT, QTableWidgetItem(ct))
            self._table.setItem(i, _COL_A, QTableWidgetItem(self._describe(loc, lmb)))
            self._table.setItem(i, _COL_B, QTableWidgetItem(self._describe(imp, imb)))
            combo = QComboBox()
            for c in _CHOICES:
                text = _t(f"mapping_conflict_choice_{c.lower()}")
                if c == self._recommended[i]:
                    text += " " + _t("mapping_conflict_recommended")
                combo.addItem(text, userData=c)
            combo.setCurrentIndex(_CHOICES.index(self._choice[i]))
            combo.activated.connect(lambda _idx, row=i: self._on_choice(row))
            self._table.setCellWidget(i, _COL_CHOICE, combo)
            self._combos.append(combo)
            self._table.setItem(i, _COL_RESULT, QTableWidgetItem())
            self._refresh_result(i)
        self._table.resizeRowsToContents()
        layout.addWidget(self._table, 1)

        mass = QHBoxLayout()
        for key, handler in (
                ("mapping_conflict_all_left", lambda: self._set_all(lambda i: "A")),
                ("mapping_conflict_all_right", lambda: self._set_all(lambda i: "B")),
                ("mapping_conflict_closer_pattern", self._closer_to_pattern),
                ("mapping_conflict_closer_manual", self._closer_to_manual)):
            btn = QPushButton(_t(key))
            btn.setToolTip(_t(key + "_tip"))
            btn.clicked.connect(handler)
            if key == "mapping_conflict_closer_pattern" and suggest_fn is None:
                btn.setVisible(False)
            mass.addWidget(btn)
        mass.addStretch(1)
        layout.addLayout(mass)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(_t("mapping_conflict_apply"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---- Anzeige ----

    def _describe(self, figs, mapped_by=None) -> str:
        names = ", ".join(self._labels.get(e, e) for e in figs) \
            if figs else _t("mapping_conflict_no_figure")
        return f"{names}  ({_source_label(mapped_by)})" if mapped_by else names

    def _result_figs(self, row: int):
        _ct, loc, _lmb, imp, _imb = self._conflicts[row]
        c = self._choice[row]
        if c == "A":
            return loc
        if c == "B":
            return imp
        return self._custom[row] or []

    def _refresh_result(self, row: int):
        self._table.item(row, _COL_RESULT).setText(
            self._describe(self._result_figs(row)))

    def _set_choice(self, row: int, choice: str):
        self._choice[row] = choice
        combo = self._combos[row]
        combo.blockSignals(True)
        combo.setCurrentIndex(_CHOICES.index(choice))
        combo.blockSignals(False)
        self._refresh_result(row)

    # ---- Bedienung ----

    def _on_choice(self, row: int):
        choice = self._combos[row].currentData()
        if choice == "C":
            picked = self._pick(row)
            if picked is None:            # Abbruch: vorherige Wahl zurueck
                self._set_choice(row, self._choice[row])
                return
            self._custom[row] = picked
        self._set_choice(row, choice)

    def _pick(self, row: int):
        """Figuren-Picker, vorbelegt mit beiden Seiten. None = abgebrochen."""
        from sequences_widget import CallFiguresPickerDialog
        ct, loc, _lmb, imp, _imb = self._conflicts[row]
        start = self._custom[row] if self._custom[row] is not None \
            else list(dict.fromkeys(loc + imp))
        unknown = self._unknown_fn(start) if self._unknown_fn else ()
        dlg = CallFiguresPickerDialog(self._entities, selected=start,
                                      parent=self, unknown_ids=unknown)
        dlg.setWindowTitle(_t("seq_map_picker_text", text=ct))
        if dlg.exec() != QDialog.Accepted:
            return None
        return dlg.selected_entity_ids()

    def _set_all(self, choose):
        """Massen-Setzen; selbst gewaehlte Zeilen (C) bleiben unberuehrt.
        choose(row) -> 'A'/'B' oder None (dann die Empfehlung)."""
        for row in range(len(self._conflicts)):
            if self._choice[row] == "C":
                continue
            self._set_choice(row, choose(row) or self._recommended[row])

    def _closer_to_pattern(self):
        def choose(row):
            ct, loc, _lmb, imp, _imb = self._conflicts[row]
            return mapping_io.closer_to(self._suggest_fn(ct), loc, imp)
        self._set_all(choose)

    def _closer_to_manual(self):
        def choose(row):
            _ct, _loc, lmb, _imp, imb = self._conflicts[row]
            return mapping_io.manual_side(lmb, imb)
        self._set_all(choose)

    # ---- Ergebnis ----

    def choices(self) -> list:
        """'A'/'B'/'C' je Konflikt (Reihenfolge wie conflicts)."""
        return list(self._choice)

    def decisions(self) -> list:
        """(call_text, figuren, mapped_by) fuer apply_call_text_figures_decisions.

        A schreibt nichts (fehlt hier). B uebernimmt Menge und Quelle aus dem
        Import, C schreibt die gewaehlte Menge als 'manual' (leere Auswahl
        entfernt die Zuordnung, wie im Picker)."""
        out = []
        for row, (ct, _loc, _lmb, imp, imb) in enumerate(self._conflicts):
            c = self._choice[row]
            if c == "B":
                out.append((ct, imp, imb))
            elif c == "C":
                out.append((ct, self._custom[row] or None, "manual"))
        return out


def run_mapping_import(parent, db, data):
    """Kompletter Import-Ablauf ohne Datei-Dialog (intern#79): parsen,
    vergleichen, bei Konflikten klaeren lassen, in einer Transaktion
    schreiben. Neue Call-Texte werden ohne Rueckfrage uebernommen.

    Rueckgabe: Zusammenfassung (dict) oder None, wenn der Nutzer die
    Konfliktklaerung abbricht (dann wird nichts geschrieben). Wirft
    ValueError bei unbekanntem Format.
    """
    imported = mapping_io.parse_import(data)
    diff = db.diff_call_text_figures(imported)
    decisions = [(ct, figs, mb) for ct, figs, mb in diff["new"]]
    counts = {"A": 0, "B": 0, "C": 0}
    if diff["conflicts"]:
        from sequences_widget import picker_entities_from_to_calls
        to_calls = db.get_teaching_order_calls()
        entities, eid_to_label, _min_to = picker_entities_from_to_calls(to_calls)
        dlg = MappingConflictDialog(
            diff["conflicts"], entities, eid_to_label,
            suggest_fn=mapping_io.make_pattern_suggester(
                to_calls, db.get_all_call_text_figures()),
            unknown_fn=db.unknown_figures, parent=parent)
        if dlg.exec() != QDialog.Accepted:
            return None
        decisions += dlg.decisions()
        for c in dlg.choices():
            counts[c] += 1
    written = db.apply_call_text_figures_decisions(decisions) if decisions else 0
    return {
        "new": len(diff["new"]),
        "identical": len(diff["identical"]),
        "kept": counts["A"], "taken": counts["B"], "custom": counts["C"],
        "unknown_figures": diff["unknown_figures"],
        "skipped": diff["skipped"],
        "written": written,
    }
