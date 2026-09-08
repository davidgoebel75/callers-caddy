"""Preview-Dialog fuer den ZIP-Label-Import (BL-157).

Zeigt die vom Analyzer (zip_import.py) erkannten Song-Bundles und laesst den User
eingreifen, bevor importiert wird:
- Titel/Label/Typ je Bundle editierbar
- Musik-Liste per Drag&Drop sortierbar (oben = Hauptlied/Primaer), je Zeile mit
  editierbarer Bezeichnung der Variante
- Lyrics-Liste mit An-/Abwahl, Primaer-Wahl und editierbarer Bezeichnung
- Editor fuer die globale Abkuerzungs-Tabelle (Modifier -> Bezeichnung)
"""


from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QRadioButton, QButtonGroup, QPushButton, QDialogButtonBox, QGroupBox,
    QScrollArea, QWidget, QMessageBox, QTabWidget, QFileDialog,
    QAbstractSpinBox, QSlider,
)

import zip_import
from i18n import _t


class _ReorderTableWidget(QTableWidget):
    """QTableWidget mit robustem Zeilen-Drag&Drop (InternalMove ohne Loecher).

    Spalte 0 = Datei (read-only), Spalte 1 = editierbare Bezeichnung,
    Spalte 2 = Probehören (Item-Glyph, kein Cell-Widget → ueberlebt Reorder).
    Nach jedem Verschieben wird on_reorder() aufgerufen (Primaer-Markierung).
    """

    def __init__(self, parent=None):
        super().__init__(0, 3, parent)
        self.on_reorder = None
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDragDropOverwriteMode(False)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.DoubleClicked
                             | QAbstractItemView.SelectedClicked
                             | QAbstractItemView.EditKeyPressed)

    def dropEvent(self, event):
        if event.source() is not self:
            super().dropEvent(event)
            return
        sel = self.selectionModel().selectedRows()
        if not sel:
            event.ignore()
            return
        src = sel[0].row()
        pos = event.position().toPoint()
        idx = self.indexAt(pos)
        if idx.isValid():
            dst = idx.row()
            rect = self.visualRect(idx)
            if pos.y() > rect.center().y():
                dst += 1
        else:
            dst = self.rowCount()
        if dst > src:
            dst -= 1
        if dst == src:
            event.ignore()
            return
        cols = self.columnCount()
        row_items = [self.takeItem(src, c) for c in range(cols)]
        self.removeRow(src)
        self.insertRow(dst)
        for c in range(cols):
            self.setItem(dst, c, row_items[c])
        self.selectRow(dst)
        event.accept()
        if self.on_reorder:
            self.on_reorder()


def _readonly_item(text: str, data=None) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if data is not None:
        it.setData(Qt.UserRole, data)
    return it


def _editable_item(text: str) -> QTableWidgetItem:
    return QTableWidgetItem(text)


_PLAY_GLYPH = "▶"    # ▶
_PAUSE_GLYPH = "⏸"   # ⏸


def _play_item() -> QTableWidgetItem:
    it = QTableWidgetItem(_PLAY_GLYPH)
    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
    it.setTextAlignment(Qt.AlignCenter)
    return it


class _ListEditorWidget(QWidget):
    """Editor-Reiter fuer eine pflegbare Liste (Schluessel -> Wert).

    Zeigt die effektive Liste (Standard + User). Beim Speichern leitet der Dialog
    aus der sichtbaren Liste das Delta ab (siehe ManagedList.set_from_effective).
    """

    def __init__(self, managed, hint: str, col_key: str, col_val: str, parent=None):
        super().__init__(parent)
        self._managed = managed
        layout = QVBoxLayout(self)
        lbl = QLabel(hint)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels([col_key, col_val])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        self._fill(managed.effective())

        row = QHBoxLayout()
        b_add = QPushButton(_t("zip_lists_add"))
        b_del = QPushButton(_t("zip_lists_remove"))
        b_add.clicked.connect(lambda: self._add_row("", ""))
        b_del.clicked.connect(self._remove_selected)
        row.addWidget(b_add)
        row.addWidget(b_del)
        row.addStretch(1)
        layout.addLayout(row)

    def _fill(self, mapping: dict):
        self.table.setRowCount(0)
        for k, v in sorted(mapping.items()):
            if k == "":   # interner Leer-Token (Instrumental) nicht anzeigen
                continue
            self._add_row(k, v)

    def _add_row(self, key: str, val: str):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(key))
        self.table.setItem(r, 1, QTableWidgetItem(val))

    def _remove_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def effective_map(self) -> dict:
        out = {}
        for r in range(self.table.rowCount()):
            ki = self.table.item(r, 0)
            vi = self.table.item(r, 1)
            k = ki.text().strip() if ki else ""
            v = vi.text().strip() if vi else ""
            if not k and not v:
                continue
            out[k] = v
        return out

    def reset_defaults(self):
        self._fill(self._managed.defaults)

    def merge_other(self, other_eff: dict):
        cur = self.effective_map()
        cur.update(other_eff)
        self._fill(cur)

    def apply_to_managed(self):
        self._managed.set_from_effective(self.effective_map())


class ImportListsDialog(QDialog):
    """Pflege-Dialog fuer die vier Erkennungs-Listen (ein Fenster, vier Reiter)."""

    _TABS = (
        ("modifiers", "zip_lists_hint_modifiers", "zip_lists_h_abbr",
         "zip_lists_h_meaning", "zip_lists_tab_modifiers"),
        ("labels", "zip_lists_hint_labels", "zip_lists_h_label",
         "zip_lists_h_fullname", "zip_lists_tab_labels"),
        ("ignore", "zip_lists_hint_ignore", "zip_lists_h_pattern",
         "zip_lists_h_note", "zip_lists_tab_ignore"),
        ("roles", "zip_lists_hint_roles", "zip_lists_h_word",
         "zip_lists_h_role", "zip_lists_tab_roles"),
    )

    def __init__(self, lists, save_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("zip_lists_title"))
        self._lists = lists
        self._save_path = save_path
        self.resize(560, 480)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self._editors = {}
        for name, hint, ck, cv, tab in self._TABS:
            ml = getattr(lists, name)
            w = _ListEditorWidget(ml, _t(hint), _t(ck), _t(cv))
            self._editors[name] = w
            self.tabs.addTab(w, _t(tab))
        layout.addWidget(self.tabs)

        row = QHBoxLayout()
        b_imp = QPushButton(_t("zip_lists_import"))
        b_reset = QPushButton(_t("zip_lists_reset"))
        b_imp.clicked.connect(self._import_other)
        b_reset.clicked.connect(self._reset_current)
        row.addWidget(b_imp)
        row.addWidget(b_reset)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _reset_current(self):
        w = self.tabs.currentWidget()
        if isinstance(w, _ListEditorWidget):
            w.reset_defaults()

    def _import_other(self):
        fp, _sel = QFileDialog.getOpenFileName(
            self, _t("zip_lists_import"), "", "JSON (*.json)")
        if not fp:
            return
        try:
            other = zip_import.load_lists(fp)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, _t("zip_lists_title"),
                                _t("zip_lists_save_failed", error=str(e)))
            return
        n = 0
        for name, w in self._editors.items():
            before = len(w.effective_map())
            w.merge_other(getattr(other, name).effective())
            n += max(0, len(w.effective_map()) - before)
        QMessageBox.information(self, _t("zip_lists_title"),
                                _t("zip_lists_import_done", n=n))

    def _on_save(self):
        for w in self._editors.values():
            w.apply_to_managed()
        try:
            zip_import.save_lists(self._lists, self._save_path)
        except OSError as e:
            QMessageBox.warning(self, _t("zip_lists_title"),
                                _t("zip_lists_save_failed", error=str(e)))
            return
        self.accept()


class ZipImportPreviewDialog(QDialog):
    """Preview vor dem ZIP-Import: pro Bundle Titel/Label/Typ, Musik- und Lyrics-Liste."""

    def __init__(self, result, lists, lists_path: str, parent=None,
                 audition_cb=None):
        super().__init__(parent)
        self.setWindowTitle(_t("zip_preview_title"))
        self._result = result
        self._lists = lists
        self._lists_path = lists_path
        self._modmap = lists.modifiers.effective()
        self._audition_cb = audition_cb   # callable(path) -> 'playing'|'paused'
        self._bundles_ui = []
        self.resize(760, 640)

        outer = QVBoxLayout(self)
        intro = QLabel(_t("zip_preview_intro", count=len(result.bundles)))
        intro.setWordWrap(True)
        outer.addWidget(intro)
        # Vollstaendigkeits-Bilanz: jede Datei ist zugeordnet oder unten gelistet.
        balance = QLabel(_t("zip_preview_balance",
                            total=result.total_files,
                            assigned=result.assigned_count,
                            ignored=len(result.ignored)))
        balance.setWordWrap(True)
        balance.setStyleSheet("color: #888; font-size: 11px;")
        outer.addWidget(balance)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget()
        self._vbox = QVBoxLayout(container)
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        for bundle in result.bundles:
            self._vbox.addWidget(self._build_bundle(bundle))
        if result.ignored:
            box = QGroupBox(_t("zip_preview_others_title"))
            bl = QVBoxLayout(box)
            for name in result.ignored:
                reason = result.ignored_reasons.get(name, "")
                txt = f"• {name}  ({reason})" if reason else f"• {name}"
                row_lbl = QLabel(txt)
                row_lbl.setStyleSheet("color: #888;")
                bl.addWidget(row_lbl)
            self._vbox.addWidget(box)
        self._vbox.addStretch(1)

        bottom = QHBoxLayout()
        btn_mods = QPushButton(_t("zip_lists_button"))
        btn_mods.clicked.connect(self._edit_lists)
        bottom.addWidget(btn_mods)
        bottom.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(_t("zip_preview_import"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        bottom.addWidget(buttons)
        outer.addLayout(bottom)

        # Mausrad-Schutz auf Fenster-Ebene: alle Combos/SpinBoxes/Slider
        # ignorieren Wheel-Events, damit beim Scrollen durch den Dialog kein
        # Auswahlfeld (z. B. Songtyp) versehentlich verstellt wird. Gleiches
        # Muster wie im Settings-Dialog — auch zukuenftige Felder sind so
        # automatisch geschuetzt.
        for child in self.findChildren(QComboBox):
            child.installEventFilter(self)
        for child in self.findChildren(QAbstractSpinBox):
            child.installEventFilter(self)
        for child in self.findChildren(QSlider):
            child.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and isinstance(
                obj, (QComboBox, QAbstractSpinBox, QSlider)):
            event.ignore()
            return True
        return super().eventFilter(obj, event)

    def _build_bundle(self, bundle) -> QGroupBox:
        box = QGroupBox(bundle.title or bundle.base)
        v = QVBoxLayout(box)

        form = QFormLayout()
        edit_title = QLineEdit(bundle.title)
        edit_label = QLineEdit(bundle.label)
        combo_type = QComboBox()
        combo_type.addItems([_t("import_type_pattern"),
                             _t("import_type_singing"),
                             _t("import_type_both")])
        combo_type.setCurrentIndex(1)  # Default: Singing (Label-Pakete sind meist Singing Calls)
        form.addRow(_t("zip_preview_song_title"), edit_title)
        form.addRow(_t("zip_preview_label"), edit_label)
        form.addRow(_t("zip_preview_type"), combo_type)
        v.addLayout(form)

        # ---- Musik-Tabelle (Drag&Drop) ----
        v.addWidget(QLabel(_t("zip_preview_music_hint")))
        mp3 = _ReorderTableWidget()
        mp3.setHorizontalHeaderLabels(
            [_t("zip_preview_col_file"), _t("zip_preview_col_label"),
             _t("zip_preview_col_play")])
        mp3.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        mp3.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        mp3.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        for ac in bundle.audio:
            r = mp3.rowCount()
            mp3.insertRow(r)
            mp3.setItem(r, 0, _readonly_item(ac.filename, data=ac.path))
            mp3.setItem(r, 1, _editable_item(ac.label_text))
            mp3.setItem(r, 2, _play_item())
        mp3.setMinimumHeight(min(34 * max(mp3.rowCount(), 1) + 30, 200))
        mp3.on_reorder = lambda t=mp3: self._mark_primary(t)
        mp3.cellClicked.connect(
            lambda r, c, t=mp3: self._on_play_clicked(t, r, c))
        self._mark_primary(mp3)
        v.addWidget(mp3)

        # ---- Lyrics-Tabelle ----
        v.addWidget(QLabel(_t("zip_preview_lyrics_hint")))
        lyr = QTableWidget(0, 4)
        lyr.setHorizontalHeaderLabels([
            _t("zip_preview_col_import"), _t("zip_preview_col_primary"),
            _t("zip_preview_col_file"), _t("zip_preview_col_label")])
        lyr.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        lyr.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        lyr.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        lyr.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        lyr.verticalHeader().setVisible(False)
        radio_group = QButtonGroup(box)
        radio_group.setExclusive(True)
        radios = []
        for lc in bundle.lyrics:
            r = lyr.rowCount()
            lyr.insertRow(r)
            chk = QTableWidgetItem()
            chk.setFlags((chk.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            chk.setCheckState(Qt.Checked if lc.selected else Qt.Unchecked)
            lyr.setItem(r, 0, chk)
            radio = QRadioButton()
            radio.setChecked(lc.is_primary_suggested)
            radio_group.addButton(radio, r)
            radios.append(radio)
            lyr.setCellWidget(r, 1, radio)
            lyr.setItem(r, 2, _readonly_item(lc.filename, data=lc.path))
            lyr.setItem(r, 3, _editable_item(lc.label_text))
        lyr.setMinimumHeight(min(34 * max(lyr.rowCount(), 1) + 30, 180))
        v.addWidget(lyr)

        self._bundles_ui.append({
            "title": edit_title, "label": edit_label, "type": combo_type,
            "mp3": mp3, "lyr": lyr, "radios": radios,
        })
        return box

    def _mark_primary(self, table):
        """Hebt Zeile 0 (Hauptlied) optisch hervor."""
        for r in range(table.rowCount()):
            item = table.item(r, 0)
            if item is None:
                continue
            f = item.font()
            f.setBold(r == 0)
            item.setFont(f)
        if table.rowCount() and table.item(0, 1) is not None:
            # Primaer-Bezeichnung ist informativ; Default "Instrumental" stoert nicht.
            pass

    def _on_play_clicked(self, table, row, col):
        """Klick auf die Probehör-Spalte (2): Datei ueber den Hauptplayer anspielen."""
        if col != 2 or self._audition_cb is None:
            return
        item0 = table.item(row, 0)
        if item0 is None:
            return
        path = item0.data(Qt.UserRole)
        try:
            state = self._audition_cb(path)
        except Exception:
            state = "paused"
        self._reset_play_glyphs()
        play_item = table.item(row, 2)
        if play_item is not None:
            play_item.setText(_PAUSE_GLYPH if state == "playing" else _PLAY_GLYPH)

    def _reset_play_glyphs(self):
        """Setzt alle Probehör-Glyphen (Spalte 2) aller Bundles auf ▶ zurueck."""
        for ui in self._bundles_ui:
            t = ui["mp3"]
            for r in range(t.rowCount()):
                it = t.item(r, 2)
                if it is not None:
                    it.setText(_PLAY_GLYPH)

    def _edit_lists(self):
        dlg = ImportListsDialog(self._lists, self._lists_path, self)
        if dlg.exec() == QDialog.Accepted:
            # Aktualisierte Modifier fuer die Anzeige uebernehmen. Die geaenderten
            # Listen wirken voll beim naechsten Import (keine Re-Analyse noetig).
            self._modmap = self._lists.modifiers.effective()
            QMessageBox.information(self, _t("zip_lists_title"),
                                    _t("zip_lists_saved"))

    def get_decisions(self) -> list:
        """Liefert die finalen Import-Entscheidungen je Bundle."""
        out = []
        for ui in self._bundles_ui:
            ti = ui["type"].currentIndex()
            is_pattern = 1 if ti in (0, 2) else 0
            is_singing = 1 if ti in (1, 2) else 0

            audio = []
            for r in range(ui["mp3"].rowCount()):
                path = ui["mp3"].item(r, 0).data(Qt.UserRole)
                name = ui["mp3"].item(r, 1).text().strip()
                audio.append({"path": path, "label_text": name})

            lyrics = []
            for r in range(ui["lyr"].rowCount()):
                selected = ui["lyr"].item(r, 0).checkState() == Qt.Checked
                is_primary = ui["radios"][r].isChecked()
                path = ui["lyr"].item(r, 2).data(Qt.UserRole)
                name = ui["lyr"].item(r, 3).text().strip()
                lyrics.append({"path": path, "selected": selected,
                               "is_primary": is_primary, "label_text": name})

            out.append({
                "title": ui["title"].text().strip(),
                "label": ui["label"].text().strip(),
                "is_pattern": is_pattern, "is_singing": is_singing,
                "audio": audio, "lyrics": lyrics,
            })
        return out
