"""Dialoge fuer Lokation, Tanzprogramm und Genre (BL-201, Stufe 12).

Lokations-, Programm- und Genre-Verwaltungs-/Auswahl-Dialoge plus der
Deduplizierungs-Dialog. Zirkelfrei: keine Rueckbezuege auf main.py.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QGroupBox, QCheckBox, QLineEdit, QSpinBox, QDoubleSpinBox, QFormLayout,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QDialog, QDialogButtonBox, QInputDialog,
    QAbstractItemView, QRadioButton, QButtonGroup, QTimeEdit,
)
from PySide6.QtCore import Qt, QTime

from song_db import SongDatabase, Location
from i18n import _t
import program_selection
from ui_helpers import _make_icon, _SVG_REMOVE_X


class LocationDialog(QDialog):
    """Dialog zur Lokation-Auswahl und -Verwaltung.

    Features:
    - Liste aller Lokationen (alphabetisch)
    - Suchfeld ueber der Liste (enthaelt-Suche, X leert die Eingabe)
    - '+' Button zum Hinzufuegen neuer Lokationen (Inline-Eingabe)
    - Doppelklick auf Lokation = uebernehmen und Dialog schliessen
    - Umbenennen per Button
    - Entfernen-Button zum Loeschen
    - OK/Abbrechen (OK liefert die gewaehlte Lokation)
    - "Keine Lokation" Button zum Abwaehlen
    """

    def __init__(self, db: SongDatabase, current_location_id=None, parent=None):
        super().__init__(parent)
        self.db = db
        self._selected_location: Location = None
        self._current_location_id = current_location_id
        self.setWindowTitle(_t("dialog_location_title"))
        self.setMinimumSize(350, 400)
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Anleitung
        info = QLabel(_t("dialog_location_info"))
        info.setObjectName("label_dim")
        layout.addWidget(info)

        # Suchfeld: 'enthaelt'-Suche ueber den angezeigten Text.
        # setClearButtonEnabled liefert das X zum Leeren mit — gleiches
        # Verhalten wie im Song-Suchfeld der SongFilterBar.
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText(_t("loc_search_placeholder"))
        self.edit_search.setClearButtonEnabled(True)
        self.edit_search.textChanged.connect(self._apply_filter)
        layout.addWidget(self.edit_search)

        # Lokation-Liste
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        self.list_widget.currentItemChanged.connect(self._on_current_changed)
        layout.addWidget(self.list_widget)

        # Buttons: + Hinzufuegen | Umbenennen | Loeschen
        btn_row = QHBoxLayout()

        self.btn_add = QPushButton(_t("btn_new_location"))
        self.btn_add.setToolTip(_t("tooltip_new_location"))
        self.btn_add.clicked.connect(self._on_add)
        btn_row.addWidget(self.btn_add)

        # BL-178 P2: Unter-Lokation (uebernimmt Einstellungen + teilt Historie)
        self.btn_add_sub = QPushButton(_t("btn_new_sub_location"))
        self.btn_add_sub.setToolTip(_t("tooltip_new_sub_location"))
        self.btn_add_sub.setEnabled(False)
        self.btn_add_sub.clicked.connect(self._on_add_sub)
        btn_row.addWidget(self.btn_add_sub)

        self.btn_rename = QPushButton(_t("btn_rename"))
        self.btn_rename.setToolTip(_t("tooltip_rename"))
        self.btn_rename.setEnabled(False)
        self.btn_rename.clicked.connect(self._on_rename_btn)
        btn_row.addWidget(self.btn_rename)

        self.btn_delete = QPushButton(_t("btn_delete"))
        self.btn_delete.setToolTip(_t("tooltip_delete"))
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self.btn_delete)

        self.btn_settings = QPushButton(_t("loc_btn_settings"))
        self.btn_settings.setToolTip(_t("loc_btn_settings_tooltip"))
        self.btn_settings.setEnabled(False)
        self.btn_settings.clicked.connect(self._on_settings)
        btn_row.addWidget(self.btn_settings)

        layout.addLayout(btn_row)

        # Dialog-Buttons
        btn_box_layout = QHBoxLayout()

        self.btn_no_location = QPushButton(_t("btn_no_location"))
        self.btn_no_location.setToolTip(_t("tooltip_no_location"))
        self.btn_no_location.clicked.connect(self._on_no_location)
        btn_box_layout.addWidget(self.btn_no_location)

        btn_box_layout.addStretch()

        self.btn_ok = QPushButton(_t("btn_ok"))
        self.btn_ok.setEnabled(False)
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.accept)
        btn_box_layout.addWidget(self.btn_ok)

        btn_cancel = QPushButton(_t("btn_cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_box_layout.addWidget(btn_cancel)

        layout.addLayout(btn_box_layout)

    def _refresh_list(self):
        """Laedt alle Lokationen neu in die Liste."""
        # Die Liste hat sich geaendert — Filter zuruecknehmen. Sonst kann ein
        # neu angelegter Eintrag versteckt sein, waehrend ihn der Aufrufer
        # gleich darauf selektiert (unsichtbare Auswahl mit aktivem OK).
        self.edit_search.clear()
        self.list_widget.clear()
        locations = self.db.get_all_locations()
        # BL-178 P2: Namensauflösung fuer die "teilt Historie mit"-Kennzeichnung
        name_by_id = {l.id: l.name for l in locations}
        for loc in locations:
            label = loc.name
            if loc.shared_history_with and loc.shared_history_with in name_by_id:
                label = f"{loc.name}  →  {name_by_id[loc.shared_history_with]}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, loc.id)
            self.list_widget.addItem(item)
            # Aktuelle Lokation vorselektieren
            if self._current_location_id and loc.id == self._current_location_id:
                item.setSelected(True)
                self.list_widget.setCurrentItem(item)
                self._selected_location = loc
                self.btn_ok.setEnabled(True)
                self.btn_rename.setEnabled(True)
                self.btn_delete.setEnabled(True)
                self.btn_settings.setEnabled(True)
                self.btn_add_sub.setEnabled(True)
        # Fokus-Steuerung: Liste oder Neu-Button
        if self.list_widget.count() > 0:
            self.list_widget.setFocus()
            if not self.list_widget.currentItem():
                self.list_widget.setCurrentRow(0)
                self._on_item_clicked(self.list_widget.item(0))
        else:
            self.btn_add.setFocus()

    def _apply_filter(self):
        """Blendet Eintraege aus, die den Suchtext nicht enthalten."""
        text = self.edit_search.text().strip().lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(bool(text) and text not in item.text().lower())
        # Eine ausgeblendete Auswahl bliebe aktiv, waere aber unsichtbar —
        # Loeschen/Umbenennen wuerden dann eine Lokation treffen, die der
        # Nutzer gar nicht sieht.
        current = self.list_widget.currentItem()
        if current is not None and current.isHidden():
            self.list_widget.setCurrentItem(None)
            self._selected_location = None
            self.btn_ok.setEnabled(False)
            self.btn_rename.setEnabled(False)
            self.btn_delete.setEnabled(False)
            self.btn_settings.setEnabled(False)
            self.btn_add_sub.setEnabled(False)

    def _on_current_changed(self, current, previous):
        """Pfeiltasten-Navigation: Auswahl bei Cursor-Wechsel aktualisieren."""
        if current:
            self._on_item_clicked(current)

    def _on_item_clicked(self, item):
        loc_id = item.data(Qt.UserRole)
        locations = self.db.get_all_locations()
        for loc in locations:
            if loc.id == loc_id:
                self._selected_location = loc
                break
        self.btn_ok.setEnabled(True)
        self.btn_rename.setEnabled(True)
        self.btn_delete.setEnabled(True)
        self.btn_settings.setEnabled(True)
        self.btn_add_sub.setEnabled(True)

    def _on_add(self):
        """Neue Lokation per Eingabedialog anlegen."""
        name, ok = QInputDialog.getText(
            self, _t("dialog_new_location"), _t("dialog_new_location_prompt"),
            QLineEdit.Normal, ""
        )
        if ok and name.strip():
            name = name.strip()
            try:
                loc = self.db.insert_location(name)
                self._refresh_list()
                # Neu angelegte Lokation selektieren
                for i in range(self.list_widget.count()):
                    item = self.list_widget.item(i)
                    if item.data(Qt.UserRole) == loc.id:
                        self.list_widget.setCurrentItem(item)
                        self._selected_location = loc
                        self.btn_ok.setEnabled(True)
                        self.btn_rename.setEnabled(True)
                        self.btn_delete.setEnabled(True)
                        self.btn_settings.setEnabled(True)
                        self.btn_add_sub.setEnabled(True)
                        break
            except Exception as e:
                QMessageBox.warning(
                    self, _t("error"),
                    _t("error_create_location", error=e)
                )

    def _on_double_click(self, item):
        """Doppelklick auf Lokation = sofort uebernehmen und Dialog schliessen."""
        loc_id = item.data(Qt.UserRole)
        locations = self.db.get_all_locations()
        for loc in locations:
            if loc.id == loc_id:
                self._selected_location = loc
                break
        self.accept()

    def _on_rename_btn(self):
        """Umbenennen per Button (delegiert an rename-Logik)."""
        current = self.list_widget.currentItem()
        if current:
            self._on_rename(current)

    def _on_rename(self, item=None):
        """Lokation umbenennen per Button."""
        if item is None:
            item = self.list_widget.currentItem()
        if not item:
            return

        loc_id = item.data(Qt.UserRole)
        old_name = item.text()

        new_name, ok = QInputDialog.getText(
            self, _t("dialog_rename_location"), _t("dialog_rename_prompt"),
            QLineEdit.Normal, old_name
        )
        if ok and new_name.strip() and new_name.strip() != old_name:
            try:
                loc = Location(id=loc_id, name=new_name.strip())
                self.db.update_location(loc)
                self._refresh_list()
                self._selected_location = loc
            except Exception as e:
                QMessageBox.warning(
                    self, _t("error"),
                    _t("error_rename", error=e)
                )

    def _on_delete(self):
        """Ausgewaehlte Lokation loeschen mit Nachfrage und History-Option."""
        current = self.list_widget.currentItem()
        if not current:
            return

        loc_name = current.text()
        loc_id = current.data(Qt.UserRole)

        # Eigener Dialog mit Checkbox
        msg = QMessageBox(self)
        msg.setWindowTitle(_t("dialog_delete_location"))
        msg.setText(_t("confirm_delete_location", name=loc_name))
        msg.setIcon(QMessageBox.Question)
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)

        chk_history = QCheckBox(_t("delete_location_history"))
        msg.setCheckBox(chk_history)

        if msg.exec() == QMessageBox.Yes:
            delete_history = chk_history.isChecked()
            try:
                self.db.delete_location(loc_id, delete_history=delete_history)
                self._selected_location = None
                self.btn_ok.setEnabled(False)
                self.btn_rename.setEnabled(False)
                self.btn_delete.setEnabled(False)
                self.btn_settings.setEnabled(False)
                self._refresh_list()
            except Exception as e:
                QMessageBox.warning(
                    self, _t("error"),
                    str(e)
                )

    def _on_settings(self):
        """Oeffnet den Einstellungs-Dialog fuer die selektierte Lokation.

        BL-178 P2: Klickt der Nutzer im Dialog eine verknuepfte Lokation an, wird
        gespeichert und der Dialog fuer die Ziel-Lokation erneut geoeffnet
        (Schleife), damit man verlustfrei durch die History-Gruppe navigieren kann.
        """
        loc = self._selected_location
        if not loc:
            return
        last_id = loc.id
        while loc is not None:
            last_id = loc.id
            dlg = _LocationSettingsDialog(self.db, loc, parent=self)
            if dlg.exec() != QDialog.Accepted:
                break
            (dp_id, temp_tempo, planned_tips, break_minutes,
             target_bpm, tempo_mode, schedules) = dlg.get_values()
            self.db.update_location_settings(loc.id, dp_id, temp_tempo,
                                             planned_tips, break_minutes,
                                             target_bpm=target_bpm,
                                             tempo_mode=tempo_mode,
                                             schedules=schedules)
            # MS50: Mehrfach-Programmzuordnung speichern (aktualisiert auch den
            # Kompat-Spiegel dance_program_id).
            self.db.set_location_program_ids(loc.id, dlg.get_program_ids())
            switch_id = getattr(dlg, "_switch_to_location_id", None)
            if switch_id is None:
                loc = None
            else:
                # Zur verknuepften Lokation wechseln (frisch aus DB laden).
                last_id = switch_id
                loc = next((l for l in self.db.get_all_locations()
                            if l.id == switch_id), None)
        # Selektion frisch aus DB nachziehen (Settings/Share koennten sich
        # geaendert haben), damit das OK des Hauptdialogs die neuen Werte hat.
        reloaded = next((l for l in self.db.get_all_locations()
                         if l.id == last_id), None)
        if reloaded is not None:
            self._selected_location = reloaded
            self._current_location_id = reloaded.id
        self._refresh_list()

    def _on_add_sub(self):
        """BL-178 P2: Legt eine Unter-Lokation an (uebernimmt Einstellungen +
        Termine der gewaehlten Lokation und teilt deren Historie)."""
        loc = self._selected_location
        if not loc:
            return
        name, ok = QInputDialog.getText(
            self, _t("loc_sub_title"), _t("loc_sub_prompt"),
            QLineEdit.Normal, "")
        if not (ok and name.strip()):
            return
        try:
            new_loc = self.db.create_sub_location(loc.id, name.strip())
        except Exception as e:
            QMessageBox.warning(self, _t("loc_sub_title"),
                                _t("error_create_location", error=e))
            return
        self._selected_location = new_loc
        self._current_location_id = new_loc.id
        self._refresh_list()

    def _on_no_location(self):
        """Lokation-Zuordnung aufheben."""
        self._selected_location = None
        self.accept()

    def get_selected_location(self) -> Location:
        """Gibt die gewaehlte Lokation zurueck (oder None)."""
        return self._selected_location


class DeduplicationDialog(QDialog):
    """Dialog zur Erkennung und Entfernung exakter Sequenz-Duplikate.

    Zeigt Statistiken (Gesamtzahl, Duplikat-Gruppen, zu loeschende Zeilen)
    und erlaubt dem User, die Bereinigung explizit auszuloesen.
    """

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._deleted = 0
        self.setWindowTitle(_t("dedup_title"))
        self.setMinimumWidth(420)
        self.setModal(True)
        self._build_ui()
        self._refresh_stats()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Statistik-Box
        box = QGroupBox(_t("dedup_stats_group"))
        box_layout = QFormLayout(box)
        box_layout.setRowWrapPolicy(QFormLayout.DontWrapRows)

        self._lbl_total  = QLabel("—")
        self._lbl_groups = QLabel("—")
        self._lbl_delete = QLabel("—")
        self._lbl_delete.setStyleSheet("font-weight: bold;")

        box_layout.addRow(_t("dedup_stat_total"),  self._lbl_total)
        box_layout.addRow(_t("dedup_stat_groups"), self._lbl_groups)
        box_layout.addRow(_t("dedup_stat_delete"), self._lbl_delete)
        layout.addWidget(box)

        # Hinweis
        hint = QLabel(_t("dedup_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(hint)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_clean = QPushButton(_t("dedup_btn_clean"))
        self._btn_clean.setStyleSheet("font-weight: bold;")
        self._btn_clean.clicked.connect(self._on_clean)
        btn_row.addWidget(self._btn_clean)
        btn_row.addStretch()
        btn_close = QPushButton(_t("btn_close"))
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _refresh_stats(self):
        total, groups, to_delete = self.db.count_duplicate_sequences()
        self._lbl_total.setText(str(total))
        self._lbl_groups.setText(str(groups))
        self._lbl_delete.setText(str(to_delete))
        self._btn_clean.setEnabled(to_delete > 0)

    def _on_clean(self):
        total, groups, to_delete = self.db.count_duplicate_sequences()
        if to_delete == 0:
            QMessageBox.information(self, _t("dedup_title"), _t("dedup_none_found"))
            return

        reply = QMessageBox.warning(
            self, _t("dedup_confirm_title"),
            _t("dedup_confirm_msg", groups=groups, to_delete=to_delete),
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel
        )
        if reply != QMessageBox.Ok:
            return

        self._deleted = self.db.remove_duplicate_sequences()
        QMessageBox.information(
            self, _t("dedup_title"),
            _t("dedup_done", deleted=self._deleted)
        )
        self._refresh_stats()

    def deleted_count(self) -> int:
        return self._deleted


class _ImportGenreDialog(QDialog):
    """BL-184: Genre-Zuweisung fuer einen kompletten Ordner-Import.

    Zeigt eine Haekchen-Liste der vorhandenen Genres. Die angehakten Genres
    werden allen importierten Songs des Ordners additiv zugewiesen (analog zum
    automatischen "NEW"-Tag). Ganz unten ein Freitextfeld, um ein neues Genre
    on-the-fly anzulegen — mit Pruefung, ob es (case-insensitive) schon
    existiert; existiert es, wird das vorhandene nur angehakt statt ein
    Duplikat anzulegen.

    Besonderheiten:
    - Das "NEW"-Genre ist eingeblendet und vorangehakt (jeder neue Song
      bekommt es ohnehin). Haekt der Nutzer es AUS, wird es beim Import wieder
      entfernt (siehe _import_files).
    - "CHECK:"-Marker (To-Do-Marker der Auto-Analyse) werden nicht angezeigt.
    """

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(_t("import_genre_title"))
        self.setMinimumWidth(340)
        self.setMinimumHeight(440)

        layout = QVBoxLayout(self)

        lbl = QLabel(_t("import_genre_hint"))
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.NoSelection)
        for gid, gname in db.get_all_genres():
            # CHECK:-Marker ausblenden — die setzt nur die Auto-Analyse.
            if gname.startswith("CHECK:"):
                continue
            item = QListWidgetItem(gname)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            # NEW ist standardmaessig angehakt (bekommt ohnehin jeder Song).
            precheck = (gname == "NEW")
            item.setCheckState(Qt.Checked if precheck else Qt.Unchecked)
            item.setData(Qt.UserRole, gid)
            self._list.addItem(item)
        layout.addWidget(self._list)

        # Neues Genre on-the-fly anlegen
        new_row = QHBoxLayout()
        new_row.addWidget(QLabel(_t("genre_add_new")))
        self._edit_new = QLineEdit()
        self._edit_new.setPlaceholderText(_t("genre_add_placeholder"))
        self._edit_new.returnPressed.connect(self._add_new_genre)
        new_row.addWidget(self._edit_new, 1)
        btn_plus = QPushButton("+")
        btn_plus.setFixedWidth(28)
        btn_plus.clicked.connect(self._add_new_genre)
        new_row.addWidget(btn_plus)
        layout.addLayout(new_row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _add_new_genre(self):
        name = self._edit_new.text().strip()
        if not name:
            return
        # Existiert das Genre schon (case-insensitive)? Dann kein Duplikat
        # anlegen — vorhandenes anhaken bzw. Hinweis geben.
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.text().lower() == name.lower():
                item.setCheckState(Qt.Checked)
                self._list.scrollToItem(item)
                self._edit_new.clear()
                return
        # Auch gegen ausgeblendete Genres pruefen (z.B. CHECK:-Marker),
        # damit die UNIQUE-Spalte nicht ins Leere laeuft.
        if self.db.get_genre_id_by_name(name) > 0 or any(
                gname.lower() == name.lower()
                for _gid, gname in self.db.get_all_genres()):
            QMessageBox.information(
                self, _t("import_genre_title"),
                _t("genre_exists_msg", name=name))
            return
        # Neu anlegen
        gid = self.db.insert_genre(name)
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        item.setData(Qt.UserRole, gid)
        self._list.addItem(item)
        self._list.scrollToItem(item)
        self._edit_new.clear()

    def selected_genre_ids(self) -> list:
        result = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.Checked:
                result.append(item.data(Qt.UserRole))
        return result


class _LocationSettingsDialog(QDialog):
    """Einstellungs-Dialog fuer eine Lokation: Tanzprogramm + Tempo + geplante Tips."""

    # BL-144: Vorbelegung, wenn noch nie eine Ziel-BPM gesetzt wurde.
    # 128 BPM ist das uebliche Square-Dance-Tempo — 0 waere unbrauchbar.
    DEFAULT_TARGET_BPM = 128
    # Plausibler Bereich; ausserhalb kommt eine Rueckfrage (Tippfehler-Schutz)
    PLAUSIBLE_BPM = (100, 150)

    def __init__(self, db, location: "Location", parent=None):
        super().__init__(parent)
        self.db = db
        self._location = location
        # MS50: Lokation kann MEHRERE Programme haben. Liste aus location_programs
        # laden; Fallback auf das alte Einzelprogramm (dance_program_id).
        self._dance_program_ids = []
        if getattr(location, "id", None) is not None:
            self._dance_program_ids = list(db.get_location_program_ids(location.id))
        if not self._dance_program_ids and location.dance_program_id is not None:
            self._dance_program_ids = [location.dance_program_id]
        # Kompat: erstes Programm gilt als "das" dance_program_id
        self._dance_program_id = (self._dance_program_ids[0]
                                  if self._dance_program_ids else None)
        self.setWindowTitle(_t("loc_settings_title", name=location.name))
        # BL-178: Mindestbreite so, dass die Termin-Zeile (Wochentag + zwei
        # Zeitfelder + Entfernen) komplett hineinpasst. Endgueltige Groesse
        # wird am Ende von __init__ per adjustSize() aus dem Layout berechnet.
        self.setMinimumWidth(420)

        layout = QFormLayout(self)
        layout.setRowWrapPolicy(QFormLayout.DontWrapRows)

        # --- Tanzprogramm(e) (MS50: Mehrfachauswahl) ---
        prog_row = QHBoxLayout()
        self._lbl_program = QLabel("")
        self._lbl_program.setMinimumWidth(90)
        self._lbl_program.setWordWrap(True)
        self._refresh_program_label()
        prog_row.addWidget(self._lbl_program, 1)
        btn_pick = QPushButton(_t("loc_settings_btn_choose"))
        btn_pick.clicked.connect(self._on_pick_program)
        prog_row.addWidget(btn_pick)
        btn_clear_prog = QPushButton(_t("loc_settings_btn_clear"))
        btn_clear_prog.clicked.connect(self._on_clear_program)
        prog_row.addWidget(btn_clear_prog)
        prog_row.addStretch()
        layout.addRow(_t("loc_settings_lbl_program"), prog_row)

        # --- Temporaeres Tempo (BL-086) ---
        # BL-144: Radio waehlt, welcher der beiden Werte gilt. Beide Zahlen
        # bleiben gespeichert, damit das Umschalten nichts ueberschreibt.
        tempo_row = QHBoxLayout()
        self._radio_percent = QRadioButton()
        self._radio_percent.setToolTip(_t("loc_settings_tip_tempo"))
        tempo_row.addWidget(self._radio_percent)
        self._spin_tempo = QSpinBox()
        self._spin_tempo.setRange(50, 150)
        self._spin_tempo.setSuffix(" %")
        self._spin_tempo.setValue(int(location.temp_tempo) if location.temp_tempo is not None else 100)
        self._spin_tempo.setToolTip(_t("loc_settings_tip_tempo"))
        tempo_row.addWidget(self._spin_tempo)
        tempo_row.addStretch()
        layout.addRow(_t("loc_settings_lbl_tempo"), tempo_row)

        # --- BL-144: Ziel-BPM ---
        bpm_row = QHBoxLayout()
        self._radio_bpm = QRadioButton()
        self._radio_bpm.setToolTip(_t("loc_settings_tip_target_bpm"))
        bpm_row.addWidget(self._radio_bpm)
        self._spin_target_bpm = QSpinBox()
        self._spin_target_bpm.setRange(0, 200)
        self._spin_target_bpm.setSpecialValueText(_t("loc_settings_bpm_none"))
        self._spin_target_bpm.setSuffix(" BPM")
        # Noch nie gesetzt: mit einem realistischen Square-Dance-Tempo vorbelegen
        self._spin_target_bpm.setValue(int(location.target_bpm)
                                       if location.target_bpm
                                       else self.DEFAULT_TARGET_BPM)
        self._spin_target_bpm.setToolTip(_t("loc_settings_tip_target_bpm"))
        bpm_row.addWidget(self._spin_target_bpm)
        bpm_row.addStretch()
        layout.addRow(_t("loc_settings_lbl_target_bpm"), bpm_row)

        # Radios gruppieren und auf den gespeicherten Modus setzen
        self._tempo_mode_group = QButtonGroup(self)
        self._tempo_mode_group.addButton(self._radio_percent)
        self._tempo_mode_group.addButton(self._radio_bpm)
        if location.effective_tempo_mode == Location.TEMPO_MODE_BPM:
            self._radio_bpm.setChecked(True)
        else:
            self._radio_percent.setChecked(True)
        self._radio_percent.toggled.connect(self._sync_tempo_fields)
        self._sync_tempo_fields()

        # --- Geplante Anzahl Tips ---
        tips_row = QHBoxLayout()
        self._spin_tips = QSpinBox()
        self._spin_tips.setRange(0, 40)
        self._spin_tips.setSpecialValueText(_t("loc_settings_tips_none"))
        self._spin_tips.setSuffix(_t("loc_settings_tips_suffix"))
        self._spin_tips.setValue(location.planned_tips if location.planned_tips else 0)
        tips_row.addWidget(self._spin_tips)
        tips_row.addStretch()
        layout.addRow(_t("loc_settings_lbl_tips"), tips_row)

        # --- Standard-Pausendauer (Minuten) ---
        break_row = QHBoxLayout()
        self._spin_break = QSpinBox()
        self._spin_break.setRange(1, 60)
        self._spin_break.setSuffix(_t("loc_settings_break_suffix"))
        self._spin_break.setValue(location.break_minutes
                                  if location.break_minutes
                                  else Location.DEFAULT_BREAK_MINUTES)
        break_row.addWidget(self._spin_break)
        break_row.addStretch()
        layout.addRow(_t("loc_settings_lbl_break"), break_row)

        # --- BL-178: Termine (mehrere Wochentag/Uhrzeit-Tripel) fuer die
        # Start-Auto-Erkennung. Eine Lokation kann an verschiedenen Tagen zu
        # verschiedenen Zeiten tanzen. Keine Zeile = terminlos (Erkennung
        # ignoriert die Lokation dann). Jede Zeile: Wochentag + Von-/Bis-Zeit + ✕.
        self._schedule_rows = []          # Liste dicts {combo, from, to, widget}
        sched_outer = QWidget()
        sched_vouter = QVBoxLayout(sched_outer)
        sched_vouter.setContentsMargins(0, 0, 0, 0)
        sched_vouter.setSpacing(4)
        rows_container = QWidget()
        self._sched_vbox = QVBoxLayout(rows_container)
        self._sched_vbox.setContentsMargins(0, 0, 0, 0)
        self._sched_vbox.setSpacing(4)
        sched_vouter.addWidget(rows_container)
        btn_add_sched = QPushButton(_t("loc_settings_btn_add_schedule"))
        btn_add_sched.clicked.connect(lambda: self._add_schedule_row())
        sched_vouter.addWidget(btn_add_sched, 0, Qt.AlignLeft)
        layout.addRow(_t("loc_settings_lbl_schedule"), sched_outer)
        # Vorhandene Termine vorbefuellen (inkl. Alt-Fallback aus schedule_list)
        for (wd, tf, tt) in location.schedule_list:
            self._add_schedule_row(wd, tf, tt)

        # --- BL-178 P2: Shared History ---
        self._switch_to_location_id = None      # gesetzt bei Klick auf verknuepfte Lok.
        self._shared_with_id = location.shared_history_with
        share_row = QHBoxLayout()
        self._lbl_shared = QLabel()
        share_row.addWidget(self._lbl_shared)
        btn_share = QPushButton(_t("loc_share_choose"))
        btn_share.clicked.connect(self._on_choose_share)
        share_row.addWidget(btn_share)
        self._btn_unshare = QPushButton(_t("loc_share_clear"))
        self._btn_unshare.clicked.connect(self._on_clear_share)
        share_row.addWidget(self._btn_unshare)
        share_row.addStretch()
        layout.addRow(_t("loc_share_label"), share_row)

        # Gruppe der verknuepften Lokationen (Transparenz + Direktwechsel)
        self._group_container = QWidget()
        self._group_vbox = QVBoxLayout(self._group_container)
        self._group_vbox.setContentsMargins(0, 0, 0, 0)
        self._group_vbox.setSpacing(2)
        self._group_row_label = QLabel(_t("loc_group_label"))
        layout.addRow(self._group_row_label, self._group_container)
        self._refresh_share_ui()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

        # BL-178: Benoetigte Fenstergroesse aus dem fertig aufgebauten Layout
        # berechnen (statt einer festen Groesse) — sonst reicht die Hoehe bei
        # mehreren Terminen nicht.
        self.adjustSize()

    def _add_schedule_row(self, wd=None, tf=None, tt=None):
        """BL-178: Fuegt der Termin-Liste eine Zeile hinzu (Wochentag + Zeiten)."""
        row_w = QWidget()
        h = QHBoxLayout(row_w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        combo = QComboBox()
        for d in range(1, 8):  # 1=Mo .. 7=So
            combo.addItem(_t(f"wd_short_{d}"), d)
        if wd and 1 <= int(wd) <= 7:
            combo.setCurrentIndex(int(wd) - 1)
        h.addWidget(combo)
        t_from = QTimeEdit()
        t_from.setDisplayFormat("HH:mm")
        t_from.setTime(self._parse_time(tf, QTime(19, 30)))
        h.addWidget(t_from)
        h.addWidget(QLabel(_t("loc_settings_lbl_time_to")))
        t_to = QTimeEdit()
        t_to.setDisplayFormat("HH:mm")
        t_to.setTime(self._parse_time(tt, QTime(22, 0)))
        h.addWidget(t_to)
        btn_rm = QPushButton()
        btn_rm.setIcon(_make_icon(_SVG_REMOVE_X, "#999999"))
        btn_rm.setFixedWidth(32)
        btn_rm.setToolTip(_t("loc_settings_btn_remove_schedule"))
        h.addWidget(btn_rm)
        h.addStretch()
        entry = {"combo": combo, "from": t_from, "to": t_to, "widget": row_w}

        def _remove():
            if entry in self._schedule_rows:
                self._schedule_rows.remove(entry)
            self._sched_vbox.removeWidget(row_w)
            row_w.deleteLater()
        btn_rm.clicked.connect(_remove)
        self._schedule_rows.append(entry)
        self._sched_vbox.addWidget(row_w)

    # ---- BL-178 P2: Shared History ----

    def _refresh_share_ui(self):
        """Aktualisiert das 'teilt mit'-Label und die Gruppen-Liste."""
        target_name = ""
        if self._shared_with_id:
            for l in self.db.get_all_locations():
                if l.id == self._shared_with_id:
                    target_name = l.name
                    break
        self._lbl_shared.setText(target_name or _t("loc_share_none"))
        self._btn_unshare.setEnabled(bool(self._shared_with_id))
        # Gruppen-Liste neu aufbauen
        while self._group_vbox.count():
            it = self._group_vbox.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        sink, group = self.db.get_history_group(self._location.id)
        show = len(group) > 1
        self._group_container.setVisible(show)
        self._group_row_label.setVisible(show)
        if not show:
            return
        for (lid, lname) in group:
            lbl = QLabel()
            lbl.setTextFormat(Qt.RichText)
            lbl.setOpenExternalLinks(False)
            disp = f"<b><u>{lname}</u></b>" if lid == sink else lname
            if lid == self._location.id:
                # aktuelle Lokation: nicht klickbar, markiert
                lbl.setText(f"{disp} {_t('loc_group_current')}")
            else:
                lbl.setText(f'<a href="{lid}">{disp}</a>')
                lbl.linkActivated.connect(self._on_switch_location)
            self._group_vbox.addWidget(lbl)

    def _on_choose_share(self):
        """Waehlt eine Ziel-Lokation und teilt die Historie mit deren Senke."""
        others = [(l.id, l.name) for l in self.db.get_all_locations()
                  if l.id != self._location.id]
        if not others:
            QMessageBox.information(self, _t("loc_share_label"),
                                    _t("loc_share_no_others"))
            return
        names = [n for _, n in others]
        choice, ok = QInputDialog.getItem(
            self, _t("loc_share_label"), _t("loc_share_pick"), names, 0, False)
        if not (ok and choice):
            return
        target_id = next(i for i, n in others if n == choice)
        cnt = self.db.count_history_entries(self._location.id)
        if cnt:
            r = QMessageBox.question(
                self, _t("loc_share_label"),
                _t("loc_share_migrate_confirm", count=str(cnt), name=choice),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if r != QMessageBox.Yes:
                return
        self.db.set_shared_history(self._location.id, target_id, migrate=True)
        eff, _group = self.db.get_history_group(self._location.id)
        self._shared_with_id = eff if eff != self._location.id else None
        self._refresh_share_ui()

    def _on_clear_share(self):
        """Trennt die Historie-Verknuepfung (bereits umgezogene Plays bleiben
        in der bisherigen Senke — bewusst einfach gehalten)."""
        self.db.set_shared_history(self._location.id, None)
        self._shared_with_id = None
        self._refresh_share_ui()

    def _on_switch_location(self, href):
        """Klick auf eine verknuepfte Lokation: speichern + zu ihr wechseln."""
        try:
            self._switch_to_location_id = int(href)
        except (ValueError, TypeError):
            return
        # Ueber die normale OK-Logik speichern und schliessen (inkl. BPM-Check).
        self._on_accept()

    def _on_accept(self):
        """BL-144: Ziel-BPM vor dem Speichern plausibilisieren.

        Ein Tippfehler (13 statt 130) wuerde jeden Song ans Tempo-Limit fahren,
        ohne dass die Ursache erkennbar ist — deshalb hier eine Rueckfrage.
        """
        if self._radio_bpm.isChecked():
            bpm = self._spin_target_bpm.value()
            lo, hi = self.PLAUSIBLE_BPM
            if bpm <= 0:
                QMessageBox.warning(self, _t("loc_settings_title", name=self._location.name),
                                    _t("loc_settings_bpm_zero"))
                self._spin_target_bpm.setFocus()
                self._spin_target_bpm.selectAll()
                return
            if bpm < lo or bpm > hi:
                reply = QMessageBox.question(
                    self, _t("loc_settings_title", name=self._location.name),
                    _t("loc_settings_bpm_implausible", value=str(bpm), lo=str(lo), hi=str(hi)),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply != QMessageBox.Yes:
                    self._spin_target_bpm.setFocus()
                    self._spin_target_bpm.selectAll()
                    return
        self.accept()

    def _program_code(self, pid):
        for row in self.db.get_all_dance_programs():
            if row[0] == pid:
                return row[1]
        return None

    def _refresh_program_label(self):
        codes = [self._program_code(p) for p in self._dance_program_ids]
        codes = [c for c in codes if c]
        self._lbl_program.setText(", ".join(codes) if codes
                                  else _t("loc_settings_no_program"))

    def _on_pick_program(self):
        dlg = _MultiProgramPickerDialog(
            self.db, selected_ids=self._dance_program_ids, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._dance_program_ids = dlg.get_selected_ids()
            self._dance_program_id = (self._dance_program_ids[0]
                                      if self._dance_program_ids else None)
            self._refresh_program_label()

    def _on_clear_program(self):
        self._dance_program_ids = []
        self._dance_program_id = None
        self._refresh_program_label()

    def get_program_ids(self):
        """MS50: alle gewaehlten Programm-IDs (fuer location_programs)."""
        return list(self._dance_program_ids)

    def _sync_tempo_fields(self):
        """BL-144: Das Feld des nicht gewaehlten Modus wird ausgegraut.

        Der Radio entscheidet, nicht der Zahlenwert — sonst waere eine Lokation
        mit Alt-Tempo (z.B. 103 %) nie auf Ziel-BPM umstellbar.
        """
        percent = self._radio_percent.isChecked()
        self._spin_tempo.setEnabled(percent)
        self._spin_target_bpm.setEnabled(not percent)

    @staticmethod
    def _parse_time(value, default: "QTime") -> "QTime":
        """BL-178: 'HH:MM'-String → QTime; faellt bei ungueltig auf default."""
        if value:
            t = QTime.fromString(str(value), "HH:mm")
            if t.isValid():
                return t
        return default

    def get_values(self):
        """Gibt (dance_program_id_or_None, temp_tempo, planned_tips_or_None,
        break_minutes, target_bpm_or_None, tempo_mode, schedules_json_or_None)
        zurueck.

        BL-144: Beide Zahlenwerte werden immer zurueckgegeben — welcher gilt,
        sagt tempo_mode.
        BL-178: schedules ist eine JSON-Liste von Termin-Tripeln
        [{"wd":2,"from":"19:30","to":"22:00"}, ...]. Keine Zeile -> None (terminlos).
        """
        import json as _json
        tips = self._spin_tips.value()
        bpm = self._spin_target_bpm.value()
        mode = (Location.TEMPO_MODE_BPM if self._radio_bpm.isChecked()
                else Location.TEMPO_MODE_PERCENT)
        triples = []
        for e in self._schedule_rows:
            wd = e["combo"].currentData()
            if wd is None:
                continue
            triples.append({
                "wd": int(wd),
                "from": e["from"].time().toString("HH:mm"),
                "to": e["to"].time().toString("HH:mm"),
            })
        schedules = _json.dumps(triples) if triples else None
        return (self._dance_program_id, self._spin_tempo.value(),
                tips if tips > 0 else None, self._spin_break.value(),
                float(bpm) if bpm > 0 else None, mode, schedules)


class _MultiProgramPickerDialog(QDialog):
    """MS50: Mehrfachauswahl der Tanzprogramme einer Lokation (Checkbox-Liste).

    Issue #64 (Komfort-Kaskade): Aktiviert der Caller ein hoeheres Programm,
    werden die tieferen Programme derselben Kette automatisch mit angehakt
    (z.B. Plus 2026 -> auch Mainstream 2026). Ohne die tieferen saehe er keine
    Sequenzen, weil es keine Sequenz ohne die tieferen Calls gibt. Abwaehlen
    bleibt frei (keine Rueckwirkung nach oben/unten).

    Zwei getrennte Ketten (rein Band-basiert, keine Code-Namen hartkodiert):
    - Alte Kette:  Basic 1/2 (10/20) + krumme Baender (29/39/49)
    - 2026er/obere Kette: runde Baender ab 30 (30/40/50/60/...)
    WICHTIG: Die 2026er-Kette enthaelt KEINE Basics und kein altes MS/PL/A1 —
    Mainstream 2026 (Band 30) hat die uebrig gebliebenen Basic-Calls bereits
    absorbiert (vgl. SET2026 in song_db.reseed_reference_data). "Ab A2 die
    2026er" folgt automatisch, weil A2 (60) rund ist. Pro tieferem Band wird
    das regulaere (non-Class) Programm angehakt (= kleinster sort_order im
    Band); das angeklickte Programm selbst bleibt wie gewaehlt (auch Class).
    """

    def __init__(self, db, selected_ids=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("dance_picker_title"))
        sel = set(selected_ids or [])
        self._checks = []             # [(pid, QCheckBox)]
        self._cb_by_pid = {}          # pid -> QCheckBox
        self._band_by_pid = {}        # pid -> Band (int) oder None
        self._suppress_cascade = False  # Reentranz-Schutz beim Auto-Anhaken

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        hint = QLabel(_t("loc_settings_multi_hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        programs = db.get_all_dance_programs()
        # Pro Band das regulaere Programm — dorthin kaskadieren die tieferen
        # Baender (program_selection.primary_program_by_band).
        self._band_by_pid = {r[0]: program_selection.band_of(r[5]) for r in programs}
        self._primary_pid_by_band = program_selection.primary_program_by_band(programs)
        self._all_bands = sorted({b for b in self._band_by_pid.values()
                                  if b is not None})

        for row in programs:
            pid, code, label = row[0], row[1], row[2]
            cb = QCheckBox(f"{code} — {label}" if label and label != code else code)
            cb.setChecked(pid in sel)
            # toggled ERST nach setChecked verbinden, damit die Vorbelegung
            # keine Kaskade ausloest (nur bewusste Klicks kaskadieren).
            cb.toggled.connect(lambda checked, p=pid: self._on_toggle(p, checked))
            layout.addWidget(cb)
            self._checks.append((pid, cb))
            self._cb_by_pid[pid] = cb

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_toggle(self, pid, checked):
        """Komfort-Kaskade: Aktivieren hakt die tieferen Programme mit an.

        Abwaehlen bleibt bewusst wirkungslos (der Nutzer darf einzelne untere
        Programme wieder entfernen). Einmalig beim Anhaken, kein dauerhafter
        Zwang.
        """
        if not checked or self._suppress_cascade:
            return
        band = self._band_by_pid.get(pid)
        self._suppress_cascade = True
        try:
            for b in program_selection.predecessor_bands(self._all_bands, band):
                pid_below = self._primary_pid_by_band.get(b)
                if pid_below is None:
                    continue
                cb = self._cb_by_pid.get(pid_below)
                if cb is not None and not cb.isChecked():
                    cb.setChecked(True)
        finally:
            self._suppress_cascade = False

    def get_selected_ids(self):
        return [pid for pid, cb in self._checks if cb.isChecked()]


class _DanceProgramManagerDialog(QDialog):
    """Verwaltungsdialog fuer Tanzprogramm-Tabelle: anlegen, umbenennen, loeschen, Patternlaenge."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(_t("dance_manager_title"))
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        hint = QLabel(_t("dance_manager_hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Tabelle
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels([
            _t("dance_manager_col_code"), _t("dance_manager_col_name"),
            _t("dance_manager_col_sort"), _t("dance_manager_col_target"),
        ])
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.doubleClicked.connect(self._on_edit)
        layout.addWidget(self._table)

        # Buttons
        btn_row = QHBoxLayout()
        btn_add = QPushButton(_t("dance_manager_btn_new"))
        btn_add.clicked.connect(self._on_add)
        btn_row.addWidget(btn_add)

        self._btn_edit = QPushButton(_t("cd.btn_edit"))
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_edit.setEnabled(False)
        btn_row.addWidget(self._btn_edit)

        self._btn_del = QPushButton(_t("btn_delete"))
        self._btn_del.clicked.connect(self._on_delete)
        self._btn_del.setEnabled(False)
        btn_row.addWidget(self._btn_del)

        btn_row.addStretch()
        btn_close = QPushButton(_t("btn_close"))
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._table.selectionModel().selectionChanged.connect(self._on_selection)
        self._refresh()

    def _refresh(self):
        programs = self.db.get_all_dance_programs()
        self._table.setUpdatesEnabled(False)
        self._table.setRowCount(0)
        self._table.setRowCount(len(programs))
        for row, (pid, code, label, sort_order, target_min, *_) in enumerate(programs):
            self._table.setItem(row, 0, QTableWidgetItem(code))
            self._table.setItem(row, 1, QTableWidgetItem(label))
            self._table.setItem(row, 2, QTableWidgetItem(str(sort_order)))
            self._table.setItem(row, 3, QTableWidgetItem(f"{target_min:.1f}"))
            self._table.item(row, 0).setData(Qt.UserRole, pid)
        self._table.setUpdatesEnabled(True)

    def _on_selection(self):
        has_sel = bool(self._table.selectedItems())
        self._btn_edit.setEnabled(has_sel)
        self._btn_del.setEnabled(has_sel)

    def _selected_id(self):
        row = self._table.currentRow()
        if row < 0:
            return None
        return self._table.item(row, 0).data(Qt.UserRole)

    def _on_add(self):
        dlg = _DanceProgramEditDialog(db=self.db, parent=self)
        if dlg.exec() == QDialog.Accepted:
            code, label, sort_order, target_min, seq_limit_to = dlg.get_values()
            try:
                self.db.insert_dance_program(code, label, sort_order, target_min, seq_limit_to)
            except Exception as e:
                QMessageBox.warning(self, _t("error"), _t("dance_manager_err_duplicate", err=e))
            self._refresh()

    def _on_edit(self):
        pid = self._selected_id()
        if pid is None:
            return
        row = self._table.currentRow()
        code = self._table.item(row, 0).text()
        label = self._table.item(row, 1).text()
        sort_order = int(self._table.item(row, 2).text())
        target_min = float(self._table.item(row, 3).text())
        # sequence_limit_to aus DB lesen
        seq_limit_to = None
        for p in self.db.get_all_dance_programs():
            if p[0] == pid:
                seq_limit_to = p[5] if len(p) > 5 else None
                break
        dlg = _DanceProgramEditDialog(code, label, sort_order, target_min,
                                      sequence_limit_to=seq_limit_to,
                                      db=self.db, parent=self)
        if dlg.exec() == QDialog.Accepted:
            code2, label2, so2, tm2, slt2 = dlg.get_values()
            try:
                self.db.update_dance_program(pid, code2, label2, so2, tm2, slt2)
            except Exception as e:
                QMessageBox.warning(self, _t("error"), _t("dance_manager_err_save", err=e))
            self._refresh()

    def _on_delete(self):
        pid = self._selected_id()
        if pid is None:
            return
        row = self._table.currentRow()
        code = self._table.item(row, 0).text()
        if QMessageBox.question(
            self, _t("dance_manager_del_title"),
            _t("dance_manager_del_msg", code=code),
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes:
            self.db.delete_dance_program(pid)
            self._refresh()


class _DanceProgramEditDialog(QDialog):
    """Inline-Editor fuer ein einzelnes Tanzprogramm."""

    def __init__(self, code="", label="", sort_order=0, target_min=7.0,
                 sequence_limit_to=None, db=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("dance_edit_title_edit") if code else _t("dance_edit_title_new"))
        self.setMinimumWidth(380)
        layout = QFormLayout(self)

        self._edit_code = QLineEdit(code)
        self._edit_code.setPlaceholderText(_t("dance_edit_placeholder_code"))
        self._edit_code.setMaxLength(10)
        layout.addRow(_t("dance_edit_lbl_code"), self._edit_code)

        self._edit_label = QLineEdit(label)
        self._edit_label.setPlaceholderText(_t("dance_edit_placeholder_name"))
        layout.addRow(_t("dance_edit_lbl_name"), self._edit_label)

        self._spin_sort = QSpinBox()
        self._spin_sort.setRange(0, 9999)
        self._spin_sort.setValue(sort_order)
        layout.addRow(_t("dance_edit_lbl_sort"), self._spin_sort)

        self._spin_target = QDoubleSpinBox()
        self._spin_target.setRange(1.0, 60.0)
        self._spin_target.setSingleStep(0.5)
        self._spin_target.setDecimals(1)
        self._spin_target.setSuffix(_t("dance_edit_suffix_min"))
        self._spin_target.setValue(target_min)
        layout.addRow(_t("dance_edit_lbl_target"), self._spin_target)

        # BL-132: Sequenz-Limit-ComboBox
        self._combo_seq_limit = QComboBox()
        self._combo_seq_limit.addItem(_t("dance_edit_seq_limit_none"), None)
        if db is not None:
            from sequence_mapper import get_all_calls_sorted
            for name, _eid, to in get_all_calls_sorted(db):
                self._combo_seq_limit.addItem(name, to)
        # Vorauswahl setzen
        if sequence_limit_to is not None:
            for i in range(self._combo_seq_limit.count()):
                if self._combo_seq_limit.itemData(i) == sequence_limit_to:
                    self._combo_seq_limit.setCurrentIndex(i)
                    break
        layout.addRow(_t("dance_edit_lbl_seq_limit"), self._combo_seq_limit)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._validate_and_accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def _validate_and_accept(self):
        if not self._edit_code.text().strip():
            QMessageBox.warning(self, _t("error"), _t("dance_edit_err_empty"))
            return
        self.accept()

    def get_values(self):
        return (
            self._edit_code.text().strip().upper(),
            self._edit_label.text().strip(),
            self._spin_sort.value(),
            self._spin_target.value(),
            self._combo_seq_limit.currentData(),  # BL-132: sequence_limit_to (float or None)
        )


class _GenreManagerDialog(QDialog):
    """Dialog zur Verwaltung aller Genres (Anlegen, Umbenennen, Loeschen/Merge)."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(_t("genre_manager_title"))
        self.setMinimumWidth(420)
        self.setMinimumHeight(500)

        layout = QVBoxLayout(self)

        self._list = QListWidget()
        self._list.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        self._btn_add = QPushButton(_t("genre_add_btn"))
        self._btn_rename = QPushButton(_t("genre_rename_btn"))
        self._btn_delete = QPushButton(_t("genre_delete_btn"))
        self._btn_rename.setEnabled(False)
        self._btn_delete.setEnabled(False)
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_rename)
        btn_row.addWidget(self._btn_delete)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        close_btn = QPushButton(_t("btn_close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self._btn_add.clicked.connect(self._add_genre)
        self._btn_rename.clicked.connect(self._rename_genre)
        self._btn_delete.clicked.connect(self._delete_genre)

        self._refresh()

    def _refresh(self):
        counts = self.db.get_genre_counts()
        genres = self.db.get_all_genres()
        sel_id = None
        if self._list.currentItem():
            sel_id = self._list.currentItem().data(Qt.UserRole)
        self._list.clear()
        restore_row = -1
        for idx, (gid, gname) in enumerate(genres):
            cnt = counts.get(gid, 0)
            item = QListWidgetItem(f"{gname}  ({cnt})")
            item.setData(Qt.UserRole, gid)
            item.setData(Qt.UserRole + 1, gname)
            self._list.addItem(item)
            if gid == sel_id:
                restore_row = idx
        if restore_row >= 0:
            self._list.setCurrentRow(restore_row)

    def _on_selection(self):
        has = bool(self._list.selectedItems())
        self._btn_rename.setEnabled(has)
        self._btn_delete.setEnabled(has)

    def _add_genre(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, _t("genre_add_btn"), _t("genre_new_name"))
        if ok and name.strip():
            self.db.insert_genre(name.strip())
            self._refresh()

    def _rename_genre(self):
        from PySide6.QtWidgets import QInputDialog
        item = self._list.currentItem()
        if not item:
            return
        gid = item.data(Qt.UserRole)
        old_name = item.data(Qt.UserRole + 1)
        new_name, ok = QInputDialog.getText(
            self, _t("genre_rename_title"), _t("genre_new_name"), text=old_name)
        if ok and new_name.strip() and new_name.strip() != old_name:
            self.db.rename_genre(gid, new_name.strip())
            self._refresh()

    def _delete_genre(self):
        item = self._list.currentItem()
        if not item:
            return
        gid = item.data(Qt.UserRole)
        gname = item.data(Qt.UserRole + 1)
        count = self.db.get_genre_counts().get(gid, 0)

        if count > 0:
            # Songs vorhanden → Dialog: Zuordnen oder einfach entfernen
            dlg = QDialog(self)
            dlg.setWindowTitle(_t("genre_delete_title"))
            dlg_layout = QVBoxLayout(dlg)
            lbl = QLabel(_t("genre_delete_text", name=gname, count=count))
            lbl.setWordWrap(True)
            dlg_layout.addWidget(lbl)

            rb_reassign = QRadioButton(_t("genre_delete_reassign_rb"))
            rb_remove = QRadioButton(_t("genre_delete_just_remove"))
            other_genres = [(g_id, g_name) for g_id, g_name
                            in self.db.get_all_genres() if g_id != gid]
            rb_reassign.setChecked(bool(other_genres))
            rb_remove.setChecked(not other_genres)
            dlg_layout.addWidget(rb_reassign)

            combo = QComboBox()
            for g_id, g_name in other_genres:
                combo.addItem(g_name, g_id)
            combo.setEnabled(bool(other_genres))
            rb_reassign.toggled.connect(combo.setEnabled)
            dlg_layout.addWidget(combo)
            dlg_layout.addWidget(rb_remove)

            btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            dlg_layout.addWidget(btns)

            if dlg.exec() != QDialog.Accepted:
                return
            if rb_reassign.isChecked() and combo.currentIndex() >= 0:
                self.db.delete_genre(gid, reassign_to_id=combo.currentData())
            else:
                self.db.delete_genre(gid)
        else:
            reply = QMessageBox.question(
                self, _t("genre_delete_title"),
                _t("genre_delete_confirm", name=gname),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            self.db.delete_genre(gid)

        self._refresh()
