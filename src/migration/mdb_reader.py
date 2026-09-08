"""Access 97 (.mdb) Leser fuer Callers Caddy 1.0 Migration.

Nutzt access-parser (Pure Python) da der aktuelle ODBC-Treiber
Access 97 (Jet 3.5) nicht mehr oeffnen kann.

Enthaelt Monkey-Patches fuer access-parser Bugs:
1. _parse_fixed_length_data: column_id >= null_table → Bounds-Check
2. _parse_dynamic_length_data: vcn-basiertes Indexing (statt sequenziellem i)
3. _parse_row: Per-Record null_table_len (statt table_header.column_count)
4. _parse_dynamic_length_records_metadata: Akzeptiert unterschiedliche
   variable_length_field_count (erweiterte Tabellen)
5. _get_table_columns: Safe Primary-Key-Lookup
"""

import os
import struct
import sys
import warnings
from access_parser import AccessParser
from access_parser.access_parser import (
    AccessTable, parse_type, TYPE_BOOLEAN,
    parse_relative_object_metadata_struct, ConstructError,
)


# ---------------------------------------------------------------------------
# Monkey-Patch 1: _parse_fixed_length_data
# Fix: column_id Bounds-Check auf null_table
# ---------------------------------------------------------------------------

def _patched_parse_fixed_length_data(self, original_record, column, null_table):
    """Gepatchte Version: faengt out-of-range column_id sicher ab."""
    column_name = column.col_name_str
    has_value = True
    try:
        if column.column_id >= len(null_table):
            # Spalte existierte beim Schreiben des Records noch nicht
            if column.type == TYPE_BOOLEAN:
                has_value = None
        else:
            has_value = null_table[column.column_id]
    except (IndexError, KeyError):
        if column.type == TYPE_BOOLEAN:
            has_value = None

    if column.type == TYPE_BOOLEAN:
        parsed_type = has_value
    else:
        if column.fixed_offset > len(original_record):
            return
        record = original_record[column.fixed_offset:]
        try:
            parsed_type = parse_type(
                column.type, record, version=self.version,
                props=column.extra_props or None)
        except Exception:
            self.parsed_table[column_name].append(None)
            return
        if not has_value:
            self.parsed_table[column_name].append(None)
            return
    self.parsed_table[column_name].append(parsed_type)


# ---------------------------------------------------------------------------
# Monkey-Patch 2: _parse_dynamic_length_data
# Fix: vcn-basiertes Indexing in Offset-Array + Jump-Table-Korrektur
# ---------------------------------------------------------------------------

def _patched_parse_dynamic_length_data(self, original_record, metadata,
                                       relative_records_column_map, null_table):
    """Gepatchte Version: nutzt variable_column_number statt sequenziellem Index.

    Jet 3.5 speichert Variable-Length-Felder nach variable_column_number (vcn).
    Wenn Spalten geloescht/hinzugefuegt wurden, entstehen Luecken in den
    Offset-Slots. Der Original-Parser nutzt enumerate(i) was nur bei
    lueckenlosen Tabellen funktioniert.
    """
    relative_offsets = metadata.variable_length_field_offsets
    num_offsets = len(relative_offsets)

    # Jump-Table: Vorberechnen welche Slot-Indices einen 0x100-Sprung haben
    jump_additions = {}  # slot_index → kumulativer jump_table_addition
    if self.version == 3 and metadata.variable_length_jump_table:
        cumulative = 0
        for slot in range(num_offsets):
            if slot in metadata.variable_length_jump_table:
                cumulative += 0x100
            jump_additions[slot] = cumulative

    for column_index in relative_records_column_map:
        column = relative_records_column_map[column_index]
        col_name = column.col_name_str
        vcn = getattr(column, 'variable_column_number', None)

        # Kein variable_column_number oder ausserhalb der Offset-Tabelle
        if vcn is None or vcn >= num_offsets:
            self.parsed_table[col_name].append(None)
            continue

        # Null-Check
        has_value = True
        try:
            if column.column_id < len(null_table):
                has_value = null_table[column.column_id]
        except (IndexError, KeyError):
            pass

        if not has_value:
            self.parsed_table[col_name].append(None)
            continue

        rel_start = relative_offsets[vcn]
        if vcn + 1 < num_offsets:
            rel_end = relative_offsets[vcn + 1]
        else:
            rel_end = metadata.var_len_count

        if rel_start == rel_end:
            self.parsed_table[col_name].append(None)
            continue

        jta_start = jump_additions.get(vcn, 0)
        jta_end = jump_additions.get(vcn + 1, jta_start)
        rel_start += jta_start
        rel_end += jta_end

        try:
            record = original_record[rel_start:rel_end]
            parsed_type = parse_type(
                column.type, record, version=self.version,
                props=column.extra_props or None)
            self.parsed_table[col_name].append(parsed_type)
        except Exception:
            self.parsed_table[col_name].append(None)


# ---------------------------------------------------------------------------
# Monkey-Patch 3: _parse_row() — Per-Record null_table_len
# Problem: table_header.column_count passt nicht zu alten Records die
# VOR einer Tabellenerweiterung geschrieben wurden.
# Fix: Erst field_count lesen, dann null_table_len davon ableiten.
# ---------------------------------------------------------------------------

def _patched_parse_row(self, record):
    """Gepatchte Version: nutzt per-Record field_count fuer null_table_len.

    Jet 3.5 Records speichern im 1. Byte die Spaltenanzahl zum
    Schreibzeitpunkt. Bei erweiterten Tabellen (ALTER TABLE ADD COLUMN)
    haben alte Records weniger Spalten als table_header.column_count.
    Die null_table Groesse muss pro Record korrekt sein, sonst werden
    die Metadaten am Record-Ende falsch gelesen.
    """
    original_record = record

    if len(record) < 3:
        return

    # Schritt 1: field_count aus dem Record lesen (1 Byte fuer Jet 3.5)
    if self.version > 3:
        field_count = struct.unpack_from("h", record)[0]
        record = record[2:]
    else:
        # UNSIGNED Byte: Column-Count kann >127 sein
        field_count = struct.unpack_from("B", record)[0]
        record = record[1:]

    # Schritt 2: null_table_len aus dem Record-eigenen field_count berechnen
    null_table_len = (field_count + 7) // 8
    if not null_table_len or null_table_len >= len(original_record):
        # Fallback: table_header.column_count
        null_table_len = (self.table_header.column_count + 7) // 8
        if not null_table_len or null_table_len >= len(original_record):
            return

    null_table = original_record[-null_table_len:]
    null_table = [((null_table[i // 8]) & (1 << (i % 8))) != 0
                  for i in range(len(null_table) * 8)]

    # Fixed-Length Spalten parsen
    relative_records_column_map = {}
    for i, column in self.columns.items():
        if not column.column_flags.fixed_length:
            relative_records_column_map[i] = column
            continue
        self._parse_fixed_length_data(record, column, null_table)

    # Dynamic-Length Spalten parsen
    if relative_records_column_map:
        relative_records_column_map = dict(
            sorted(relative_records_column_map.items()))
        reverse_record = original_record[::-1]
        metadata = self._parse_dynamic_length_records_metadata(
            reverse_record, original_record, null_table_len)
        dynamic_ok = False
        if metadata and metadata.variable_length_field_offsets:
            self._parse_dynamic_length_data(
                original_record, metadata,
                relative_records_column_map, null_table)
            dynamic_ok = True

        if not dynamic_ok:
            # Dynamic-Part fehlgeschlagen → alle Dynamic-Spalten mit None
            for column in relative_records_column_map.values():
                self.parsed_table[column.col_name_str].append(None)


# ---------------------------------------------------------------------------
# Monkey-Patch 4: _parse_dynamic_length_records_metadata()
# Problem: Verwirft Records bei Mismatch variable_length_field_count vs
# table_header.variable_columns. Bei erweiterten Tabellen matcht fast
# kein Record.
# Fix: Akzeptiere abweichende Counts, parse trotzdem.
# ---------------------------------------------------------------------------

def _patched_parse_dynamic_records_metadata(self, reverse_record, original_record,
                                            null_table_length):
    """Gepatchte Version: akzeptiert variable_length_field_count Mismatch.

    Bei erweiterten Tabellen (ALTER TABLE ADD COLUMN) haben alte Records
    weniger Variable-Length-Spalten als table_header.variable_columns.
    Der Original-Parser verwirft diese Records komplett (returns None).
    Wir akzeptieren sie und parsen mit den vorhandenen Offsets.
    """
    if self.version > 3:
        reverse_record = reverse_record[null_table_length:]
        return parse_relative_object_metadata_struct(
            reverse_record, version=self.version)

    # Jet 3.5: Metadata vom Ende des Records (reverse_record)
    variable_length_jump_table_cnt = (len(original_record) - 1) // 256
    reverse_record = reverse_record[null_table_length:]
    try:
        metadata = parse_relative_object_metadata_struct(
            reverse_record, variable_length_jump_table_cnt, self.version)
        metadata.relative_metadata_end = (
            metadata.relative_metadata_end + null_table_length)
    except ConstructError:
        return None

    expected = self.table_header.variable_columns
    actual = metadata.variable_length_field_count

    if actual == expected:
        # Perfekt: Record passt zum aktuellen Schema
        return metadata

    # Mismatch: Versuche den Standard-Fallback (suche expected byte)
    metadata_start = reverse_record.find(bytes([expected]))
    if metadata_start != -1 and metadata_start < 10:
        try:
            new_metadata = parse_relative_object_metadata_struct(
                reverse_record[metadata_start:],
                variable_length_jump_table_cnt, self.version)
            new_metadata.relative_metadata_end = (
                new_metadata.relative_metadata_end + metadata_start)
            return new_metadata
        except ConstructError:
            pass

    # Kein Match gefunden: Akzeptiere das Original-Ergebnis trotzdem!
    # Die vorhandenen Offsets beziehen sich auf die Spalten, die beim
    # Schreiben des Records existierten.
    if actual > 0 and metadata.variable_length_field_offsets:
        return metadata

    return None


# ---------------------------------------------------------------------------
# Monkey-Patch 5: _get_table_columns() Primary-Key-Lookup
# Problem: Geloeschte/hinzugefuegte Spalten hinterlassen ungueltige col_ids
# in den Index-Eintraegen → KeyError bei Primary-Key-Aufloesung.
# ---------------------------------------------------------------------------

def _patched_get_table_columns(self):
    """Gepatchte Version: faengt KeyError bei Primary-Key-Lookup ab."""
    from access_parser.access_parser import (
        parse_table_head, parse_table_data,
    )
    try:
        table_header = parse_table_head(self.table.value, version=self.version)
        merged_data = self.table.value[table_header.tdef_header_end:]
        if table_header.TDEF_header.next_page_ptr:
            merged_data = merged_data + self._merge_table_data(
                table_header.TDEF_header.next_page_ptr)
        parsed_data = parse_table_data(
            merged_data,
            table_header.index_count,
            table_header.real_index_count,
            table_header.column_count,
            version=self.version,
        )
        table_header['column'] = parsed_data['column']
        table_header['column_names'] = parsed_data['column_names']
        table_header['real_index_2'] = parsed_data['real_index_2']
        table_header["all_indexes"] = parsed_data["all_indexes"]
        table_header["index_names"] = parsed_data["index_names"]
    except ConstructError:
        return

    col_names = table_header.column_names
    columns = table_header.column

    for i, c in enumerate(columns):
        c.col_name_str = col_names[i].col_name_str
        c.extra_props = None

    offset = min(x.column_index for x in columns)
    column_dict = {x.column_index - offset: x for x in columns}
    if len(column_dict) != len(columns):
        column_dict = {x.column_id: x for x in columns}

    if self.props:
        for i, col in column_dict.items():
            if col.col_name_str in self.props:
                col.extra_props = self.props[col.col_name_str]

    # Primary Keys: sicher aufloesen (KeyError abfangen)
    primary_keys = []
    try:
        primary_keys = [
            column_dict[col.col_id].col_name_str
            for idx in table_header.all_indexes
            for col in table_header.real_index_2[idx.idx_col_num].unk_struct
            if idx.idx_type == 1 and col.col_id ^ 0xFFFF
        ]
    except (KeyError, IndexError, AttributeError):
        pass  # PK-Info nicht kritisch fuer Datenimport

    return column_dict, primary_keys, table_header


# Patches anwenden
AccessTable._parse_fixed_length_data = _patched_parse_fixed_length_data
AccessTable._parse_dynamic_length_data = _patched_parse_dynamic_length_data
AccessTable._parse_row = _patched_parse_row
AccessTable._parse_dynamic_length_records_metadata = _patched_parse_dynamic_records_metadata
AccessTable._get_table_columns = _patched_get_table_columns


# ---------------------------------------------------------------------------
# Offizielle CC1-Spaltennamen (nur diese werden uebernommen)
# ---------------------------------------------------------------------------

_OFFICIAL_SONG_COLS = {
    "ID", "Volume", "Speed", "Pitch", "Loop", "BPM", "Name", "Artist",
    "Label", "Loop_Start", "Loop_End", "URL_Vocal", "URL_Music",
    "URL_Lyric", "Songtype", "Laenge", "Genre", "Rating_Singing",
    "Rating_Pattern", "Tempo",
}

_OFFICIAL_GROUP_COLS = {
    "id", "name", "plz", "ort", "strasse", "telefon", "kontaktname",
    "kontaktplz", "kontaktort", "kontaktstrasse", "kontakttelefon", "tanzort",
}


class MdbReader:
    """Liest Songs, Gruppen und Historie aus einer Callers Caddy 1.0 MDB."""

    # Tabellennamen-Mapping: CC1-Standard → moegliche Varianten
    _TABLE_ALIASES = {
        "gruppen": ["gruppen", "Gruppen"],
        "Song": ["Song"],
        "Historie": ["Historie"],
        "Sequenzen": ["Sequenzen"],
        "AlleFiguren": ["AlleFiguren"],
    }

    def __init__(self, mdb_path: str):
        self._path = mdb_path
        warnings.filterwarnings("ignore")
        # access-parser gibt "Error while parsing MSysObjects" auf stderr aus
        # → stderr temporaer umleiten
        old_stderr = sys.stderr
        sys.stderr = open(os.devnull, "w")
        try:
            self._db = AccessParser(mdb_path)
        finally:
            sys.stderr.close()
            sys.stderr = old_stderr

    def _resolve_table_name(self, name: str) -> str | None:
        """Findet den tatsaechlichen Tabellennamen im Catalog (Case-Fallback)."""
        catalog = self._db.catalog or {}
        # Exakter Match
        if name in catalog:
            return name
        # Aliase pruefen
        aliases = self._TABLE_ALIASES.get(name, [])
        for alias in aliases:
            if alias in catalog:
                return alias
        # Case-insensitiver Fallback
        name_lower = name.lower()
        for cat_name in catalog:
            if cat_name.lower() == name_lower:
                return cat_name
        return None

    def _parse(self, table_name: str,
               official_cols: set | None = None) -> list[dict]:
        """Parsed eine Tabelle und gibt Liste von Dicts zurueck.

        Args:
            table_name: Name der Access-Tabelle
            official_cols: Wenn gesetzt, nur diese Spalten uebernehmen
                           (Case-Sensitive). Schuetzt vor User-Erweiterungen.
        """
        # Tabellennamen im Catalog aufloesen (Case-Fallback)
        resolved = self._resolve_table_name(table_name)
        if resolved is None:
            print(f"[MdbReader] Tabelle '{table_name}' nicht gefunden "
                  f"im Catalog: {list((self._db.catalog or {}).keys())}")
            return []
        if resolved != table_name:
            print(f"[MdbReader] Tabelle '{table_name}' -> '{resolved}' "
                  f"(Case-Korrektur)")

        try:
            parsed = self._db.parse_table(resolved)
        except Exception as e:
            print(f"[MdbReader] Fehler beim Lesen von '{resolved}': {e}")
            return []

        if not parsed:
            return []

        cols = list(parsed.keys())

        # Nur offizielle Spalten behalten (User-Erweiterungen ignorieren)
        if official_cols:
            # Case-insensitiver Match fuer offizielle Spalten
            official_lower = {c.lower(): c for c in official_cols}
            extra = [c for c in cols if c.lower() not in official_lower]
            if extra:
                print(f"[MdbReader] '{resolved}': {len(extra)} "
                      f"Zusatzspalten ignoriert: {extra}")
            cols = [c for c in cols if c.lower() in official_lower]

        if not cols:
            return []

        # Row-Count Konsistenz pruefen und padden
        row_counts = {c: len(parsed[c]) for c in cols}
        max_rows = max(row_counts.values())
        min_rows = min(row_counts.values())
        if min_rows != max_rows:
            print(f"[MdbReader] WARNUNG '{resolved}': "
                  f"Row-Count-Mismatch (min={min_rows}, max={max_rows}). "
                  f"Spalten mit weniger Rows werden mit None aufgefuellt.")
            # Kuerzere Spalten auf max_rows auffuellen
            for c in cols:
                col_data = parsed[c]
                while len(col_data) < max_rows:
                    col_data.append(None)

        rows = []
        for i in range(max_rows):
            row = {}
            for c in cols:
                val = parsed[c][i]
                # bytes → str (CP1252)
                if isinstance(val, bytes):
                    try:
                        val = val.decode("utf-8")
                    except UnicodeDecodeError:
                        val = val.decode("cp1252", errors="replace")
                row[c] = val
            rows.append(row)
        return rows

    def read_songs(self) -> list[dict]:
        """Liest die Song-Tabelle (520+ Eintraege).

        Felder: ID, Volume, Speed, Pitch, Loop, BPM, Name, Artist, Label,
        Loop_Start, Loop_End, URL_Vocal, URL_Music, URL_Lyric, Songtype,
        Laenge, Genre, Rating_Singing, Rating_Pattern, Tempo
        """
        return self._parse("Song", _OFFICIAL_SONG_COLS)

    def read_groups(self) -> list[dict]:
        """Liest die gruppen-Tabelle (45+ Eintraege).

        Felder: id, name, plz, ort, strasse, telefon, kontaktname,
        kontaktplz, kontaktort, kontaktstrasse, kontakttelefon, tanzort
        """
        return self._parse("gruppen", _OFFICIAL_GROUP_COLS)

    def read_history(self) -> list[dict]:
        """Liest die Historie-Tabelle (4830+ Eintraege).

        Felder: datum, gruppe, titel
        Achtung: Referenziert Songs und Gruppen per NAME, nicht per ID!
        """
        return self._parse("Historie")

    def read_sequences(self) -> list[dict]:
        """Liest die Sequenzen-Tabelle (885+ Eintraege).

        Felder: ID, Feld1-Feld15, Level, Skill
        Jede Sequenz enthaelt bis zu 15 Calls als Einzelfelder.
        """
        return self._parse("Sequenzen")

    def read_alle_figuren(self) -> list[dict]:
        """Liest die AlleFiguren-Tabelle (1026+ Eintraege).

        Felder: Figur, Alias (und weitere)
        Dient als zusaetzliche Alias-Quelle fuer das Call-Mapping.
        """
        return self._parse("AlleFiguren")

    def get_summary(self) -> dict:
        """Schnelle Zaehlung ohne vollstaendiges Parsen."""
        songs = self.read_songs()
        groups = self.read_groups()
        history = self.read_history()
        return {
            "songs": len(songs),
            "groups": len(groups),
            "history": len(history),
            "db_path": self._path,
        }
