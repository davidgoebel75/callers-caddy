"""Songdaten-Export/-Import als JSON (BL-206).

Zweck: die DB-Daten der Songs einer (gefilterten) Liste exportieren, extern
bearbeiten oder zwischen Installationen/Callern abgleichen und vorsichtig wieder
einspielen.

Bewusste Trennung (siehe BL-206):
- Export ist ungefaehrlich -> Button sitzt im Song-Listen-Widget.
- Import kann Daten ueberschreiben -> lebt an ruhiger Stelle (Potential-Widget),
  schreibt NIE neue Songs an, matcht ueber den Songnamen (nicht ID/Pfad) und
  zeigt vor dem Schreiben einen Feld-Diff mit Vetorecht.

Universelle Feldliste: Spalten werden zur Laufzeit aus dem Schema geholt
(db.list_song_columns), Extended-Data-Keys aus song_properties. Neue Felder
erscheinen dadurch automatisch, ohne dass dieses Modul angepasst werden muss.
Maximale Freiheit bei der Auswahl; kritische Felder sind per Default abgewaehlt.

Zirkelfrei: haengt nur an song_db + i18n + Qt, nicht an main.py.
"""

import os
import json
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton,
    QDialog, QDialogButtonBox, QFileDialog, QMessageBox, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from i18n import _t

FORMAT_TAG = "callers-caddy-songdata"
FORMAT_VERSION = 1

# Reserviertes synthetisches Feld (M:N ueber song_genres, keine echte Spalte).
GENRES_FIELD = "genres"

# Der Songname ist der primaere Zuordnungsschluessel und immer mit dabei.
IDENTIFIER = "title"

# Stabiler Zweitschluessel (lokale Song-id). Nur wirksam, wenn die JSON von
# derselben Installation stammt (install_id-Abgleich) -> erlaubt Umbenennen.
# Automatisch exportiert, kein auswaehlbares Datenfeld.
LOCAL_ID_KEY = "_local_id"

# Kritische Felder: Ueberschreiben hat Nebenwirkungen (Datei-/Pfadbezug bzw.
# Bibliotheks-Aufnahmedatum). Sie werden angeboten, aber per Default NICHT
# ausgewaehlt. Zusaetzlich gilt jede Property mit Endung '_file' als kritisch.
CRITICAL_COLUMNS = {"filename", "lyrics_file", "date_added"}

# 'id' ist installationsspezifisch und laut BL-206 bewusst KEIN Bezugspunkt.
EXCLUDED_COLUMNS = {"id"}

# Bekannte Feld-Labels (uebersetzbar). Unbekannte/kuenftige Spalten und
# Property-Keys werden mit ihrem technischen Namen angezeigt (Universalitaet).
_COLUMN_LABEL_KEYS = {
    "filename": "sdio_field_filename",
    "title": "sdio_field_title",
    "artist": "sdio_field_artist",
    "label": "sdio_field_label",
    "quality": "sdio_field_quality",
    "base_bpm": "sdio_field_base_bpm",
    "standard_tempo": "sdio_field_standard_tempo",
    "pitch": "sdio_field_pitch",
    "volume": "sdio_field_volume",
    "loop_in": "sdio_field_loop_in",
    "loop_out": "sdio_field_loop_out",
    "loop_offset_ms": "sdio_field_loop_offset_ms",
    "lyrics_file": "sdio_field_lyrics_file",
    "is_pattern": "sdio_field_is_pattern",
    "is_singing": "sdio_field_is_singing",
    "date_added": "sdio_field_date_added",
    "err": "sdio_field_err",
    GENRES_FIELD: "sdio_field_genres",
}

_REAL_TOLERANCE = 1e-9


# --------------------------------------------------------------------------- #
#  Feld-Modell
# --------------------------------------------------------------------------- #

class FieldDef:
    """Ein anbietbares Feld: technischer Name, Quelle, Label, kritisch?"""

    def __init__(self, key, source, label, critical, affinity="", default_on=None):
        self.key = key            # technischer Name / Property-Key
        self.source = source      # 'column' | 'property' | 'genres'
        self.label = label        # Anzeigetext
        self.critical = critical  # Warnhinweis + Warnfarbe (Datei-/Pfadbezug)
        self.affinity = affinity  # nur bei 'column' relevant (INTEGER/REAL/TEXT)
        # Ob die Checkbox per Default an ist. Kritische Felder UND alle
        # Extended-Data-Properties sind per Default AUS (wer sie will, hakt an).
        self.default_on = (not critical and source != "property") \
            if default_on is None else default_on


def _label_for(key, source):
    tk = _COLUMN_LABEL_KEYS.get(key)
    if tk:
        txt = _t(tk)
        if txt and txt != tk:
            return txt
    return key


def _is_critical(key, source):
    if source == "column":
        return key in CRITICAL_COLUMNS
    if source == "property":
        return key.endswith("_file")
    return False


def available_fields(db, songs):
    """Alle anbietbaren Felder fuer die uebergebene Song-Menge (universell).

    Reihenfolge: Genres, dann songs-Spalten (Schema-Reihenfolge, ohne 'id' und
    ohne den Identifier 'title'), dann Extended-Data-Property-Keys (alphabetisch).
    'title' wird separat als fester Identifier behandelt.
    """
    fields = []
    # Genres direkt nach dem (festen) Titel anbieten.
    fields.append(FieldDef(GENRES_FIELD, "genres",
                           _label_for(GENRES_FIELD, "genres"), False))
    for name, affinity in db.list_song_columns():
        if name in EXCLUDED_COLUMNS or name == IDENTIFIER:
            continue
        fields.append(FieldDef(name, "column", _label_for(name, "column"),
                               _is_critical(name, "column"), affinity))
    song_ids = [s.id for s in songs if getattr(s, "id", None)]
    for key in db.get_all_property_keys(song_ids):
        fields.append(FieldDef(key, "property", _label_for(key, "property"),
                               _is_critical(key, "property")))
    return fields


# --------------------------------------------------------------------------- #
#  Export
# --------------------------------------------------------------------------- #

def build_export(db, songs, selected_fields):
    """Baut das Export-Dict aus der Song-Menge und den gewaehlten Feldern.

    'title' ist immer enthalten (Identifier). Genres als Namensliste, Spalten
    mit ihrem DB-Wert, Properties nur wenn beim Song gesetzt.
    """
    col_fields = [f for f in selected_fields if f.source == "column"]
    prop_fields = [f for f in selected_fields if f.source == "property"]
    want_genres = any(f.source == "genres" for f in selected_fields)

    field_names = [IDENTIFIER]
    if want_genres:
        field_names.append(GENRES_FIELD)
    field_names += [f.key for f in col_fields] + [f.key for f in prop_fields]

    out_songs = []
    for s in songs:
        row = db.get_song_row(s.id)
        # _local_id: stabiler Zweitschluessel fuer den Re-Import auf DERSELBEN
        # Installation (erlaubt Titel-Umbenennen). Automatisch, kein Datenfeld.
        entry = {LOCAL_ID_KEY: s.id, IDENTIFIER: row.get(IDENTIFIER, s.title or "")}
        if want_genres:
            entry[GENRES_FIELD] = [name for _, name in db.get_genres_for_song(s.id)]
        for f in col_fields:
            entry[f.key] = row.get(f.key)
        if prop_fields:
            props = db.get_properties(s.id)
            for f in prop_fields:
                if f.key in props:
                    entry[f.key] = props[f.key]
        out_songs.append(entry)

    return {
        "format": FORMAT_TAG,
        "version": FORMAT_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        # Installations-Fingerprint: nur bei Gleichheit darf der Import ueber
        # _local_id zuordnen (Titel-Umbenennen). Sonst Titel-Abgleich.
        "install_id": db.get_install_id(),
        "fields": field_names,
        "count": len(out_songs),
        "songs": out_songs,
    }


def write_export_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
#  Import-Planung (reine Logik, ohne UI)
# --------------------------------------------------------------------------- #

def normalize_title(s):
    """Normalisierung fuer den Titel-Abgleich: getrimmt + case-insensitiv."""
    return (s or "").strip().casefold()


def _coerce(affinity, val):
    """JSON-Wert an die Spalten-Affinitaet angleichen (fuer Vergleich + Schreiben)."""
    if val is None:
        return None
    a = affinity or ""
    try:
        if "INT" in a:
            return int(val)
        if "REAL" in a or "FLOA" in a or "DOUB" in a:
            return float(val)
    except (TypeError, ValueError):
        return val
    return str(val)


def _values_differ(affinity, old, new):
    o = _coerce(affinity, old)
    n = _coerce(affinity, new)
    if isinstance(o, float) or isinstance(n, float):
        try:
            return abs(float(o) - float(n)) > _REAL_TOLERANCE
        except (TypeError, ValueError):
            return str(o) != str(n)
    return o != n


def _change_default_on(ch):
    """Default-Haken je Aenderung: Extended-Data-Properties und kritische Felder
    sind AUS, uebrige Spalten (inkl. Titel-Umbenennen) und Genres AN."""
    if ch.critical or ch.kind == "property":
        return False
    return True


def skipped_report_text(plan):
    """Mehrzeiliger Report ueber uebersprungene/ungleiche Songs (mit Namen)."""
    lines = []
    if plan["not_found"]:
        lines.append(_t("sdio_report_notfound", n=len(plan["not_found"]))
                     + ": " + ", ".join(plan["not_found"][:50]))
    if plan["ambiguous"]:
        lines.append(_t("sdio_report_ambiguous", n=len(plan["ambiguous"]))
                     + ": " + ", ".join(plan["ambiguous"][:50]))
    if plan["unchanged"]:
        lines.append(_t("sdio_report_unchanged", n=len(plan["unchanged"])))
    if plan["invalid"]:
        lines.append(_t("sdio_report_invalid", n=len(plan["invalid"])))
    return "\n".join(lines)


class Change:
    """Eine einzelne Feld-Aenderung, die der Nutzer einzeln bestaetigen kann."""

    def __init__(self, song_id, title, field_def, kind, old, new, critical):
        self.song_id = song_id
        self.title = title          # lokaler Titel (Anzeige)
        self.field_def = field_def  # FieldDef oder None (bei Genre-Add/Remove)
        self.kind = kind            # 'column' | 'property' | 'genre_add' | 'genre_remove'
        self.old = old
        self.new = new
        self.critical = critical


def compute_plan(db, data):
    """Vergleicht die JSON-Songs mit der lokalen DB.

    Zuordnung: stammt die JSON von DIESER Installation (install_id-Abgleich),
    wird ein Eintrag mit gueltiger _local_id direkt ueber die Song-id zugeordnet
    (erlaubt Titel-Umbenennen). Sonst Abgleich ueber den normalisierten Titel.

    Rueckgabe: dict mit
      changes:   [Change, ...]  (nur abweichende Felder)
      not_found: [titel, ...]
      ambiguous: [titel, ...]   (>1 lokaler Song mit gleichem Titel)
      unchanged: [titel, ...]   (gefunden, aber keine Abweichung)
      invalid:   [beschreibung] (Eintraege ohne Titel)
    """
    entries = data if isinstance(data, list) else data.get("songs", [])
    col_affinity = {name: aff for name, aff in db.list_song_columns()}

    all_songs = db.get_all()
    local_ids = {s.id for s in all_songs}
    title_index = {}
    for s in all_songs:
        title_index.setdefault(normalize_title(s.title), []).append(s.id)

    same_install = False
    if isinstance(data, dict):
        jid = data.get("install_id")
        same_install = bool(jid) and jid == db.get_install_id()

    result = {"changes": [], "not_found": [], "ambiguous": [],
              "unchanged": [], "invalid": []}

    # Datei-interne Titel-Dubletten nur fuer den Titel-Pfad sperren (nicht bei
    # id-gematchten Eintraegen — dort ist der Titel egal).
    seen_norms = {}
    for entry in entries:
        if same_install and _valid_local_id(entry, local_ids):
            continue
        raw_title = entry.get(IDENTIFIER)
        if raw_title and str(raw_title).strip():
            seen_norms[normalize_title(str(raw_title))] = \
                seen_norms.get(normalize_title(str(raw_title)), 0) + 1

    for entry in entries:
        # 1) Stabiler Zweitschluessel (nur bei gleicher Installation)
        if same_install and _valid_local_id(entry, local_ids):
            song_id = int(entry[LOCAL_ID_KEY])
            song_changes = _diff_entry(db, song_id, entry, col_affinity,
                                       allow_title=True)
            if song_changes:
                result["changes"].extend(song_changes)
            else:
                result["unchanged"].append(_local_title(db, song_id))
            continue

        # 2) Titel-Abgleich (Standard, auch fuer Caller-Austausch)
        raw_title = entry.get(IDENTIFIER)
        if not raw_title or not str(raw_title).strip():
            result["invalid"].append(_t("sdio_import_no_title"))
            continue
        title = str(raw_title)
        norm = normalize_title(title)

        if seen_norms.get(norm, 0) > 1:
            if title not in result["ambiguous"]:
                result["ambiguous"].append(title)
            continue

        matches = title_index.get(norm, [])
        if not matches:
            result["not_found"].append(title)
            continue
        if len(matches) > 1:
            result["ambiguous"].append(title)
            continue

        song_id = matches[0]
        song_changes = _diff_entry(db, song_id, entry, col_affinity,
                                   allow_title=False)
        if song_changes:
            result["changes"].extend(song_changes)
        else:
            result["unchanged"].append(title)

    return result


def _valid_local_id(entry, local_ids):
    """True, wenn der Eintrag eine _local_id traegt, die lokal existiert."""
    lid = entry.get(LOCAL_ID_KEY)
    try:
        return lid is not None and int(lid) in local_ids
    except (TypeError, ValueError):
        return False


def _diff_entry(db, song_id, entry, col_affinity, allow_title=False):
    """Feld-Diff eines einzelnen JSON-Eintrags gegen den lokalen Song.

    allow_title: bei id-basierter Zuordnung darf auch der Titel geaendert werden
    (Umbenennen). Beim Titel-Abgleich ist der Titel der Schluessel und bleibt.
    """
    changes = []
    local_title = _local_title(db, song_id)
    row = db.get_song_row(song_id)
    local_props = db.get_properties(song_id)

    for key, new_val in entry.items():
        if key == LOCAL_ID_KEY:
            continue
        if key == IDENTIFIER and not allow_title:
            continue

        if key == GENRES_FIELD:
            file_genres = new_val if isinstance(new_val, list) else [new_val]
            file_set = {str(g).strip() for g in file_genres if str(g).strip()}
            local_names = [name for _, name in db.get_genres_for_song(song_id)]
            local_lookup = {n.casefold(): n for n in local_names}
            file_lookup = {g.casefold(): g for g in file_set}
            for cf, disp in file_lookup.items():
                if cf not in local_lookup:
                    changes.append(Change(song_id, local_title, None,
                                          "genre_add", "", disp, False))
            for cf, disp in local_lookup.items():
                if cf not in file_lookup:
                    changes.append(Change(song_id, local_title, None,
                                          "genre_remove", disp, "", False))
            continue

        if key in col_affinity:
            aff = col_affinity[key]
            old_val = row.get(key)
            if _values_differ(aff, old_val, new_val):
                fd = FieldDef(key, "column", _label_for(key, "column"),
                              _is_critical(key, "column"), aff)
                changes.append(Change(song_id, local_title, fd, "column",
                                      old_val, _coerce(aff, new_val), fd.critical))
            continue

        # Alles Uebrige = Extended-Data-Property (auch kuenftige/fremde Keys).
        old_val = local_props.get(key, "")
        if str(old_val) != str(new_val):
            fd = FieldDef(key, "property", _label_for(key, "property"),
                          _is_critical(key, "property"))
            changes.append(Change(song_id, local_title, fd, "property",
                                  old_val, new_val, fd.critical))
    return changes


def _local_title(db, song_id):
    s = db.get_by_id(song_id)
    return (s.title or s.filename) if s else f"ID {song_id}"


def apply_changes(db, changes):
    """Schreibt die uebergebenen (bestaetigten) Aenderungen.

    Spaltenaenderungen werden pro Song gebuendelt (ein UPDATE), Properties und
    Genres einzeln. Rueckgabe: (anzahl_songs, anzahl_aenderungen).
    """
    col_by_song = {}      # song_id -> {col: value}
    touched = set()
    applied = 0

    for ch in changes:
        touched.add(ch.song_id)
        if ch.kind == "column":
            col_by_song.setdefault(ch.song_id, {})[ch.field_def.key] = ch.new
            applied += 1
        elif ch.kind == "property":
            db.set_property(ch.song_id, ch.field_def.key, str(ch.new))
            applied += 1
        elif ch.kind == "genre_add":
            gid = db.get_genre_id_by_name(ch.new)
            if gid <= 0:
                gid = db.insert_genre(ch.new)
            db.add_song_genre(ch.song_id, gid)
            applied += 1
        elif ch.kind == "genre_remove":
            gid = db.get_genre_id_by_name(ch.old)
            if gid > 0:
                db.remove_song_genre(ch.song_id, gid)
            applied += 1

    for song_id, col_values in col_by_song.items():
        db.apply_import_fields(song_id, col_values)

    return len(touched), applied


# --------------------------------------------------------------------------- #
#  UI: Feld-Auswahl (Export)
# --------------------------------------------------------------------------- #

class FieldSelectDialog(QDialog):
    """Feld-Auswahl vor dem Export. 'title' ist fix an; kritische Felder sind
    per Default abgewaehlt (Warnfarbe + Tooltip)."""

    def __init__(self, fields, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("sdio_export_fields_title"))
        self.resize(460, 560)
        self._fields = fields
        self._checks = []  # [(FieldDef, QCheckBox)]

        layout = QVBoxLayout(self)
        info = QLabel(_t("sdio_export_fields_info"))
        info.setWordWrap(True)
        layout.addWidget(info)

        # Identifier fest anzeigen
        id_lbl = QLabel("✓ " + _t("sdio_field_title") + "  " + _t("sdio_identifier_hint"))
        id_lbl.setStyleSheet("color:#888; font-size:11px;")
        layout.addWidget(id_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        vinner = QVBoxLayout(inner)
        vinner.setSpacing(2)
        for fd in fields:
            cb = QCheckBox(fd.label)
            cb.setChecked(fd.default_on)
            if fd.critical:
                cb.setText(fd.label + "  ⚠")
                cb.setToolTip(_t("sdio_critical_tooltip"))
                cb.setStyleSheet("color:#c0392b;")
            elif fd.source == "property":
                cb.setToolTip(_t("sdio_extended_tooltip"))
            self._checks.append((fd, cb))
            vinner.addWidget(cb)
        vinner.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)

        quick = QHBoxLayout()
        btn_all = QPushButton(_t("sdio_select_all"))
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none = QPushButton(_t("sdio_select_none"))
        btn_none.clicked.connect(lambda: self._set_all(False))
        btn_safe = QPushButton(_t("sdio_select_default"))
        btn_safe.clicked.connect(self._select_default)
        quick.addWidget(btn_all)
        quick.addWidget(btn_none)
        quick.addWidget(btn_safe)
        quick.addStretch()
        layout.addLayout(quick)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _set_all(self, state):
        for _, cb in self._checks:
            cb.setChecked(state)

    def _select_default(self):
        for fd, cb in self._checks:
            cb.setChecked(fd.default_on)

    def selected(self):
        return [fd for fd, cb in self._checks if cb.isChecked()]


# --------------------------------------------------------------------------- #
#  UI: Import-Vorschau (Diff)
# --------------------------------------------------------------------------- #

class ImportPreviewDialog(QDialog):
    """Zeigt den Feld-Diff (alt -> neu) mit Checkbox je Aenderung. Kritische
    Zeilen sind default abgewaehlt und farblich markiert. Uebersprungene Songs
    (nicht gefunden / mehrdeutig / unveraendert) stehen im Report darunter."""

    COL_CHECK, COL_SONG, COL_FIELD, COL_OLD, COL_NEW, COL_HINT = range(6)

    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("sdio_import_preview_title"))
        self.resize(880, 620)
        self._changes = plan["changes"]

        layout = QVBoxLayout(self)

        summary = _t("sdio_import_summary",
                     changes=len(plan["changes"]),
                     notfound=len(plan["not_found"]),
                     ambiguous=len(plan["ambiguous"]),
                     unchanged=len(plan["unchanged"]))
        lbl = QLabel(summary)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "", _t("sdio_col_song"), _t("sdio_col_field"),
            _t("sdio_col_old"), _t("sdio_col_new"), _t("sdio_col_hint")])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(self.COL_SONG, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(self.COL_OLD, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(self.COL_NEW, QHeaderView.Stretch)
        table.setRowCount(len(self._changes))
        self._table = table

        for r, ch in enumerate(self._changes):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked if _change_default_on(ch) else Qt.Unchecked)
            chk.setData(Qt.UserRole, r)
            table.setItem(r, self.COL_CHECK, chk)

            table.setItem(r, self.COL_SONG, QTableWidgetItem(ch.title))
            table.setItem(r, self.COL_FIELD, QTableWidgetItem(self._field_label(ch)))
            table.setItem(r, self.COL_OLD, QTableWidgetItem(self._fmt(ch.old)))
            table.setItem(r, self.COL_NEW, QTableWidgetItem(self._fmt(ch.new)))

            hint = ""
            if ch.critical:
                hint = _t("sdio_hint_critical")
            table.setItem(r, self.COL_HINT, QTableWidgetItem(hint))

            if ch.critical:
                for c in range(6):
                    it = table.item(r, c)
                    if it:
                        it.setForeground(QColor("#c0392b"))
        layout.addWidget(table, 1)

        quick = QHBoxLayout()
        btn_all = QPushButton(_t("sdio_select_all"))
        btn_all.clicked.connect(lambda: self._set_all(Qt.Checked))
        btn_none = QPushButton(_t("sdio_select_none"))
        btn_none.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        btn_safe = QPushButton(_t("sdio_select_default"))
        btn_safe.clicked.connect(self._check_default)
        quick.addWidget(btn_all)
        quick.addWidget(btn_none)
        quick.addWidget(btn_safe)
        quick.addStretch()
        layout.addLayout(quick)

        # Report ueber uebersprungene / ungleiche Songs (mit Namen)
        skipped = skipped_report_text(plan)
        if skipped:
            box = QTextEdit()
            box.setReadOnly(True)
            box.setPlainText(skipped)
            box.setMaximumHeight(120)
            layout.addWidget(box)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(_t("sdio_apply_btn"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _field_label(self, ch):
        if ch.kind == "genre_add":
            return _t("sdio_field_genres") + "  (+)"
        if ch.kind == "genre_remove":
            return _t("sdio_field_genres") + "  (−)"
        return ch.field_def.label if ch.field_def else ch.kind

    def _fmt(self, v):
        if v is None:
            return ""
        return str(v)

    def _set_all(self, state):
        for r in range(self._table.rowCount()):
            self._table.item(r, self.COL_CHECK).setCheckState(state)

    def _check_default(self):
        for r in range(self._table.rowCount()):
            ch = self._changes[r]
            self._table.item(r, self.COL_CHECK).setCheckState(
                Qt.Checked if _change_default_on(ch) else Qt.Unchecked)

    def selected_changes(self):
        out = []
        for r in range(self._table.rowCount()):
            if self._table.item(r, self.COL_CHECK).checkState() == Qt.Checked:
                out.append(self._changes[r])
        return out


# --------------------------------------------------------------------------- #
#  Einstiegspunkte fuer die Widgets
# --------------------------------------------------------------------------- #

def export_songs_interactive(parent, db, songs, default_dir=""):
    """Kompletter Export-Ablauf: Feld-Auswahl -> Datei -> schreiben -> Info."""
    if not songs:
        QMessageBox.information(parent, _t("sdio_export_title"),
                               _t("sdio_export_empty"))
        return

    fields = available_fields(db, songs)
    dlg = FieldSelectDialog(fields, parent)
    if dlg.exec() != QDialog.Accepted:
        return
    selected = dlg.selected()

    default_name = f"songdata_export_{datetime.now():%Y-%m-%d}.json"
    start = os.path.join(default_dir, default_name) if default_dir else default_name
    path, _sel = QFileDialog.getSaveFileName(
        parent, _t("sdio_export_title"), start, "JSON (*.json)")
    if not path:
        return
    if not path.lower().endswith(".json"):
        path += ".json"

    data = build_export(db, songs, selected)
    try:
        write_export_json(path, data)
    except Exception as e:  # noqa: BLE001 - Nutzer soll die Ursache sehen
        QMessageBox.warning(parent, _t("error"), str(e))
        return

    QMessageBox.information(
        parent, _t("sdio_export_title"),
        _t("sdio_export_done", count=data["count"],
           fields=len(data["fields"]), path=path))


def import_songs_interactive(parent, db):
    """Kompletter Import-Ablauf: Datei -> Diff-Vorschau -> schreiben -> Report."""
    path, _sel = QFileDialog.getOpenFileName(
        parent, _t("sdio_import_title"), "", "JSON (*.json)")
    if not path:
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        QMessageBox.warning(parent, _t("error"), str(e))
        return

    # Format-Hinweis (weich): fremde JSONs mit 'songs' trotzdem zulassen.
    if isinstance(data, dict) and data.get("format") not in (None, FORMAT_TAG):
        if QMessageBox.question(
                parent, _t("sdio_import_title"),
                _t("sdio_import_wrong_format")) != QMessageBox.Yes:
            return

    plan = compute_plan(db, data)
    if not plan["changes"]:
        msg = _t("sdio_import_nothing", notfound=len(plan["not_found"]),
                 ambiguous=len(plan["ambiguous"]),
                 unchanged=len(plan["unchanged"]))
        detail = skipped_report_text(plan)
        if detail:
            msg += "\n\n" + detail
        QMessageBox.information(parent, _t("sdio_import_title"), msg)
        return

    dlg = ImportPreviewDialog(plan, parent)
    if dlg.exec() != QDialog.Accepted:
        return
    chosen = dlg.selected_changes()
    if not chosen:
        return

    songs_n, applied = apply_changes(db, chosen)
    QMessageBox.information(
        parent, _t("sdio_import_title"),
        _t("sdio_import_done", songs=songs_n, changes=applied))
    return songs_n
