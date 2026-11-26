"""Sequenzen, Teaching-Order, Zuordnungen, Figuren-Mengen und Band-Cache
von SongDatabase (intern#143, intern#165).

Mixin: SongDatabase erbt die Methoden, Aufrufer schreiben weiter
db.get_filtered_sequences() usw. Die Zustandsvariablen des Band-Caches legt
SongDatabase.__init__ an. Die Hilfsfunktionen fuer Calllisten und Sequenz-Typen
auf Modulebene sind auch ohne DB nutzbar.
"""
import json
import sqlite3


# Hoechstzahl Werte je IN (...)-Liste (Grenze fuer SQL-Parameter)
_SQL_CHUNK = 400


def _chunks(values):
    """values in Teilen zu hoechstens _SQL_CHUNK fuer IN (...)-Listen."""
    for i in range(0, len(values), _SQL_CHUNK):
        yield values[i:i + _SQL_CHUNK]


def _teaching_order_sort_key(teaching_order):
    """Sortierschluessel wie ORDER BY teaching_order in SQLite (NULL zuerst)."""
    return (teaching_order is not None, teaching_order or 0)


# ---- SQL-Statements: Sequenzen (Cached Live-Mapping) ----


# Figuren je Call-Text mit ihrer fruehesten Teaching-Order (NULL = Figur ohne
# call_programs-Zeile). Grundlage fuer die Rangfolge "hoechste Figur zuerst".
_SELECT_CALL_TEXT_FIGURES_RANKED = (
    "SELECT f.call_text, f.entity_id, r.min_to "
    "FROM call_text_figures f "
    "LEFT JOIN (SELECT entity_id, MIN(teaching_order) AS min_to "
    "           FROM call_programs GROUP BY entity_id) r "
    "ON r.entity_id = f.entity_id"
)


# intern#247: Kartentext -> Callname der App fuer die Choreo-Engine (letzte Lesart
# im Mapping). Nur Texte mit genau einem Call (ohne call_text_figures_extra).
_SELECT_CHOREO_CALL_NAMES = (
    "SELECT m.call_text, c.canonical_name FROM call_text_mappings m "
    "JOIN calls c ON c.entity_id = m.entity_id "
    "WHERE m.call_text NOT IN (SELECT call_text FROM call_text_figures_extra)"
)


def read_choreo_call_names(db_path: str, call_texts=None) -> dict:
    """{Kartentext: Callname} aus der DB unter db_path, eigene Verbindung nur
    lesend (fuer Hintergrund-Threads, die die Haupt-Verbindung nicht teilen
    duerfen). Leeres dict, wenn die DB nicht lesbar ist.

    call_texts: nur diese Kartentexte lesen (intern#263). Square Flow braucht je
    Auftrag nur die Zeilen der Sequenz; die ganze Tabelle (ca. 10.000 Zeilen)
    kostete auf schwachen Rechnern ueber 100 ms je Auftrag. None = alle."""
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return {}
    try:
        if call_texts is None:
            return dict(con.execute(_SELECT_CHOREO_CALL_NAMES).fetchall())
        texts = sorted({str(t) for t in call_texts if t})
        out = {}
        for part in _chunks(texts):       # Grenze fuer SQL-Parameter
            out.update(con.execute(
                _SELECT_CHOREO_CALL_NAMES
                + f" AND m.call_text IN ({','.join('?' * len(part))})", part).fetchall())
        return out
    except sqlite3.Error:
        return {}
    finally:
        con.close()


def read_choreo_cache(db_path: str, sequence_id: int):
    """intern#247: (input_hash, engine_ver, result_json, anim_z) aus sequence_choreo
    oder None. anim_z: Animation zlib-gepackt (intern#263), None bei Eintraegen ohne.
    Eigene, nur lesende Verbindung (Hintergrund-Thread)."""
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return None
    try:
        return con.execute(
            "SELECT input_hash, engine_ver, result_json, anim_z FROM sequence_choreo "
            "WHERE sequence_id = ?", (sequence_id,)).fetchone()
    except sqlite3.Error:
        return None
    finally:
        con.close()


def write_choreo_cache(db_path: str, sequence_id: int, input_hash: str,
                       engine_ver: str, result_json: str, anim_z=None) -> bool:
    """intern#247: Ergebnis je Sequenz ablegen (ersetzt den alten Eintrag).
    anim_z: Animation zlib-gepackt (intern#263, analysis.anim_to_blob) oder None.
    Eigene kurze Verbindung aus dem Hintergrund-Thread; gelingt das Schreiben
    nicht (DB gesperrt), bleibt es beim naechsten Mal ungespeichert."""
    try:
        con = sqlite3.connect(db_path, timeout=2)
    except sqlite3.Error:
        return False
    try:
        with con:
            con.execute(
                "INSERT OR REPLACE INTO sequence_choreo "
                "(sequence_id, input_hash, engine_ver, result_json, anim_z) "
                "VALUES (?, ?, ?, ?, ?)",
                (sequence_id, input_hash, engine_ver, result_json, anim_z))
        return True
    except sqlite3.Error:
        return False
    finally:
        con.close()


def _text_max_to(rows) -> dict:
    """Verdichtet Zeilen aus _SELECT_CALL_TEXT_FIGURES_RANKED zu
    {call_text: Teaching-Order}.

    BL-210: mehrere Figuren eines Textes -> hoechste Teaching-Order zaehlt
    (alle Figuren muessen tanzbar sein). Fehlt einer Figur die Teaching-Order,
    gilt der Text als ungemappt (None).
    """
    text_to_to = {}
    for text, _eid, to in rows:
        if text not in text_to_to:
            text_to_to[text] = to
            continue
        prev = text_to_to[text]
        text_to_to[text] = None if prev is None or to is None else max(prev, to)
    return text_to_to


_INSERT_SEQUENCE = """
INSERT INTO sequences (field_1, field_2, field_3, field_4, field_5,
                       field_6, field_7, field_8, field_9, field_10,
                       field_11, field_12, field_13, field_14, field_15,
                       level_original, max_teaching_order,
                       type, difficulty, calls_json, source, tags)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

_COUNT_SEQUENCES = "SELECT COUNT(*) FROM sequences;"

# ---------------------------------------------------------------------------
# Sequenz-Typ-Kanonisierung
# ---------------------------------------------------------------------------
# Ein Sequenz-Typ darf nur EINE Schreibweise haben, sonst zerfaellt der
# Typ-Filter im SequenzView in scheinbar verschiedene Kategorien. Kanonisch ist
# die native Ceder-Konvention: "Singer (...)" (nicht "Singing call (...)") und
# Pfeil "➔" als Trenner (nicht Bindestrich). Diese Tabelle bildet bekannte
# Alt-/Import-Schreibweisen auf die kanonische Form ab; unbekannte Werte bleiben
# unveraendert (nur um Pfeil-Trenner normalisiert).
_SEQ_TYPE_ALIASES = {
    "Singing call (Corner progression)": "Singer (Corner progression)",
    "Singing call (R-H Lady progression)": "Singer (R-H Lady progression)",
    "Static Set ➔ Resolve - Complete Dance Routine": "Static Set ➔ Resolve",
}


def canonicalize_seq_type(raw: str) -> str:
    """Fuehrt einen Sequenz-Typ auf seine kanonische Schreibweise zurueck.

    Anwenden an JEDER Schreibstelle (Import, Editor), damit nie zwei Labels fuer
    denselben Typ entstehen. Idempotent: canonicalize(canonicalize(x)) == canonicalize(x).
    """
    if not raw:
        return ""
    value = raw.strip()
    # "- Complete Dance Routine" ist ein Special-Tag (Ceder special=15), kein
    # eigener Typ — an jeden Basistyp anhaengbar (Static Set, Six Couples ...).
    # Generisch abstreifen, damit keine Schatten-Kategorien entstehen.
    _CDR = " - Complete Dance Routine"
    if value.endswith(_CDR):
        value = value[:-len(_CDR)]
    # Bindestrich-Trenner der "X - Y"-Resolve-Typen auf native Pfeil-Form ziehen.
    if value.startswith(("Static Set - ", "Zero Line - ", "Zero Box - ")):
        value = value.replace(" - ", " ➔ ", 1)
    return _SEQ_TYPE_ALIASES.get(value, value)


# ---------------------------------------------------------------------------
# Sequenz-Calllisten: JSON <-> Liste, Mirror-Felder
# ---------------------------------------------------------------------------
# calls_json ist die Source of Truth (beliebig viele Calls). field_1..15 werden
# als Mirror der ersten 15 mitgefuehrt (Rueckwaerts-Kompatibilitaet fuer aeltere
# App-Versionen). Beide entstehen aus DERSELBEN bereinigten Liste, damit nichts
# auseinanderlaeuft. Bereinigung = strip + leere/'-'-Platzhalter raus (identisch
# zur bisherigen get_sequence_calls-Logik, damit der Alt-Bestand bitgleich bleibt).

def clean_calls(calls) -> list:
    """Bereinigt eine rohe Callliste: strip, leere und '-'-Platzhalter entfernen."""
    out = []
    for c in (calls or []):
        if c is None:
            continue
        s = str(c).strip()
        if s and s != "-":
            out.append(s)
    return out


def calls_to_json(calls) -> str:
    """Bereinigte Callliste als JSON-Array-String (UTF-8, keine ASCII-Escapes)."""
    return json.dumps(clean_calls(calls), ensure_ascii=False)


def calls_from_json(raw) -> list:
    """JSON-Array-String -> Liste. Leer/ungueltig -> []."""
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (ValueError, TypeError):
        return []


def calls_to_mirror_fields(calls) -> list:
    """Erste 15 bereinigte Calls, auf genau 15 mit None aufgefuellt (Mirror)."""
    cleaned = clean_calls(calls)[:15]
    return cleaned + [None] * (15 - len(cleaned))


class SequencesMixin:
    """Sequenz-Bereich der Datenbank: Sequenzen, Teaching-Order, Zuordnungen,
    Figuren-Mengen und Band-Cache."""

    def _backfill_calls_json(self):
        """Fuellt calls_json fuer Alt-Zeilen aus field_1..15 (Option C).

        Selbst-abgesichert: verarbeitet nur Zeilen mit calls_json IS NULL. Nach
        dem ersten Lauf sind das keine mehr -> die Pruefung ist danach ein
        billiger Count. Neu eingefuegte Zeilen setzen calls_json ohnehin direkt.
        Baut die Liste bitgleich zur get_sequence_calls-Logik (strip, '-'/leer raus).
        """
        # Spalte vorhanden? (falls Migration auf einer Uralt-DB scheiterte)
        cols = [r[1] for r in self._conn.execute("PRAGMA table_info(sequences)")]
        if "calls_json" not in cols:
            return
        rows = self._conn.execute(
            "SELECT id, field_1, field_2, field_3, field_4, field_5, "
            "field_6, field_7, field_8, field_9, field_10, "
            "field_11, field_12, field_13, field_14, field_15 "
            "FROM sequences WHERE calls_json IS NULL"
        ).fetchall()
        if not rows:
            return
        updates = [(calls_to_json(row[1:16]), row[0]) for row in rows]
        self._conn.executemany(
            "UPDATE sequences SET calls_json = ? WHERE id = ?", updates)
        self._conn.commit()
        print(f"[SongDB] calls_json-Backfill: {len(updates)} Sequenzen gefuellt")

    # ---- enthält-Filter-Index (sequence_calls) ----

    def _sync_sequence_calls_for(self, seq_id: int, calls) -> None:
        """Aktualisiert die Index-Zeilen EINER Sequenz (kein commit hier).

        Loescht die alten Zeilen und legt je Call eine neue an (nur sequence_id,
        position, call_text). Aufrufer committet."""
        self._conn.execute(
            "DELETE FROM sequence_calls WHERE sequence_id = ?", (seq_id,))
        cleaned = clean_calls(calls)
        if cleaned:
            self._conn.executemany(
                "INSERT INTO sequence_calls (sequence_id, position, call_text) "
                "VALUES (?, ?, ?)",
                [(seq_id, i + 1, t) for i, t in enumerate(cleaned)])

    def rebuild_sequence_calls_index(self) -> int:
        """Baut den kompletten enthält-Filter-Index aus calls_json neu auf.

        Aufrufen nach Massen-Importen (Roh-INSERTs, die insert_sequence umgehen)
        oder wenn der Index veraltet ist. Gibt die Zeilenzahl zurueck."""
        self._conn.execute("DELETE FROM sequence_calls")
        ins = []
        for sid, cj in self._conn.execute("SELECT id, calls_json FROM sequences"):
            for pos, text in enumerate(calls_from_json(cj), start=1):
                ins.append((sid, pos, text))
        if ins:
            self._conn.executemany(
                "INSERT INTO sequence_calls (sequence_id, position, call_text) "
                "VALUES (?, ?, ?)", ins)
        self._conn.commit()
        print(f"[SongDB] sequence_calls-Index neu gebaut: {len(ins)} Zeilen")
        return len(ins)

    def _ensure_sequence_calls_index(self) -> None:
        """Baut den Index beim Oeffnen neu, falls er fehlt oder veraltet ist.

        Vergleicht die Zahl der indizierten Sequenzen mit der Zahl der Sequenzen
        mit mind. einem Call. Stimmt sie nicht (leer, teilbefuellt, Altbestand vom
        externen Remap-Tool), wird neu gebaut. Im Normalfall (synchron) passiert
        nichts."""
        try:
            want = self._conn.execute(
                "SELECT COUNT(*) FROM sequences "
                "WHERE calls_json IS NOT NULL AND calls_json != '[]'"
            ).fetchone()[0]
            have = self._conn.execute(
                "SELECT COUNT(DISTINCT sequence_id) FROM sequence_calls"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            return  # Tabelle fehlt (Uralt-DB) — _create_tables legt sie noch an
        if have != want:
            self.rebuild_sequence_calls_index()

    # ---- Calls eines Tanzprogramms (BL-199) ----

    def get_real_calls(self) -> list[tuple]:
        """[(entity_id, canonical_name)] aller echten Calls (ohne '--'-Trenner)."""
        return self._conn.execute(
            "SELECT entity_id, canonical_name FROM calls "
            "WHERE canonical_name NOT LIKE '--%'").fetchall()

    def get_calls_for_program(self, program_label: str) -> list:
        """Alle echten Calls eines Programms, nach Teaching-Order sortiert.

        program_label ist das in call_programs.program gespeicherte Programm-
        Label (z. B. "Mainstream (2026)"), NICHT der dance_programs.code.
        Trenner-Eintraege ("-- ... --") werden herausgefiltert, Duplikate
        (mehrere teaching_order-Zeilen je Call) zusammengefasst.

        Returns:
            Liste von (entity_id, canonical_name).
        """
        if not program_label:
            return []
        cur = self._conn.execute(
            "SELECT c.entity_id, c.canonical_name "
            "FROM call_programs cp JOIN calls c ON c.entity_id = cp.entity_id "
            "WHERE cp.program = ? AND c.canonical_name NOT LIKE '--%' "
            "ORDER BY cp.teaching_order, c.canonical_name;",
            (program_label,)
        )
        seen = set()
        out = []
        for eid, name in cur.fetchall():
            if eid in seen:
                continue
            seen.add(eid)
            out.append((eid, name))
        return out

    # ---- Sequenzen-CRUD ----

    def get_all_calls_json(self) -> set:
        """calls_json aller Sequenzen, fuer den Dubletten-Check beim Import."""
        return {r[0] for r in self._conn.execute(
            "SELECT calls_json FROM sequences WHERE calls_json IS NOT NULL")
            if r[0]}

    def insert_sequence(self, fields: list, level_original: str = "",
                        max_teaching_order: float = None,
                        seq_type: str = "", difficulty: str = "",
                        source: str = "", tags: str = "") -> int:
        """Fuegt eine Sequenz ein und gibt die ID zurueck.

        Args:
            fields: Liste von Call-Texten (wird auf 15 Felder aufgefuellt)
            level_original: Original-Level-Text (z.B. "Mainstream - SSD Week 9")
            max_teaching_order: Vorberechnete hoechste Teaching-Order
            seq_type: Sequenz-Typ (z.B. "Singer (Corner progression)")
            difficulty: Schwierigkeitsgrad (z.B. "Easy", "Medium", "Hard")
        """
        # calls_json = volle Liste (Source of Truth); field_1..15 = Mirror der
        # ersten 15 (Rueckwaerts-Kompatibilitaet). Beide aus derselben Liste.
        mirror = calls_to_mirror_fields(fields)
        params = mirror + [level_original, max_teaching_order,
                           canonicalize_seq_type(seq_type), difficulty or "",
                           calls_to_json(fields), source or "", tags or ""]
        cur = self._conn.execute(_INSERT_SEQUENCE, params)
        seq_id = cur.lastrowid
        self._sync_sequence_calls_for(seq_id, fields)
        self._conn.commit()
        return seq_id

    def bulk_import_sequences(self, seqs, source: str = "",
                              replace_source: bool = False,
                              dedup_against_existing: bool = True) -> tuple:
        """Fuegt VIELE Sequenzen effizient ein — eine Transaktion, Index +
        max_teaching_order werden EINMAL am Ende aufgebaut (nicht pro Zeile).
        Ersetzt das langsame Schleifen-insert_sequence fuer Massen-Importe.

        Args:
            seqs: iterable von dicts {calls, level, seq_type, difficulty}.
            source: Herkunfts-Marke der neuen Zeilen ('' = User, 'ceder' = Referenz).
            replace_source: True -> vorher ALLE Zeilen mit genau diesem source
                loeschen (sauberes Ersetzen des Referenz-Satzes; User-Sequenzen
                mit anderem source bleiben unberuehrt).
            dedup_against_existing: True -> Sequenzen ueberspringen, deren calls_json
                schon in der DB existiert (nach evtl. replace_source) oder im Batch
                doppelt ist. Verhindert Doppelungen gegen User-eigene Sequenzen.

        Returns:
            (inserted, skipped)
        """
        if replace_source:
            self._conn.execute(
                "DELETE FROM sequence_calls WHERE sequence_id IN "
                "(SELECT id FROM sequences WHERE source = ?)", (source or "",))
            self._conn.execute("DELETE FROM sequences WHERE source = ?",
                               (source or "",))

        existing = self.get_all_calls_json() if dedup_against_existing else set()

        rows = []
        skipped = 0
        batch_seen = set()
        for s in seqs:
            meta = s if isinstance(s, dict) else {}
            calls = meta.get("calls") if isinstance(s, dict) else s
            cleaned = clean_calls(calls)
            if not cleaned:
                skipped += 1
                continue
            cj = calls_to_json(cleaned)
            if dedup_against_existing and (cj in existing or cj in batch_seen):
                skipped += 1
                continue
            batch_seen.add(cj)
            mirror = calls_to_mirror_fields(cleaned)
            rows.append(tuple(mirror) + (
                meta.get("level", "") or "", None,
                canonicalize_seq_type(meta.get("seq_type", "") or ""),
                meta.get("difficulty", "") or "", cj, source or ""))

        if rows:
            self._conn.executemany(
                "INSERT INTO sequences (field_1, field_2, field_3, field_4, "
                "field_5, field_6, field_7, field_8, field_9, field_10, "
                "field_11, field_12, field_13, field_14, field_15, "
                "level_original, max_teaching_order, type, difficulty, "
                "calls_json, source) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        self._conn.commit()
        # Index + Cache einmal aufbauen (Bulk-INSERT umging insert_sequence).
        self.rebuild_sequence_calls_index()
        # Auto-Mappings fuer die neuen Call-Texte anlegen — sonst bliebe der Import
        # voellig ungemappt und der Band-Filter (Programmwahl) zeigte 0 Sequenzen.
        self.backfill_auto_mappings()
        self.recompute_sequence_max_to()
        return (len(rows), skipped)

    def get_sequence_count(self) -> int:
        """Anzahl aller Sequenzen in der Datenbank."""
        cur = self._conn.execute(_COUNT_SEQUENCES)
        return cur.fetchone()[0]

    def get_all_sequences_for_export(self) -> list[dict]:
        """Gibt alle Sequenzen im JSON-Import-Format zurueck (calls, level, seq_type, difficulty)."""
        cur = self._conn.execute(
            "SELECT id, calls_json, field_1, field_2, field_3, field_4, field_5, "
            "field_6, field_7, field_8, field_9, field_10, "
            "field_11, field_12, field_13, field_14, field_15, "
            "level_original, type, difficulty "
            "FROM sequences ORDER BY id"
        )
        result = []
        for row in cur.fetchall():
            seq_id = row[0]
            # Volle Liste aus calls_json (Fallback: Mirror-Felder row[2:17]).
            calls = calls_from_json(row[1]) if row[1] else clean_calls(row[2:17])
            result.append({
                "id": str(seq_id),
                "calls": calls,
                "level": row[17] or "",
                "seq_type": row[18] or "",
                "difficulty": row[19] or "",
            })
        return result

    # ---- MS50-Perf: Band-Cover-Cache + Scope-Materialisierung ----

    def _band_data_version(self) -> int:
        """Aktueller Wert des Trigger-Zaehlers (0 falls Tabelle fehlt)."""
        try:
            row = self._conn.execute("SELECT v FROM _band_cache_ver").fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def sequence_data_version(self) -> int:
        """intern#263: Aenderungszaehler fuer Speicher ausserhalb der DB-Schicht
        (Sequenz-Detail). Steigt per Trigger bei jeder Aenderung an
        sequence_calls, call_text_mappings, call_text_figures_extra und
        call_programs, also auch an Schreibstellen, die niemand Bescheid geben."""
        return self._band_data_version()

    def _check_band_cache_version(self):
        """Verwirft den Band-Cache, sobald sich relevante Daten geaendert haben
        (sequences/sequence_calls/call_text_mappings/call_programs -> Trigger)."""
        ver = self._band_data_version()
        if ver != self._band_cache_ver_seen:
            self._band_cover_cache = {}
            self._scope_key = None
            self._seq_figures = None
            self._band_cache_ver_seen = ver

    # Stand der Cover-Regel im Schluessel des persistenten _band_cover-Caches:
    # aendert sich die Regel, passen alte Eintraege nicht mehr (intern#206).
    _COVER_RULE = 2

    def _sequence_figures(self) -> dict:
        """intern#111: Figuren-Menge je Sequenz, nur Figuren mit call_programs-
        Zeile in einem echten Band (bandlose/ungemappte Calls schliessen nicht
        aus). Einmal je Daten-Version aufbauen (~100 ms bei 106k sequence_calls);
        danach kostet jede Band-/Limit-/"Nur"-Kombination nur einen Mengenvergleich
        (~2 ms) statt des vollen Joins (~145 ms).

        intern#206: Teaching-Order < 1 (Band 0: Filler Words, Face) liegt vor allen
        Programmen und gehoert zu keinem. Solche Figuren zaehlen nicht als gebandet,
        sonst schloesse jeder Filler-Text die Sequenz aus jeder Programmwahl aus."""
        if self._seq_figures is None:
            banded = {e for (e,) in self._conn.execute(
                "SELECT DISTINCT entity_id FROM call_programs "
                "WHERE teaching_order >= 1")}
            text_figs = {}
            for ct, eid in self._conn.execute(
                    "SELECT call_text, entity_id FROM call_text_figures"):
                if eid in banded:
                    text_figs.setdefault(ct, []).append(eid)
            seq_figs = {}
            for sid, ct in self._conn.execute(
                    "SELECT sequence_id, call_text FROM sequence_calls"):
                figs = text_figs.get(ct)
                if figs:
                    seq_figs.setdefault(sid, set()).update(figs)
            self._seq_figures = {s: frozenset(f) for s, f in seq_figs.items()}
        return self._seq_figures

    def _cover_ids(self, bandset: frozenset, max_to: float = None) -> frozenset:
        """Menge der Sequenz-IDs, deren gemappte Figuren ALLE in mindestens einem der
        Baender liegen (aggregiert pro Figur -> Mehrfachnennung korrekt). Optional
        begrenzt max_to die Figuren zusaetzlich auf Teaching-Position <= max_to (feiner
        Limit-Filter). Ergebnis je (Band-Menge, max_to) gecacht. Rechnet ueber
        _sequence_figures statt per SQL-Join (intern#111)."""
        if not bandset:
            return frozenset()
        key = (bandset, max_to)
        cached = self._band_cover_cache.get(key)
        if cached is not None:
            return cached
        bands = sorted(bandset)
        # Persistenter Cover-Cache (B): erst in _band_cover nachschlagen. Der
        # Eintrag ist mit dem `v` gestempelt, bei dem er galt; passt es zum
        # aktuellen `v`, sparen wir den Aufbau von _sequence_figures (~100 ms) —
        # auch ueber Neustarts hinweg. cache_key ist stabil aus Band-Menge + Limit.
        ck = f"r{self._COVER_RULE}|{bands}|{max_to}"
        ver = self._band_data_version()
        try:
            prow = self._conn.execute(
                "SELECT ids FROM _band_cover WHERE cache_key=? AND ver=?",
                (ck, ver)).fetchone()
        except sqlite3.OperationalError:
            prow = None   # Tabelle (noch) nicht vorhanden (alte DB vor Migration)
        if prow is not None:
            ids = (frozenset(int(x) for x in prow[0].split(","))
                   if prow[0] else frozenset())
            self._band_cover_cache[key] = ids
            return ids
        # Eine Figur "zaehlt" nur, wenn sie eine Band-Zeile im gewaehlten Band hat
        # UND (bei gesetztem Limit) an einer Teaching-Position <= max_to liegt. So
        # wirkt der Limit feingranular INNERHALB eines Bandes (z.B. Spin Chain Thru
        # vor Recycle, obwohl beide in Band 29). Eine Sequenz passt, wenn ALLE ihre
        # gebandeten Figuren zaehlen (Mehrfachnennung: irgendeine Band-Zeile reicht).
        allowed = {e for e, to in self._conn.execute(
                       "SELECT entity_id, teaching_order FROM call_programs")
                   if to is not None and int(to) in bandset
                   and (max_to is None or to <= max_to)}
        ids = frozenset(sid for sid, figs in self._sequence_figures().items()
                        if figs <= allowed)
        self._band_cover_cache[key] = ids
        # Ergebnis persistieren (B): ueber Neustarts halten, damit der Start den
        # Aufbau von _sequence_figures spart. Eintraege alter Versionen passen
        # nie mehr -> beim Schreiben mit aufraeumen.
        try:
            self._conn.execute("DELETE FROM _band_cover WHERE ver <> ?", (ver,))
            self._conn.execute(
                "INSERT OR REPLACE INTO _band_cover (cache_key, ver, ids) "
                "VALUES (?, ?, ?)",
                (ck, ver, ",".join(str(i) for i in sorted(ids))))
            self._conn.commit()
        except sqlite3.OperationalError:
            pass   # Tabelle fehlt (alte DB) -> nur In-Memory-Cache, kein Persist
        return ids

    def _ensure_band_scope(self, bands_filter, bands_below_filter, cover_max_to=None):
        """Materialisiert die aktuell gefilterte Band-ID-Menge (Baender minus 'below'
        fuer "Only", optional mit feiner Limit-Obergrenze cover_max_to) in der TEMP-
        Tabelle seq_scope. Rechnet nur neu, wenn sich Band-Menge, Limit oder Daten
        aenderten. Danach lesen count/page/ids alle billig aus seq_scope."""
        self._check_band_cache_version()
        bkey = frozenset(int(b) for b in bands_filter) if bands_filter else frozenset()
        lkey = (frozenset(int(b) for b in bands_below_filter)
                if bands_below_filter else frozenset())
        key = (bkey, lkey, cover_max_to)
        if key == self._scope_key:
            return
        cover = set(self._cover_ids(bkey, cover_max_to))
        if lkey:
            cover -= set(self._cover_ids(lkey, cover_max_to))
        self._conn.execute(
            "CREATE TEMP TABLE IF NOT EXISTS seq_scope (id INTEGER PRIMARY KEY)")
        self._conn.execute("DELETE FROM seq_scope")
        self._conn.executemany(
            "INSERT INTO seq_scope (id) VALUES (?)", [(i,) for i in cover])
        # DELETE/INSERT oeffnen implizit eine Transaktion. Ohne commit() bliebe die
        # Haupt-Verbindung mit altem Lese-Stand darin haengen; sobald eine zweite
        # Verbindung schreibt (Square-Flow-Cache), scheitert dann jeder Schreibzugriff
        # hier mit "database is locked" (SQLITE_BUSY_SNAPSHOT), Review #194.
        self._conn.commit()
        self._scope_key = key

    def invalidate_band_cache(self):
        """Verwirft den Band-Cache manuell. Die Trigger-Version macht das i.d.R.
        selbst; diese Methode ist ein expliziter Reset (z.B. fuer Tests)."""
        self._band_cover_cache = {}
        self._scope_key = None
        self._seq_figures = None
        self._band_cache_ver_seen = -1

    def _build_sequence_where(self,
                              entity_id_filter: str = None,
                              max_to_filter: float = None,
                              type_filter: str = None,
                              difficulty_filter: str = None,
                              min_to_filter: float = None,
                              tags_filter: str = None,
                              bands_filter=None,
                              bands_below_filter=None,
                              cover_max_to: float = None,
                              hide_unmapped: bool = False) -> tuple:
        """Hilfsmethode: baut WHERE-Clause + params fuer Sequenz-Abfragen.

        bands_filter: iterable von Programm-Baendern (Ganzzahlen). Wenn gesetzt,
        greift der MS50-Mengen-Filter (statt/zusaetzlich zu max_to_filter): nur
        Sequenzen, deren gemappte Figuren ALLE in einem der Baender liegen und die
        mind. eine erkannte Figur haben. Aggregiert pro Figur (Mehrfachnennung).

        Returns:
            (where_sql, params)
        """
        where_clauses = []
        params = []

        # MS50-Perf: Der teure "welche Sequenz ist mit diesen Baendern tanzbar"-Join
        # wird NICHT mehr je Query neu gerechnet. Stattdessen materialisiert
        # _ensure_band_scope die (gecachte) Menge tanzbarer IDs einmal in der TEMP-
        # Tabelle seq_scope (inkl. 'below' fuer "Only" bereits herausgerechnet) und
        # wir referenzieren sie nur. Neu-Berechnung nur bei Band-Wechsel oder
        # Datenaenderung (Trigger-Version). Siehe _cover_ids / _ensure_band_scope.
        if bands_filter:
            self._ensure_band_scope(bands_filter, bands_below_filter, cover_max_to)
            where_clauses.append("id IN (SELECT id FROM seq_scope)")

        if entity_id_filter:
            # enthält-Filter ueber den indizierten sequence_calls-Index: von der
            # entity_id ueber call_text_figures (idx_ctm_entity/idx_ctfe_entity) auf die
            # call_texts, von dort ueber idx_seqcalls_calltext auf die
            # sequence_ids. Index-Seek statt Full-Scan; deckt auch Calls >15 ab.
            where_clauses.append("""id IN (
                SELECT sc.sequence_id
                FROM call_text_figures m
                JOIN sequence_calls sc ON sc.call_text = m.call_text
                WHERE m.entity_id = ?
            )""")
            params.append(entity_id_filter)

        # intern#156: Sequenzen ohne Einstufung (mind. ein Call-Text ohne tanzbare
        # Zuordnung, in der Liste rot) haben unbekannten Inhalt -> standardmaessig
        # aus. Der Band-Filter allein laesst sie durch, weil er nur die
        # zugeordneten Figuren prueft.
        if hide_unmapped:
            where_clauses.append("max_teaching_order IS NOT NULL")

        if max_to_filter is not None:
            where_clauses.append(
                "max_teaching_order IS NOT NULL AND max_teaching_order <= ?"
            )
            params.append(max_to_filter)

        # "Nur"-Filter: hoechster Call muss im Ziel-Programm liegen
        # (Untergrenze = Programm-Start, z.B. 50.0 fuer A1)
        if min_to_filter is not None:
            where_clauses.append(
                "max_teaching_order IS NOT NULL AND max_teaching_order >= ?"
            )
            params.append(min_to_filter)

        if type_filter:
            where_clauses.append("type = ?")
            params.append(type_filter)

        if difficulty_filter:
            where_clauses.append("difficulty = ?")
            params.append(difficulty_filter)

        # BL-191: Tag-Filter — exakter Match auf den gewaehlten Tag.
        if tags_filter:
            where_clauses.append("tags = ?")
            params.append(tags_filter)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        return where_sql, params

    def get_filtered_sequences(self, entity_id_filter: str = None,
                               max_to_filter: float = None,
                               limit: int = 50, offset: int = 0,
                               type_filter: str = None,
                               difficulty_filter: str = None,
                               min_to_filter: float = None,
                               tags_filter: str = None,
                               bands_filter=None,
                               bands_below_filter=None,
                               cover_max_to: float = None,
                               hide_unmapped: bool = False) -> list[tuple]:
        """Gibt gefilterte Sequenzen zurueck (Lazy Loading).

        Returns:
            [(id, field_1..15, level_original, max_teaching_order, type, difficulty), ...]
            Indizes: 0=id, 1-15=fields, 16=level_original, 17=max_to, 18=type, 19=difficulty
        """
        where_sql, params = self._build_sequence_where(
            entity_id_filter, max_to_filter, type_filter, difficulty_filter,
            min_to_filter, tags_filter, bands_filter, bands_below_filter,
            cover_max_to=cover_max_to, hide_unmapped=hide_unmapped)

        sql = f"""SELECT id, field_1, field_2, field_3, field_4, field_5,
                         field_6, field_7, field_8, field_9, field_10,
                         field_11, field_12, field_13, field_14, field_15,
                         level_original, max_teaching_order,
                         type, difficulty
                  FROM sequences {where_sql}
                  ORDER BY id LIMIT ? OFFSET ?"""
        params.extend([limit, offset])
        cur = self._conn.execute(sql, params)
        return cur.fetchall()

    def get_filtered_count(self, entity_id_filter: str = None,
                           max_to_filter: float = None,
                           type_filter: str = None,
                           difficulty_filter: str = None,
                           min_to_filter: float = None,
                           tags_filter: str = None,
                           bands_filter=None,
                           bands_below_filter=None,
                           cover_max_to: float = None,
                           hide_unmapped: bool = False) -> int:
        """Gibt die Anzahl gefilterter Sequenzen zurueck."""
        where_sql, params = self._build_sequence_where(
            entity_id_filter, max_to_filter, type_filter, difficulty_filter,
            min_to_filter, tags_filter, bands_filter, bands_below_filter,
            cover_max_to=cover_max_to, hide_unmapped=hide_unmapped)
        sql = f"SELECT COUNT(*) FROM sequences {where_sql}"
        cur = self._conn.execute(sql, params)
        return cur.fetchone()[0]

    def get_filtered_sequence_ids(self, entity_id_filter: str = None,
                                   max_to_filter: float = None,
                                   type_filter: str = None,
                                   difficulty_filter: str = None,
                                   min_to_filter: float = None,
                                   tags_filter: str = None,
                                   bands_filter=None,
                                   bands_below_filter=None,
                                   cover_max_to: float = None,
                                   hide_unmapped: bool = False) -> list:
        """Gibt alle IDs gefilterter Sequenzen zurueck (fuer Navigation im Detail-Dialog)."""
        where_sql, params = self._build_sequence_where(
            entity_id_filter, max_to_filter, type_filter, difficulty_filter,
            min_to_filter, tags_filter, bands_filter, bands_below_filter,
            cover_max_to=cover_max_to, hide_unmapped=hide_unmapped)
        sql = f"SELECT id FROM sequences {where_sql} ORDER BY id"
        cur = self._conn.execute(sql, params)
        return [row[0] for row in cur.fetchall()]

    def get_sequence_type_values(self) -> list[str]:
        """Gibt alle vorhandenen (nicht-leeren) type-Werte sortiert zurueck."""
        cur = self._conn.execute(
            "SELECT DISTINCT type FROM sequences WHERE type != '' ORDER BY type"
        )
        return [row[0] for row in cur.fetchall()]

    def get_sequence_difficulty_values(self) -> list[str]:
        """Gibt alle vorhandenen (nicht-leeren) difficulty-Werte zurueck (Easy→Medium→Hard)."""
        cur = self._conn.execute(
            "SELECT DISTINCT difficulty FROM sequences WHERE difficulty != '' ORDER BY difficulty"
        )
        raw = [row[0] for row in cur.fetchall()]
        # Sinnvolle Reihenfolge: Easy vor Medium vor Hard
        order = ["Easy", "Medium", "Hard"]
        sorted_vals = [v for v in order if v in raw]
        sorted_vals += [v for v in raw if v not in order]
        return sorted_vals

    def get_sequence_tags_values(self) -> list[str]:
        """BL-191: Gibt alle vorhandenen (nicht-leeren) Tag-Werte alphabetisch
        zurueck. Basis fuer die Auto-Vervollstaendigung im Editor und die
        Filter-Vorschlaege im Sequences-Widget."""
        cur = self._conn.execute(
            "SELECT DISTINCT tags FROM sequences WHERE tags != '' "
            "ORDER BY tags COLLATE NOCASE"
        )
        return [row[0] for row in cur.fetchall()]

    def get_sequence_details_many(self, sequence_ids) -> dict:
        """intern#263: Calls, Typ und Schwierigkeit vieler Sequenzen auf einmal,
        fuer den Speicher des Sequenz-Details.

        {sequence_id: (calls, seq_type, difficulty)}; calls genau wie
        get_sequence_calls, seq_type/difficulty wie get_sequence_raw (roh).
        Wenige Abfragen fuer die ganze Liste statt ca. 12 je Sequenz: Jede
        Abfrage gibt den GIL ab, und waehrend der Wiedergabe kostet jedes
        Zurueckholen bis zu 5 ms, wenn andere Threads rechnen.
        Sequenzen, die es nicht gibt, fehlen im Ergebnis."""
        ids = list(dict.fromkeys(sequence_ids))
        rows = {}
        for part in _chunks(ids):
            for r in self._conn.execute(
                    "SELECT id, calls_json, field_1, field_2, field_3, field_4, "
                    "field_5, field_6, field_7, field_8, field_9, field_10, "
                    "field_11, field_12, field_13, field_14, field_15, type, difficulty "
                    f"FROM sequences WHERE id IN ({','.join('?' * len(part))})", part):
                calls = calls_from_json(r[1]) if r[1] else clean_calls(r[2:17])
                rows[r[0]] = (calls, r[17], r[18])
        texts = sorted({t for calls, _, _ in rows.values() for t in calls})
        figure_tos = {}  # call_text -> {entity_id: [teaching_order, ...]}
        mapping = {}     # call_text -> (entity_id, teaching_order, canonical_name)
        for part in _chunks(texts):
            marks = ",".join("?" * len(part))
            for text, eid, to in self._conn.execute(
                    "SELECT f.call_text, f.entity_id, t.teaching_order "
                    "FROM call_text_figures f "
                    "LEFT JOIN teaching_order_calls t ON t.entity_id = f.entity_id "
                    f"WHERE f.call_text IN ({marks})", part):
                figure_tos.setdefault(text, {}).setdefault(eid, []).append(to)
            # intern#87: teaching_order_calls ist eine View mit einer Zeile je
            # (entity_id x Programm). Deterministisch das niedrigste Band je
            # Call-Text waehlen, NULL zuerst wie ORDER BY in SQLite (passt zu
            # _eid_min_to). Einzige Stelle der Regel, get_sequence_calls nutzt sie.
            for text, eid, to, name in self._conn.execute(
                    "SELECT m.call_text, m.entity_id, t.teaching_order, t.canonical_name "
                    "FROM call_text_mappings m "
                    "LEFT JOIN teaching_order_calls t ON t.entity_id = m.entity_id "
                    f"WHERE m.call_text IN ({marks})", part):
                old = mapping.get(text)
                if old is None or (_teaching_order_sort_key(to)
                                    < _teaching_order_sort_key(old[1])):
                    mapping[text] = (eid, to, name)
        out = {}
        for sid, (calls, seq_type, difficulty) in rows.items():
            result = []
            for i, text in enumerate(calls):
                m = mapping.get(text)
                if m:
                    result.append((i + 1, text, m[0], m[1], m[2],
                                   list(figure_tos.get(text, {}).values())))
                else:
                    result.append((i + 1, text, None, None, None, None))
            out[sid] = (result, seq_type, difficulty)
        return out

    def get_sequence_calls(self, sequence_id: int) -> list[tuple]:
        """Gibt alle Calls einer Sequenz zurueck (via call_text_mappings).

        Liest die volle Callliste aus calls_json (Fallback field_1..15) und joined
        mit call_text_mappings + teaching_order_calls. Laeuft ueber
        get_sequence_details_many, damit die Regel "niedrigstes Band je Call-Text"
        (intern#87) nur dort steht (Review #196).

        Returns:
            [(position, call_text, entity_id, teaching_order, canonical_name,
              figure_tos), ...]
            figure_tos: je Figur aus call_text_figures die Liste ihrer
            Teaching-Orders; daraus macht program_selection.call_program_label
            das Programm-Etikett (intern#176).
        """
        hit = self.get_sequence_details_many([sequence_id]).get(sequence_id)
        return hit[0] if hit else []

    def get_sequence_raw(self, sequence_id: int) -> dict | None:
        """Gibt die Rohdaten einer Sequenz zurueck (fuer den Editor).

        Returns:
            {"fields": [15 Strings/None], "level_original": str,
             "seq_type": str, "difficulty": str, "tags": str}  oder None.
        """
        cur = self._conn.execute(
            "SELECT calls_json, field_1, field_2, field_3, field_4, field_5, "
            "field_6, field_7, field_8, field_9, field_10, "
            "field_11, field_12, field_13, field_14, field_15, "
            "level_original, type, difficulty, tags "
            "FROM sequences WHERE id = ?",
            (sequence_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        # Volle Liste aus calls_json (Fallback: Mirror-Felder). Nicht mehr auf 15
        # begrenzt — der Editor bekommt alle Calls.
        fields = calls_from_json(row[0]) if row[0] else clean_calls(row[1:16])
        return {
            "fields": fields,
            "level_original": row[16] or "",
            "seq_type": row[17] or "",
            "difficulty": row[18] or "",
            "tags": row[19] or "",
        }

    def update_sequence(self, sequence_id: int, fields: list,
                        level_original: str = "", seq_type: str = "",
                        difficulty: str = "", tags: str = "") -> None:
        """Aktualisiert eine bestehende Sequenz (Editor).

        max_teaching_order wird auf NULL gesetzt — der Aufrufer sollte
        anschliessend recompute_sequence_max_to() ausfuehren.
        """
        mirror = calls_to_mirror_fields(fields)
        set_fields = ", ".join(f"field_{i} = ?" for i in range(1, 16))
        params = mirror + [level_original or "", canonicalize_seq_type(seq_type),
                           difficulty or "", calls_to_json(fields), tags or "",
                           sequence_id]
        self._conn.execute(
            f"UPDATE sequences SET {set_fields}, level_original = ?, "
            f"type = ?, difficulty = ?, calls_json = ?, tags = ?, "
            f"max_teaching_order = NULL "
            f"WHERE id = ?",
            params
        )
        self._sync_sequence_calls_for(sequence_id, fields)
        self._conn.commit()

    def find_sequence_by_fields(self, fields: list,
                                exclude_id: int = None) -> int | None:
        """Sucht eine Sequenz mit identischen 15 Feldern (exakte Dublette).

        Args:
            fields: Liste von Call-Texten (wird auf 15 aufgefuellt)
            exclude_id: Diese ID bei der Suche ignorieren (eigene beim Editieren)

        Returns:
            id der ersten gefundenen identischen Sequenz, sonst None.
        """
        # Vergleich ueber die volle Callliste (calls_json). Erkennt auch
        # >15-Call-Dubletten und ist unabhaengig von NULL/''/'-'-Feinheiten,
        # weil calls_json bereits bereinigt ist.
        params = [calls_to_json(fields)]
        sql = "SELECT id FROM sequences WHERE calls_json = ?"
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        sql += " ORDER BY id LIMIT 1"
        cur = self._conn.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None

    # ---- Teaching-Order-Calls (Referenztabelle) ----

    def clear_teaching_order_calls(self):
        """Loescht alle Programm-Zugehoerigkeiten (vor Neuimport).

        teaching_order_calls ist seit dem MS50-Umbau eine VIEW ueber
        calls + call_programs. Geleert werden die Zugehoerigkeiten
        (call_programs); die Identitaeten (calls) bleiben als FK-Ziel fuer
        call_text_mappings erhalten und werden beim Insert per OR IGNORE
        aktualisiert.
        """
        self._conn.execute("DELETE FROM call_programs;")
        self._conn.commit()

    def bulk_insert_teaching_order_calls(self, rows: list[tuple]):
        """Fuegt Teaching-Order-Eintraege ein (Identitaet + Zugehoerigkeit).

        Args:
            rows: [(entity_id, canonical_name, teaching_order, program), ...]

        Eine entity_id darf mehrfach vorkommen (mehrere Programme/Baender);
        eindeutig ist (entity_id, teaching_order).
        """
        self._conn.executemany(
            "INSERT OR IGNORE INTO calls (entity_id, canonical_name) VALUES (?, ?)",
            [(r[0], r[1]) for r in rows]
        )
        self._conn.executemany(
            "INSERT OR REPLACE INTO call_programs "
            "(entity_id, teaching_order, program) VALUES (?, ?, ?)",
            [(r[0], r[2], r[3]) for r in rows]
        )
        self._conn.commit()

    def get_teaching_order_calls(self) -> list[tuple]:
        """Alle Teaching-Order-Calls sortiert nach teaching_order.

        Returns:
            [(entity_id, canonical_name, teaching_order, program), ...]
        """
        cur = self._conn.execute(
            "SELECT entity_id, canonical_name, teaching_order, program "
            "FROM teaching_order_calls ORDER BY teaching_order"
        )
        return cur.fetchall()

    def get_teaching_order_count(self) -> int:
        """Anzahl der Teaching-Order-Eintraege."""
        cur = self._conn.execute("SELECT COUNT(*) FROM teaching_order_calls")
        return cur.fetchone()[0]

    # ---- Call-Text-Mappings (Zuordnungstabelle) ----

    def clear_call_text_mappings(self, mapped_by: str = None):
        """Loescht Mappings. Ohne Parameter: alle. Mit: nur die angegebene Quelle.

        Args:
            mapped_by: 'auto', 'manual' oder 'inferred' — None loescht alle
        """
        # BL-210: weitere Figuren zuerst, solange die Hauptzeilen noch sagen,
        # zu welcher Quelle sie gehoeren (nie Zusatzzeile ohne Hauptzeile).
        if mapped_by:
            self._conn.execute(
                "DELETE FROM call_text_figures_extra WHERE call_text IN "
                "(SELECT call_text FROM call_text_mappings WHERE mapped_by = ?)",
                (mapped_by,))
            self._conn.execute(
                "DELETE FROM call_text_mappings WHERE mapped_by = ?",
                (mapped_by,))
        else:
            self._conn.execute("DELETE FROM call_text_figures_extra;")
            self._conn.execute("DELETE FROM call_text_mappings;")
        self._conn.commit()

    def bulk_insert_call_text_mappings(self, rows: list[tuple]):
        """Fuegt Call-Text-Mappings ein.

        Args:
            rows: [(call_text, entity_id, mapped_by), ...]
        """
        self._conn.executemany(
            "INSERT OR IGNORE INTO call_text_mappings "
            "(call_text, entity_id, mapped_by) VALUES (?, ?, ?)",
            rows
        )
        self._conn.commit()

    def get_entity_for_call_text(self, call_text: str) -> str | None:
        """Gibt die gemappte entity_id fuer einen Call-Text zurueck.

        Returns None, wenn kein Mapping existiert ODER das Mapping auf NULL
        zeigt (z.B. bewusst nicht zugeordnet). Wird vom Editor fuer die
        Gruen-Markierung gemappter Zeilen genutzt.
        """
        if not call_text or not call_text.strip():
            return None
        cur = self._conn.execute(
            "SELECT entity_id FROM call_text_mappings WHERE call_text = ?",
            (call_text.strip(),)
        )
        row = cur.fetchone()
        if not row:
            return None
        return row[0]

    def set_call_text_mapping(self, call_text: str, entity_id: str,
                              mapped_by: str = "manual"):
        """Setzt oder aktualisiert ein einzelnes Mapping (fuer manuelle Zuordnung).

        BL-210: Einzel-Figur-Weg — eine bisherige Figuren-Menge des Texts wird
        dabei abgeraeumt, damit nie eine alte Menge halb stehen bleibt.
        """
        self._conn.execute(
            "DELETE FROM call_text_figures_extra WHERE call_text = ?",
            (call_text,))
        self._conn.execute(
            "INSERT OR REPLACE INTO call_text_mappings "
            "(call_text, entity_id, mapped_by) VALUES (?, ?, ?)",
            (call_text, entity_id, mapped_by)
        )
        self._conn.commit()

    def set_call_text_mappings(self, pairs: list, mapped_by: str = "manual") -> int:
        """Setzt viele Mappings in EINER Transaktion (ein einziges commit).

        pairs: [(call_text, entity_id), ...]

        Perf: das einzelne set_call_text_mapping committet je Aufruf (ein Fsync
        pro Zeile). Beim Bestaetigen vieler markierter Zeilen summiert sich das
        auf hunderte ms — als Batch sind es wenige ms. Gibt die Zahl der
        geschriebenen Zeilen zurueck.

        BL-210: Einzel-Figur-Weg — bisherige Figuren-Mengen der Texte werden
        abgeraeumt (siehe set_call_text_mapping).
        """
        rows = [(ct, eid, mapped_by) for ct, eid in pairs if ct and eid]
        if not rows:
            return 0
        self._conn.executemany(
            "DELETE FROM call_text_figures_extra WHERE call_text = ?",
            [(ct,) for ct, _eid, _mb in rows]
        )
        self._conn.executemany(
            "INSERT OR REPLACE INTO call_text_mappings "
            "(call_text, entity_id, mapped_by) VALUES (?, ?, ?)",
            rows
        )
        self._conn.commit()
        return len(rows)

    # ---- BL-210: Figuren-Mengen je Call-Text ----

    @staticmethod
    def _figure_rank_key(entity_id: str, min_to):
        """Sortierschluessel "hoechste Figur zuerst".

        Hoechste Figur = Figur, deren FRUEHESTE Teaching-Order am hoechsten ist
        (der Band-Filter wertet eine Figur als abgedeckt, sobald eine ihrer
        Programm-Zugehoerigkeiten erlaubt ist). Figur ohne call_programs-Zeile
        (min_to None) kommt zuletzt. Fuer die Filter dieser Version ist ihr
        Platz egal (Band-Filter uebergeht sie, Limit wertet den Text als
        ungemappt). Eine aeltere Version sieht aber nur die Hauptfigur und
        muss dort eine Figur MIT Programm finden, sonst uebergeht ihr
        Band-Filter den ganzen Call-Text.
        Gleichstand: entity_id aufsteigend.
        """
        if min_to is None:
            return (1, 0.0, entity_id)
        return (0, -min_to, entity_id)

    def _rank_figures(self, entity_ids) -> list[str]:
        """Entfernt Duplikate/Leere und sortiert hoechste Figur zuerst."""
        ids = list(dict.fromkeys(e for e in entity_ids if e))
        if len(ids) < 2:
            return ids
        placeholders = ",".join("?" * len(ids))
        min_to = dict(self._conn.execute(
            "SELECT entity_id, MIN(teaching_order) FROM call_programs "
            f"WHERE entity_id IN ({placeholders}) GROUP BY entity_id", ids))
        return sorted(ids, key=lambda e: self._figure_rank_key(e, min_to.get(e)))

    @classmethod
    def _collect_ranked_figures(cls, rows) -> dict[str, list[str]]:
        """(call_text, entity_id, min_to)-Zeilen -> {call_text: [hoechste, ...]}."""
        groups: dict[str, dict[str, object]] = {}
        for call_text, entity_id, min_to in rows:
            groups.setdefault(call_text, {})[entity_id] = min_to
        return {
            ct: sorted(figs, key=lambda e: cls._figure_rank_key(e, figs[e]))
            for ct, figs in groups.items()
        }

    def unknown_figures(self, entity_ids) -> set[str]:
        """entity_ids ohne Zeile in calls.

        Solche Zuordnungen stammen aus Altbestaenden, die ohne Fremdschluessel
        geschrieben wurden (Prod-DB: 65 auto-Zuordnungen, z.B. action_face_in).
        Neu schreiben laesst die DB sie nicht: set_call_text_figures laesst sie
        weg, der Picker markiert sie.
        """
        ids = list(dict.fromkeys(e for e in entity_ids if e))
        if not ids:
            return set()
        placeholders = ",".join("?" * len(ids))
        known = {r[0] for r in self._conn.execute(
            f"SELECT entity_id FROM calls WHERE entity_id IN ({placeholders})", ids)}
        return set(ids) - known

    def _write_call_text_figures(self, call_text: str, entity_ids,
                                 mapped_by: str):
        """Schreibt die Figuren-Menge eines Call-Texts OHNE commit.

        Hoechste Figur nach call_text_mappings, Rest nach
        call_text_figures_extra, alte Zusatzzeilen weg. Leere Menge entfernt
        die Zuordnung. Figuren ohne calls-Zeile fallen weg.
        """
        entity_ids = [e for e in entity_ids if e]
        unknown = self.unknown_figures(entity_ids)
        ranked = self._rank_figures(e for e in entity_ids if e not in unknown)
        self._conn.execute(
            "DELETE FROM call_text_figures_extra WHERE call_text = ?",
            (call_text,))
        if not ranked:
            self._conn.execute(
                "DELETE FROM call_text_mappings WHERE call_text = ?",
                (call_text,))
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO call_text_mappings "
            "(call_text, entity_id, mapped_by) VALUES (?, ?, ?)",
            (call_text, ranked[0], mapped_by))
        self._conn.executemany(
            "INSERT INTO call_text_figures_extra (call_text, entity_id) "
            "VALUES (?, ?)",
            [(call_text, e) for e in ranked[1:]])

    def set_call_text_figures(self, call_text: str, entity_ids,
                              mapped_by: str = "manual"):
        """Setzt die Figuren-Menge eines Call-Texts (ersetzt die bisherige).

        Leere Liste entfernt die Zuordnung (wie delete_call_text_mapping).
        Figuren ohne calls-Zeile fallen weg (siehe unknown_figures). Eine
        Transaktion: schlaegt ein Schreibschritt fehl, bleibt die bisherige
        Menge vollstaendig stehen.
        """
        try:
            self._write_call_text_figures(call_text, entity_ids, mapped_by)
        except Exception:
            self._conn.rollback()
            raise
        self._conn.commit()

    def get_call_text_figures(self, call_text: str) -> list[str]:
        """Figuren eines Call-Texts, hoechste zuerst. Ohne Zuordnung: []."""
        rows = self._conn.execute(
            _SELECT_CALL_TEXT_FIGURES_RANKED + " WHERE f.call_text = ?",
            (call_text,))
        return self._collect_ranked_figures(rows).get(call_text, [])

    def set_call_text_figures_bulk(self, pairs, mapped_by: str = "manual") -> int:
        """Setzt viele Figuren-Mengen in EINER Transaktion (ein commit).

        pairs: Iterable von (call_text, entity_ids). Je Text wie
        set_call_text_figures (leere Menge entfernt die Zuordnung); Paare ohne
        Call-Text werden uebersprungen. Gibt die Zahl der geschriebenen
        Call-Texte zurueck (analog set_call_text_mappings).
        """
        written = 0
        try:
            for call_text, entity_ids in pairs:
                if not call_text:
                    continue
                self._write_call_text_figures(call_text, entity_ids, mapped_by)
                written += 1
        except Exception:
            self._conn.rollback()
            raise
        self._conn.commit()
        return written

    def _normalize_call_text_figures(self):
        """Stellt die Invariante der Figuren-Mengen wieder her, OHNE commit.

        Fuer Referenz-Updates (Merges, geaenderte Teaching-Orders) und fuer
        Zustaende, die eine aeltere Version hinterlassen hat:
        - Zusatzzeilen ohne Hauptfigur oder gleich der Hauptfigur fallen weg
        - die hoechste Figur steht (wieder) in call_text_mappings
        Betrifft nur Texte mit Zusatzzeilen; mapped_by bleibt erhalten.
        Ohne Zusatzzeilen ein billiger No-Op (laeuft bei jedem Start).
        """
        if self._conn.execute(
                "SELECT 1 FROM call_text_figures_extra LIMIT 1").fetchone() is None:
            return
        self._conn.execute(
            "DELETE FROM call_text_figures_extra WHERE NOT EXISTS ("
            "SELECT 1 FROM call_text_mappings m "
            "WHERE m.call_text = call_text_figures_extra.call_text "
            "AND m.entity_id IS NOT NULL "
            "AND m.entity_id <> call_text_figures_extra.entity_id)")
        sets = self._collect_ranked_figures(self._conn.execute(
            _SELECT_CALL_TEXT_FIGURES_RANKED + " WHERE f.call_text IN "
            "(SELECT call_text FROM call_text_figures_extra)"))
        main = {ct: (eid, mb) for ct, eid, mb in self._conn.execute(
            "SELECT call_text, entity_id, mapped_by FROM call_text_mappings "
            "WHERE call_text IN (SELECT call_text FROM call_text_figures_extra)")}
        for call_text, ranked in sets.items():
            entity_id, mapped_by = main[call_text]
            if ranked[0] != entity_id:
                self._write_call_text_figures(call_text, ranked, mapped_by)

    def get_all_call_text_figures(self) -> dict[str, list[str]]:
        """Alle Figuren-Mengen in einem Query-Durchlauf:
        {call_text: [hoechste, ...]} — gleiche Reihenfolge wie
        get_call_text_figures. Texte ohne Figur fehlen."""
        rows = self._conn.execute(_SELECT_CALL_TEXT_FIGURES_RANKED)
        return self._collect_ranked_figures(rows)

    def get_sequence_ids_with_call_text(self, call_text: str) -> list[int]:
        """Sequenz-IDs, die den gegebenen (exakten) Call-Text enthalten.

        Nutzt den indizierten sequence_calls-Index (idx_seqcalls_calltext) —
        Index-Seek statt Full-Scan. Reihenfolge: kleinste ID zuerst (stabil zum
        Durchblaettern). Fuer "Beispiel zeigen" im Call-Mapping-Dialog.
        """
        ct = (call_text or "").strip()
        if not ct:
            return []
        cur = self._conn.execute(
            "SELECT DISTINCT sequence_id FROM sequence_calls "
            "WHERE call_text = ? ORDER BY sequence_id",
            (ct,)
        )
        return [row[0] for row in cur.fetchall()]

    def get_unmapped_call_texts_by_frequency(self) -> list[tuple]:
        """Gibt ungemappte Call-Texte sortiert nach Haeufigkeit zurueck.

        Returns:
            [(call_text, count), ...] — haeufigste zuerst, bei Gleichstand alphabetisch
        """
        cur = self._conn.execute("""
            SELECT je.value AS val, COUNT(*) AS cnt
            FROM sequences, json_each(sequences.calls_json) je
            WHERE je.value NOT IN (SELECT call_text FROM call_text_mappings)
            GROUP BY val
            ORDER BY cnt DESC, val ASC
        """)
        return cur.fetchall()

    def count_duplicate_sequences(self) -> tuple:
        """Zaehlt exakte Sequenz-Duplikate (alle 15 Felder identisch).

        Returns:
            (total, dup_groups, to_delete)
            total:      Gesamtzahl Sequenzen
            dup_groups: Anzahl Gruppen mit mind. einem Duplikat
            to_delete:  Anzahl zu loeschender Zeilen (Duplikate ohne den aeltesten Eintrag)
        """
        # Dubletten = identische volle Callliste (calls_json). Ersetzt das
        # GROUP BY ueber field_1..15 und erkennt auch >15-Call-Dubletten.
        cur = self._conn.execute("SELECT COUNT(*) FROM sequences")
        total = cur.fetchone()[0]

        cur = self._conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT MIN(id) FROM sequences
                GROUP BY calls_json
                HAVING COUNT(*) > 1
            )
        """)
        dup_groups = cur.fetchone()[0]

        cur = self._conn.execute("""
            SELECT COUNT(*) FROM sequences
            WHERE id NOT IN (
                SELECT MIN(id) FROM sequences GROUP BY calls_json
            )
        """)
        to_delete = cur.fetchone()[0]

        return (total, dup_groups, to_delete)

    def delete_sequences(self, seq_ids: list) -> int:
        """Loescht eine oder mehrere Sequenzen anhand der IDs.

        Sequenzen werden von keiner anderen Tabelle ueber Foreign Key
        referenziert — DELETE ist daher harmlos und endgueltig (kein
        Papierkorb wie bei Songs).

        Args:
            seq_ids: Liste der zu loeschenden Sequenz-IDs.

        Returns:
            Anzahl tatsaechlich geloeschter Zeilen.
        """
        if not seq_ids:
            return 0
        placeholders = ",".join("?" * len(seq_ids))
        # Index-Kinder zuerst (FK NO ACTION wuerde den Sequenz-Delete sonst blocken)
        self._conn.execute(
            f"DELETE FROM sequence_calls WHERE sequence_id IN ({placeholders})",
            list(seq_ids)
        )
        cur = self._conn.execute(
            f"DELETE FROM sequences WHERE id IN ({placeholders})",
            list(seq_ids)
        )
        deleted = cur.rowcount
        self._conn.commit()
        return deleted

    def remove_duplicate_sequences(self) -> int:
        """Loescht exakte Sequenz-Duplikate, behaelt den aeltesten Eintrag (MIN id).

        Fuehrt anschliessend VACUUM aus um den Speicherplatz freizugeben.

        Returns:
            Anzahl geloeschter Zeilen
        """
        # Index-Kinder der zu loeschenden Sequenzen zuerst entfernen (FK).
        self._conn.execute("""
            DELETE FROM sequence_calls
            WHERE sequence_id NOT IN (
                SELECT MIN(id) FROM sequences GROUP BY calls_json
            )
        """)
        cur = self._conn.execute("""
            DELETE FROM sequences
            WHERE id NOT IN (
                SELECT MIN(id) FROM sequences GROUP BY calls_json
            )
        """)
        deleted = cur.rowcount
        self._conn.commit()
        self._conn.execute("VACUUM")
        return deleted

    def get_all_call_texts_with_mapping(self) -> list[tuple]:
        """Gibt alle Call-Texte aus Sequenzen mit Haeufigkeit und aktuellem Mapping.

        Returns:
            [(call_text, count, entity_id, mapped_by), ...]
            entity_id/mapped_by sind None wenn kein Mapping.
            Sortiert: count DESC, call_text ASC.

        intern#95: Frueher lieferte die Abfrage zusaetzlich canonical_name und
        program aus der Mehrfach-View teaching_order_calls (eine Zeile je
        entity_id x Programm). Das Band war willkuerlich gewaehlt UND der Join
        vervielfachte die Zeilen, sodass COUNT(*) die Haeufigkeit einer Figur in
        zwei Programmen verdoppelte. Gelesen hat die beiden Spalten niemand — der
        Call-Mapping-Dialog nimmt seine Beschriftung aus _eid_to_label. Darum
        ganz raus statt ein Band zu bestimmen.
        """
        cur = self._conn.execute("""
            SELECT
                je.value AS val,
                COUNT(*) AS cnt,
                m.entity_id,
                m.mapped_by
            FROM sequences, json_each(sequences.calls_json) je
            LEFT JOIN call_text_mappings m ON m.call_text = je.value
            GROUP BY val
            ORDER BY cnt DESC, val ASC
        """)
        return cur.fetchall()

    def get_all_call_text_mappings(self) -> list[dict]:
        """Gibt alle Zuordnungen als Liste von Dicts zurueck (Export).

        BL-210: eine Zeile je Figur, hoechste Figur zuerst; weitere Figuren
        tragen das mapped_by der Hauptzeile. "Keine Figur" ist eine Zeile mit
        entity_id None. Grundlage fuer den v2-Export (mapping_io.build_export)
        und den Vergleich beim Import; 0.159 und aelter lesen v2 nicht.
        """
        figures = self.get_all_call_text_figures()
        cur = self._conn.execute(
            "SELECT call_text, entity_id, mapped_by FROM call_text_mappings ORDER BY call_text"
        )
        return [
            {"call_text": call_text, "entity_id": fig, "mapped_by": mapped_by}
            for call_text, entity_id, mapped_by in cur.fetchall()
            for fig in (figures.get(call_text) or [entity_id])
        ]

    def _local_call_text_sets(self) -> dict:
        """{call_text: (figuren, mapped_by)} inkl. "keine Figur" ([])."""
        out = {}
        for r in self.get_all_call_text_mappings():
            figs, _mb = out.setdefault(r["call_text"], ([], r["mapped_by"]))
            if r["entity_id"]:
                figs.append(r["entity_id"])
        return out

    def diff_call_text_figures(self, imported: dict) -> dict:
        """Vergleicht importierte Figuren-Mengen mit den lokalen (intern#79).

        imported: {call_text: obj mit .figures (list) und .mapped_by}
        (mapping_io.ImportedMapping). Steht lokal schon genau dieselbe Menge,
        ist der Text identisch, auch wenn sie verwaiste IDs enthaelt (Altbestand
        ohne calls-Zeile) -- dann gibt es nichts zu melden. Sonst fallen Figuren
        ohne calls-Zeile weg und werden gemeldet; bleibt dadurch von einer
        Menge nichts uebrig, wird der Call-Text uebersprungen (statt ihn zu
        "keine Figur" zu machen).

        Returns dict:
            new:        [(call_text, figuren, mapped_by)] lokal noch nicht da
            identical:  [call_text] gleiche Menge (Quelle egal)
            conflicts:  [(call_text, lokal, lokal_mb, import, import_mb)]
            unknown_figures: sortierte entity_ids ohne calls-Zeile, nur aus
                        Texten, die geschrieben wuerden (neu/Konflikt)
            skipped:    [call_text] nur unbekannte Figuren
        """
        local = self._local_call_text_sets()
        res = {"new": [], "identical": [], "conflicts": [],
               "unknown_figures": [], "skipped": []}
        pending = {}
        for ct, m in imported.items():
            if ct in local and set(m.figures) == set(local[ct][0]):
                res["identical"].append(ct)
            else:
                pending[ct] = m
        unknown = self.unknown_figures(
            [e for m in pending.values() for e in m.figures])
        reported = set()
        for ct, m in pending.items():
            figs = [e for e in m.figures if e not in unknown]
            dropped = set(m.figures) - set(figs)
            if m.figures and not figs:
                res["skipped"].append(ct)
                reported |= dropped
                continue
            if ct not in local:
                res["new"].append((ct, figs, m.mapped_by))
                reported |= dropped
                continue
            loc_figs, loc_mb = local[ct]
            if set(figs) == set(loc_figs):
                # nach dem Filtern identisch: wird nicht geschrieben, also
                # auch nichts melden
                res["identical"].append(ct)
            else:
                res["conflicts"].append((ct, loc_figs, loc_mb, figs, m.mapped_by))
                reported |= dropped
        res["unknown_figures"] = sorted(reported)
        return res

    def apply_call_text_figures_decisions(self, decisions) -> int:
        """Schreibt geklaerte Zuordnungen in EINER Transaktion (intern#79).

        decisions: Iterable von (call_text, figuren, mapped_by). figuren
        None entfernt die Zuordnung, [] setzt bewusst "keine Figur"
        (entity_id NULL), sonst die Menge. Rueckgabe: Anzahl Call-Texte.
        """
        written = 0
        try:
            for call_text, figs, mapped_by in decisions:
                if not call_text:
                    continue
                if figs is None:
                    self._write_call_text_figures(call_text, [], mapped_by)
                elif not figs:
                    self._conn.execute(
                        "DELETE FROM call_text_figures_extra WHERE call_text = ?",
                        (call_text,))
                    self._conn.execute(
                        "INSERT OR REPLACE INTO call_text_mappings "
                        "(call_text, entity_id, mapped_by) VALUES (?, NULL, ?)",
                        (call_text, mapped_by))
                else:
                    self._write_call_text_figures(call_text, figs, mapped_by)
                written += 1
        except Exception:
            self._conn.rollback()
            raise
        self._conn.commit()
        return written

    def delete_call_text_mapping(self, call_text: str):
        """Loescht ein bestehendes Mapping fuer den gegebenen Call-Text
        (BL-210: samt der weiteren Figuren seiner Menge)."""
        self._conn.execute(
            "DELETE FROM call_text_figures_extra WHERE call_text = ?", (call_text,)
        )
        self._conn.execute(
            "DELETE FROM call_text_mappings WHERE call_text = ?", (call_text,)
        )
        self._conn.commit()

    def ensure_filler_words_entity(self):
        """Stellt sicher dass der 'Filler Words'-Eintrag in teaching_order_calls existiert.

        teaching_order=0.001 → erscheint ganz oben in der sortierten Liste,
        beeinflusst max_teaching_order einer Sequenz nicht nennenswert. Seit
        intern#206 steht der Eintrag auch in reference_calls.json (der Reseed
        loescht sonst alle call_programs); hier bleibt nur die Absicherung.
        """
        self._conn.execute(
            "INSERT OR IGNORE INTO calls (entity_id, canonical_name) "
            "VALUES ('filler_words', 'Filler Words')"
        )
        self._conn.execute(
            "INSERT OR IGNORE INTO call_programs (entity_id, teaching_order, program) "
            "VALUES ('filler_words', 0.001, '')"
        )
        self._conn.commit()

    def split_sequence_call_at_comma(self, call_text: str) -> tuple:
        """Splittet einen Call-Text am ersten Komma in allen betroffenen Sequenzen.

        Findet alle Sequenzen die diesen Text in einem Feld enthalten,
        teilt ihn am ersten Komma auf und schiebt nachfolgende Felder
        um eine Position nach rechts. Ueberlauf bei Feld 15 wird abgeschnitten.

        Returns:
            (seq_count, split_count) — Anzahl Sequenzen + Einzelvorkommen
        """
        comma_idx = call_text.find(',')
        if comma_idx < 0:
            return (0, 0)
        part1 = call_text[:comma_idx].strip()
        part2 = call_text[comma_idx + 1:].strip()
        if not part1 or not part2:
            return (0, 0)

        target = call_text.strip()
        rows = self._conn.execute("""
            SELECT id, calls_json FROM sequences
            WHERE EXISTS (
                SELECT 1 FROM json_each(sequences.calls_json) je WHERE je.value = ?
            )
        """, (target,)).fetchall()

        seq_count = 0
        split_count = 0
        set_clause = ", ".join(f"field_{i}=?" for i in range(1, 16))

        for seq_id, cj in rows:
            calls = calls_from_json(cj)
            new_calls = []
            changed = False
            for c in calls:
                if c == target:
                    new_calls.extend([part1, part2])
                    split_count += 1
                    changed = True
                else:
                    new_calls.append(c)
            if not changed:
                continue
            # calls_json + Mirror aktualisieren. Kein Ueberlauf-Abschnitt mehr —
            # die Liste darf ueber 15 hinaus wachsen.
            mirror = calls_to_mirror_fields(new_calls)
            self._conn.execute(
                f"UPDATE sequences SET {set_clause}, calls_json=? WHERE id=?",
                tuple(mirror) + (calls_to_json(new_calls), seq_id)
            )
            self._sync_sequence_calls_for(seq_id, new_calls)
            seq_count += 1

        self._conn.commit()
        return (seq_count, split_count)

    def get_mapping_stats(self) -> dict:
        """Statistik ueber den Mapping-Stand."""
        # Alle einzigartigen Texte aus Sequenzen (volle Callliste via json_each)
        all_texts = set()
        cur = self._conn.execute(
            "SELECT DISTINCT je.value FROM sequences, "
            "json_each(sequences.calls_json) je"
        )
        for (val,) in cur.fetchall():
            if val and val.strip() and val.strip() != '-':
                all_texts.add(val.strip())

        cur = self._conn.execute("SELECT COUNT(*) FROM call_text_mappings WHERE entity_id IS NOT NULL")
        mapped_count = cur.fetchone()[0]

        # Zaehlung je Quelle in EINER Abfrage; 'inferred' = per "Optimieren"
        # aus Mengen-Vorschlaegen uebernommen (intern#97)
        by_source = dict(self._conn.execute(
            "SELECT mapped_by, COUNT(*) FROM call_text_mappings GROUP BY mapped_by"))

        return {
            "total_unique_texts": len(all_texts),
            "mapped": mapped_count,
            "unmapped": len(all_texts) - mapped_count,
            "auto": by_source.get("auto", 0),
            "manual": by_source.get("manual", 0),
            "inferred": by_source.get("inferred", 0),
        }

    def backfill_auto_mappings(self) -> int:
        """Legt fuer alle noch ungemappten Call-Texte, die EXAKT (Score 1.0) zu
        einem bekannten Call passen, ein 'auto'-Mapping an.

        Gemeinsame Basis fuer Startup-Backfill-Migration, Bulk-Import und den
        Remapping-Knopf — damit die drei Pfade nicht auseinanderlaufen. Ohne
        diesen Schritt bleibt ein Massenimport voellig ungemappt: der Band-Filter
        (Programmwahl) liefert dann 0 Sequenzen, obwohl welche da sind.

        Idempotent und risikoarm: fuegt nur exakte Treffer via INSERT OR IGNORE
        hinzu, fasst manuelle Mappings nie an und loescht nichts. Gibt die Anzahl
        neu angelegter Mappings zurueck.
        """
        toc = self.get_teaching_order_calls()
        if not toc:
            return 0
        from sequence_mapper import CallMatcher
        matcher = CallMatcher(toc)
        # Nur Texte OHNE bestehendes Mapping betrachten (manuelle bleiben unberuehrt).
        texts = [r[0] for r in self._conn.execute(
            "SELECT DISTINCT sc.call_text FROM sequence_calls sc "
            "LEFT JOIN call_text_mappings m ON m.call_text = sc.call_text "
            "WHERE m.call_text IS NULL"
        )]
        rows = []
        for t in texts:
            eid = matcher.exact_entity(t)
            if eid is not None:
                rows.append((t, eid, "auto"))
        if rows:
            self._conn.executemany(
                "INSERT OR IGNORE INTO call_text_mappings "
                "(call_text, entity_id, mapped_by) VALUES (?, ?, ?)", rows)
            self._conn.commit()
        return len(rows)

    def _backfill_auto_mappings_once(self):
        """Startup-Heilung (einmalig, per Flag in app_meta): baut fehlende Auto-
        Mappings fuer Bestands-DBs nach, die per Massenimport ungemappt blieben.

        Laeuft nach reseed_reference_data(), damit calls/call_programs aktuell
        sind. Bei frischen oder bereits gehealten DBs ein billiger No-Op.
        """
        done = self._conn.execute(
            "SELECT value FROM app_meta WHERE key='auto_mappings_backfilled'"
        ).fetchone()
        if done:
            return
        try:
            n = self.backfill_auto_mappings()
            if n:
                self.recompute_sequence_max_to()
                print(f"[SongDB] Auto-Mapping-Backfill: {n} fehlende Mappings ergaenzt")
        except Exception as e:
            # Backfill darf den Start nie verhindern — Flag NICHT setzen, damit es
            # beim naechsten Start erneut versucht wird.
            print(f"[SongDB] Auto-Mapping-Backfill uebersprungen: {e}")
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) "
            "VALUES ('auto_mappings_backfilled', '1')")
        self._conn.commit()

    def _remap_group_prefix_once(self):
        """Startup-Heilung (einmalig, per Flag in app_meta) fuer intern#89.

        Bis dahin belegte eine Figur mit Gruppe im Namen den Schluessel des
        blanken Calls ("All Eight Circulate" fing "Circulate"), und "All 8
        Spin The Top" landete auf "Spin the Top". Zuordnungen mit genau einer
        Figur, die auf diesen alten Volltreffer zeigen, bekommen den neuen --
        auch 'manual', denn dann hat der Caller nur den falschen gruenen
        Vorschlag bestaetigt. Danach ergaenzt der Abgleich die Texte, die erst
        jetzt ein Volltreffer sind, und die Einstufung wird neu gerechnet.
        """
        if self._conn.execute(
                "SELECT 1 FROM app_meta WHERE key='group_prefix_remapped'").fetchone():
            return
        try:
            toc = self.get_teaching_order_calls()
            if toc:
                from sequence_mapper import CallMatcher, normalize_call_text
                matcher = CallMatcher(toc)
                # Spiegelt CallMatcher._exact vor intern#89: normalisiert
                # (Gruppe vorn ab, kein canon_key), erster in Teaching-Order gewinnt
                old = {}
                for eid, name, *_ in toc:
                    old.setdefault(normalize_call_text(name), eid)
                rows = []
                for text, eid in self._conn.execute(
                        "SELECT call_text, entity_id FROM call_text_mappings m "
                        "WHERE NOT EXISTS (SELECT 1 FROM call_text_figures_extra x "
                        "WHERE x.call_text = m.call_text)"):
                    new = matcher.exact_entity(text)
                    if new and new != eid and eid == old.get(normalize_call_text(text)):
                        rows.append((new, text))
                self._conn.executemany(
                    "UPDATE call_text_mappings SET entity_id = ?, mapped_by = 'auto' "
                    "WHERE call_text = ?", rows)
                self.backfill_auto_mappings()   # committet, das UPDATE mit
                # Immer neu rechnen: scheitert es nach dem Commit, holt der
                # naechste Start es nach (dann ohne umzuhaengende Zeilen)
                self.recompute_sequence_max_to()
                if rows:
                    print(f"[SongDB] intern#89: {len(rows)} Zuordnungen umgehaengt")
        except Exception as e:
            # Darf den Start nie verhindern — Flag NICHT setzen, damit es beim
            # naechsten Start erneut versucht wird.
            print(f"[SongDB] Gruppen-Heilung (intern#89) uebersprungen: {e}")
            self._conn.rollback()
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) "
            "VALUES ('group_prefix_remapped', '1')")
        self._conn.commit()

    def _recompute_max_to_once(self):
        """Startup-Heilung (einmalig, per Flag in app_meta): rechnet
        max_teaching_order mit der neuen Band-Regel nach.

        intern#95: Bis dahin bestimmte recompute_sequence_max_to() bei Figuren in
        mehreren Programmen ein beliebiges (faktisch das hoechste) Band; jetzt
        gilt das niedrigste. Gespeicherte Werte aus Bestands-DBs sind damit zu
        hoch — ohne diese Nachrechnung blieben betroffene Sequenzen bis zum
        naechsten Import/Remapping aus dem Limit-Filter.
        """
        done = self._conn.execute(
            "SELECT value FROM app_meta WHERE key='max_to_min_band'"
        ).fetchone()
        if done:
            return
        try:
            self.recompute_sequence_max_to()
        except Exception as e:
            # Darf den Start nie verhindern — Flag NICHT setzen, damit es beim
            # naechsten Start erneut versucht wird.
            print(f"[SongDB] max_teaching_order-Nachrechnung uebersprungen: {e}")
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) "
            "VALUES ('max_to_min_band', '1')")
        self._conn.commit()

    def recompute_sequence_max_to(self):
        """Berechnet max_teaching_order fuer alle Sequenzen neu.

        Basiert auf call_text_figures (Mapping + Zusatzfiguren) und der fruehesten
        Teaching-Order je Figur. Konservativ: NULL wenn mindestens ein Feld
        unmapped ist.
        """
        cur = self._conn.execute(
            "SELECT id, calls_json, field_1, field_2, field_3, field_4, field_5, "
            "field_6, field_7, field_8, field_9, field_10, "
            "field_11, field_12, field_13, field_14, field_15 "
            "FROM sequences"
        )
        sequences = cur.fetchall()

        # Mapping-Cache laden. EIN Durchlauf ueber call_text_figures (Haupt-
        # mapping + Zusatzfiguren) mit der fruehesten Teaching-Order je Figur —
        # genau die Zeilen, die auch die Figuren-Rangfolge nutzt.
        #
        # intern#95: Vorher joint(e) diese Stelle auf die Mehrfach-View
        # teaching_order_calls (eine Zeile je entity_id x Programm) und behielt
        # per Dict-Comprehension die LETZTE Zeile -> ein beliebiges (faktisch das
        # hoechste) Band. Eine Figur ist aber schon ab ihrem NIEDRIGSTEN Band
        # tanzbar; sonst faellt eine Sequenz aus dem Limit-Filter, obwohl sie ins
        # Programm passt. min_to ist dieselbe Regel, nach der auch der Band-Filter
        # (_cover_ids) und der Figuren-Picker gehen.
        #
        text_to_to = _text_max_to(
            self._conn.execute(_SELECT_CALL_TEXT_FIGURES_RANKED))

        updates = []
        for seq in sequences:
            seq_id = seq[0]
            # Volle Callliste (calls_json), Fallback Mirror-Felder seq[2:17].
            calls = calls_from_json(seq[1]) if seq[1] else clean_calls(seq[2:17])
            max_to = None
            has_unmapped = False

            for text in calls:
                to = text_to_to.get(text)
                if to is not None:
                    max_to = max(max_to or 0.0, to)
                else:
                    has_unmapped = True

            # Konservativ: NULL wenn Felder unmapped
            if has_unmapped:
                max_to = None

            updates.append((max_to, seq_id))

        self._conn.executemany(
            "UPDATE sequences SET max_teaching_order = ? WHERE id = ?",
            updates
        )
        self._conn.commit()

    def get_unmapped_call_texts_of_sequence(self, sequence_id: int) -> list[str]:
        """intern#119: Call-Texte einer Sequenz ohne (tanzbare) Zuordnung, in
        Sequenz-Reihenfolge, ohne Doppelte.

        Dieselbe Regel wie recompute_sequence_max_to(): ein Text zaehlt als
        ungemappt, wenn er keine Zuordnung hat oder einer seiner Figuren die
        Teaching-Order fehlt. Genau diese Texte machen max_teaching_order NULL.
        """
        row = self._conn.execute(
            "SELECT calls_json, field_1, field_2, field_3, field_4, field_5, "
            "field_6, field_7, field_8, field_9, field_10, "
            "field_11, field_12, field_13, field_14, field_15 "
            "FROM sequences WHERE id = ?", (sequence_id,)).fetchone()
        if not row:
            return []
        calls = list(dict.fromkeys(
            calls_from_json(row[0]) if row[0] else clean_calls(row[1:16])))
        if not calls:
            return []
        marks = ",".join("?" * len(calls))
        text_to_to = _text_max_to(self._conn.execute(
            f"{_SELECT_CALL_TEXT_FIGURES_RANKED} WHERE f.call_text IN ({marks})",
            calls))
        return [t for t in calls if text_to_to.get(t) is None]

    def get_all_sequences_raw(self) -> list[tuple]:
        """Gibt alle Sequenzen mit Rohdaten zurueck (fuer Remapping).

        Returns:
            [(id, field_1..field_15), ...]
        """
        cur = self._conn.execute(
            "SELECT id, field_1, field_2, field_3, field_4, field_5, "
            "field_6, field_7, field_8, field_9, field_10, "
            "field_11, field_12, field_13, field_14, field_15 "
            "FROM sequences ORDER BY id"
        )
        return cur.fetchall()
